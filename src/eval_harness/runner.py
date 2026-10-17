"""The runner: resolve prices, select cases, ask the budget guard, run, score, record."""

import hashlib
import json
import secrets
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from eval_harness.agent import run_agent
from eval_harness.budget import decide_start, estimate_run_cost, remaining_budget, should_abort
from eval_harness.cases import Case, CaseError, case_set_hash, load_cases, load_open_questions
from eval_harness.config import Config, same_family
from eval_harness.final_answer import FinalAnswer
from eval_harness.ingest import Chunk, IngestError
from eval_harness.judge import (
    STRUCTURED_OUTPUT_PARAMETERS,
    Rubric,
    RubricError,
    judge_scorer,
    load_rubrics,
)
from eval_harness.ledger import Ledger
from eval_harness.manifest import Manifest, ManifestError, load_manifest
from eval_harness.openrouter import (
    ChatResponse,
    EmbeddingResponse,
    ModelInfo,
    OpenRouterClient,
    OpenRouterError,
)
from eval_harness.pack import PackError, load_pack_tools
from eval_harness.scorers import SCORERS, Scorer, score_case
from eval_harness.search import SearchIndex, search_tools
from eval_harness.trace import Trace


class RunRefused(Exception):
    """The run did not start; nothing was spent."""


class _BudgetCrossed(Exception):
    pass


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    repeat: int
    category: str
    reviewed: bool
    status: str
    passed: bool
    cost_usd: float
    latency_s: float


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    cases: list[CaseResult]
    run_spend_usd: float
    cumulative_usd: float
    remaining_usd: float


def run_eval(
    config: Config,
    client: OpenRouterClient,
    *,
    model_id: str,
    category: str | None = None,
    case_id: str | None = None,
    limit: int | None = None,
    repeats: int = 1,
    echo: Callable[[str], None] = print,
) -> RunResult:
    """Run the selected cases against one model. Raises RunRefused if the guard says no."""
    models = client.models()
    if model_id not in models:
        raise RunRefused(f"model {model_id!r} is not in the OpenRouter models list")
    model = models[model_id]
    if same_family(model_id, config.judge_model):
        raise RunRefused(
            f"the agent {model_id!r} is from the same model family as the judge "
            f"{config.judge_model!r}"
        )

    try:
        rubrics = load_rubrics(config.pack)
    except RubricError as exc:
        raise RunRefused(str(exc)) from exc
    cases = _select_cases(config, category, case_id, limit, rubrics)
    judged_per_repeat = sum(name in rubrics for case in cases for name in case.scoring)
    judge = _judge_model(config, models) if judged_per_repeat else None
    manifest, index = _load_corpus(config)
    instruments = {
        s.instrument: manifest.instruments[s.instrument] for s in manifest.indexed_sources
    }
    cases_hash = case_set_hash(config.pack / "evals" / "cases")
    manifest_hash = _manifest_hash(config)
    system_prompt = (config.pack / "system_prompt.md").read_text(encoding="utf-8")
    try:
        tools = load_pack_tools(config.pack)
    except PackError as exc:
        raise RunRefused(str(exc)) from exc

    ledger = Ledger(config.ledger_path)
    ledger_total = ledger.total()
    estimate = estimate_run_cost(
        case_count=len(cases) * repeats,
        history_per_case_usd=ledger.per_case_average(model=model_id, category=category),
        prompt_price_usd=model.prompt_price_usd,
        completion_price_usd=model.completion_price_usd,
        assumed_prompt_tokens=config.budget.assumed_prompt_tokens_per_case,
        assumed_completion_tokens=config.budget.assumed_completion_tokens_per_case,
        margin=config.budget.safety_margin,
    )
    if judge is not None:
        estimate += estimate_run_cost(
            case_count=judged_per_repeat * repeats,
            history_per_case_usd=None,
            prompt_price_usd=judge.prompt_price_usd,
            completion_price_usd=judge.completion_price_usd,
            assumed_prompt_tokens=config.budget.assumed_prompt_tokens_per_case,
            assumed_completion_tokens=config.budget.assumed_completion_tokens_per_case,
            margin=config.budget.safety_margin,
        )
    try:
        key_usage: float | None = client.key_usage()
    except OpenRouterError:
        key_usage = None
    decision = decide_start(
        estimate_usd=estimate,
        ledger_total_usd=ledger_total,
        key_usage_usd=key_usage,
        ceiling_usd=config.budget.ceiling_usd,
    )
    if not decision.allowed or key_usage is None or decision.remaining_usd is None:
        raise RunRefused(decision.reason)
    echo(f"budget ok: {decision.reason}")

    started_at = datetime.now(UTC)
    run_id = f"{started_at:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    run_dir = config.runs_dir / run_id
    run_spend = 0.0
    results: list[CaseResult] = []
    status = "completed"

    try:
        for repeat in range(1, repeats + 1):
            for case in cases:
                case_spend = 0.0

                def record(
                    response: ChatResponse | EmbeddingResponse,
                    purpose: str = "agent",
                    model_used: str = model_id,
                    case: Case = case,
                    repeat: int = repeat,
                ) -> None:
                    nonlocal run_spend, case_spend
                    ledger.append(
                        run_id=run_id,
                        purpose=purpose,
                        model=model_used,
                        usage=response.usage,
                        case_id=case.id,
                        category=case.category,
                        repeat=repeat,
                    )
                    run_spend += response.cost
                    case_spend += response.cost
                    if should_abort(run_spend_usd=run_spend, remaining_usd=decision.remaining_usd):
                        raise _BudgetCrossed

                def embed_query(query: str, record=record) -> list[float]:
                    response = client.embed(config.embedding_model, [query])
                    record(response, "embedding", config.embedding_model)
                    return response.vectors[0]

                trace = Trace(run_dir / "traces" / f"{case.id}.{repeat}.jsonl")

                def record_retrieval(tool: str, chunks: list[Chunk], trace: Trace = trace) -> None:
                    trace.add(
                        "retrieval",
                        tool=tool,
                        chunks=[
                            {
                                "id": c.id,
                                "instrument": c.instrument,
                                "article": c.article,
                                "text": c.text,
                            }
                            for c in chunks
                        ],
                    )

                trace.add(
                    "case",
                    case_id=case.id,
                    category=case.category,
                    language=case.language,
                    input=case.input,
                    model=model_id,
                    repeat=repeat,
                )
                started = time.monotonic()
                try:
                    final = run_agent(
                        client,
                        model=model,
                        system_prompt=system_prompt,
                        user_input=case.input,
                        tools=[
                            *search_tools(index, instruments, record_retrieval, embed_query),
                            *tools,
                        ],
                        settings=config.agent,
                        trace=trace,
                        on_response=record,
                    )
                except OpenRouterError as exc:
                    trace.add("error", message=str(exc))
                    final = None
                except _BudgetCrossed:
                    results.append(
                        _aborted(case, repeat, trace, case_spend, time.monotonic() - started)
                    )
                    raise
                latency = round(time.monotonic() - started, 3)

                scorers = SCORERS
                if judge is not None:
                    scorers = SCORERS | {
                        name: judge_scorer(
                            client,
                            model=judge,
                            rubric=rubric,
                            settings=config.judge,
                            on_response=lambda response: record(response, "judge", judge.id),
                        )
                        for name, rubric in rubrics.items()
                    }
                agent_spend = case_spend
                try:
                    result = _score(case, repeat, final, trace, agent_spend, latency, scorers)
                except _BudgetCrossed:
                    results.append(_aborted(case, repeat, trace, agent_spend, latency))
                    raise
                results.append(result)
                echo(_case_line(result))
    except _BudgetCrossed:
        status = "aborted"

    cumulative = max(ledger.total(), key_usage + run_spend)
    remaining = remaining_budget(config.budget.ceiling_usd, ledger.total(), key_usage + run_spend)

    run = RunResult(run_id, status, results, run_spend, cumulative, remaining)
    reviewed, unreviewed = _tally(results, reviewed=True), _tally(results, reviewed=False)
    _write_summary(
        run_dir,
        run,
        {
            "started_at": started_at.isoformat(),
            "case_set_hash": cases_hash,
            "manifest_hash": manifest_hash,
            "git_commit": _git_commit(config),
            "config": asdict(config),
            "model": model_id,
            "models": {
                "agent": config.agent_model,
                "judge": config.judge_model,
                "embedding": config.embedding_model,
            },
            "pricing": asdict(model) | {"supported_parameters": sorted(model.supported_parameters)},
            "selection": {
                "category": category,
                "case": case_id,
                "limit": limit,
                "repeats": repeats,
            },
            "estimate_usd": estimate,
            "ledger_total_at_start_usd": ledger_total,
            "key_usage_at_start_usd": key_usage,
            "reviewed": reviewed,
            "unreviewed": unreviewed,
        },
    )
    passed = sum(r.passed for r in results)
    echo(f"run {run_id} {status}: {len(results)} case(s), {passed} passed")
    echo(f"headline (reviewed cases only): {reviewed['passed']}/{reviewed['total']} passed")
    echo(f"unreviewed: {unreviewed['passed']}/{unreviewed['total']} passed, not in the headline")
    echo(
        f"run spend USD {run_spend:.6f}; cumulative USD {cumulative:.6f}; "
        f"remaining USD {remaining:.6f}"
    )
    return run


def _load_corpus(config: Config) -> tuple[Manifest, SearchIndex]:
    try:
        return load_manifest(config.pack), SearchIndex.load(
            config.index_dir, config.embedding_model
        )
    except (ManifestError, IngestError) as exc:
        raise RunRefused(str(exc)) from exc


def _judge_model(config: Config, models: dict[str, ModelInfo]) -> ModelInfo:
    judge = models.get(config.judge_model)
    if judge is None:
        raise RunRefused(f"judge model {config.judge_model!r} is not in the OpenRouter models list")
    if not judge.supported_parameters >= STRUCTURED_OUTPUT_PARAMETERS:
        raise RunRefused(
            f"judge model {judge.id!r} does not support structured outputs "
            f"({sorted(STRUCTURED_OUTPUT_PARAMETERS)})"
        )
    return judge


def _select_cases(
    config: Config,
    category: str | None,
    case_id: str | None,
    limit: int | None,
    rubrics: dict[str, Rubric],
) -> list[Case]:
    try:
        questions = load_open_questions(config.open_questions) if config.open_questions else None
        cases = load_cases(config.pack / "evals" / "cases", [*SCORERS, *rubrics], questions)
    except CaseError as exc:
        raise RunRefused(f"invalid cases: {exc}") from exc
    selected = [c for c in cases if category in (None, c.category) and case_id in (None, c.id)]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise RunRefused("no cases match the selection")
    unsupported = [c.id for c in selected if not isinstance(c.input, str)]
    if unsupported:
        raise RunRefused(f"bilingual inputs are not supported by the runner yet: {unsupported}")
    return selected


def _manifest_hash(config: Config) -> str | None:
    manifests = sorted(config.pack.glob("manifest.*"))
    if not manifests:
        return None
    if len(manifests) > 1:
        raise RunRefused(f"the pack has several corpus manifests: {[p.name for p in manifests]}")
    return hashlib.sha256(manifests[0].read_bytes()).hexdigest()


def _git_commit(config: Config) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.pack,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _tally(results: list[CaseResult], *, reviewed: bool) -> dict[str, Any]:
    group = [r for r in results if r.reviewed == reviewed]
    by_category: dict[str, dict[str, int]] = {}
    for result in group:
        counts = by_category.setdefault(result.category, {"total": 0, "passed": 0})
        counts["total"] += 1
        counts["passed"] += result.passed
    return {"total": len(group), "passed": sum(r.passed for r in group), "by_category": by_category}


def _score(
    case: Case,
    repeat: int,
    final: FinalAnswer | None,
    trace: Trace,
    cost: float,
    latency: float,
    scorers: dict[str, Scorer],
) -> CaseResult:
    if final is None:
        trace.add("verdict", passed=False, details={"error": "the case did not finish"})
        return CaseResult(
            case.id, repeat, case.category, case.reviewed, "error", False, cost, latency
        )
    verdict = score_case(case, final, trace.steps, scorers)
    trace.add("verdict", passed=verdict.passed, details=verdict.details)
    return CaseResult(
        case.id, repeat, case.category, case.reviewed, final.status, verdict.passed, cost, latency
    )


def _aborted(case: Case, repeat: int, trace: Trace, cost: float, latency: float) -> CaseResult:
    trace.add("aborted", reason="run spend crossed the remaining budget")
    return CaseResult(
        case.id, repeat, case.category, case.reviewed, "aborted", False, cost, round(latency, 3)
    )


def _case_line(result: CaseResult) -> str:
    mark = "PASS" if result.passed else "FAIL"
    reviewed = "" if result.reviewed else " [unreviewed]"
    return (
        f"{mark} {result.case_id} (repeat {result.repeat}) status={result.status} "
        f"cost USD {result.cost_usd:.6f} latency {result.latency_s:.2f}s{reviewed}"
    )


def _write_summary(run_dir, run: RunResult, context: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run.run_id,
        "status": run.status,
        **context,
        "run_spend_usd": run.run_spend_usd,
        "cumulative_usd": run.cumulative_usd,
        "remaining_usd": run.remaining_usd,
        "cases": [asdict(c) for c in run.cases],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
