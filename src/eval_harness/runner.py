"""The runner: resolve prices, select cases, ask the budget guard, run, score, record."""

import hashlib
import json
import secrets
import subprocess
import time
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from eval_harness.agent import run_agent
from eval_harness.budget import decide_start, estimate_run_cost, remaining_budget, should_abort
from eval_harness.cases import (
    CONSISTENCY,
    PAIR_LANGUAGES,
    Case,
    CaseError,
    case_set_hash,
    load_cases,
    load_open_questions,
)
from eval_harness.config import Config, same_family
from eval_harness.final_answer import FinalAnswer
from eval_harness.ingest import Chunk, IngestError
from eval_harness.judge import (
    PAIR_RUBRIC,
    STRUCTURED_OUTPUT_PARAMETERS,
    RubricError,
    judge_scorer,
    load_rubrics,
    pair_judge,
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
from eval_harness.pack import PackError, load_pack_tools, mark_open_questions
from eval_harness.scorers import (
    SCORERS,
    PairScorer,
    Scorer,
    article_key,
    consistency_scorer,
    score_case,
    score_pair,
)
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
    pair_rubric = rubrics.pop(PAIR_RUBRIC, None)
    open_questions = _load_open_questions(config)
    cases = _select_cases(
        config, open_questions, category, case_id, limit, [*SCORERS, *rubrics, CONSISTENCY]
    )
    pairs = sum(case.language == "both" for case in cases)
    if pairs and pair_rubric is None:
        raise RunRefused(
            f"bilingual cases need the rubric {config.pack / 'evals' / 'rubrics' / 'bilingual.md'}"
        )
    agent_runs = sum(len(_inputs(case)) for case in cases)
    judged_per_repeat = pairs + sum(
        len(_inputs(case)) for case in cases for name in case.scoring if name in rubrics
    )
    judge = _judge_model(config, models) if judged_per_repeat else None
    manifest, index = _load_corpus(config)
    _check_planted_chunks(cases, index)
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
    if open_questions is not None:
        tools = mark_open_questions(tools, open_questions)

    ledger = Ledger(config.ledger_path)
    ledger_total = ledger.total()
    estimate = estimate_run_cost(
        case_count=agent_runs * repeats,
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
                planted = case.planted_chunks or []

                def record_retrieval(
                    tool: str, chunks: list[Chunk], trace: Trace = trace, planted=planted
                ) -> None:
                    trace.add(
                        "retrieval",
                        tool=tool,
                        chunks=[
                            {
                                "id": c.id,
                                "instrument": c.instrument,
                                "article": c.article,
                                "text": c.text,
                                **({"planted": True} if c in planted else {}),
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
                finals: dict[str, FinalAnswer] | None = {}
                halves: dict[str, list[dict[str, Any]]] = {}
                try:
                    for language, user_input in _inputs(case).items():
                        if case.language == "both":
                            trace.add("half", language=language, input=user_input)
                        first_step = len(trace.steps)
                        finals[language] = run_agent(
                            client,
                            model=model,
                            system_prompt=system_prompt,
                            user_input=user_input,
                            tools=[
                                *search_tools(
                                    index, instruments, record_retrieval, embed_query, planted
                                ),
                                *tools,
                            ],
                            settings=config.agent,
                            trace=trace,
                            on_response=record,
                        )
                        halves[language] = trace.steps[first_step:]
                except OpenRouterError as exc:
                    trace.add("error", message=str(exc))
                    finals = None
                except _BudgetCrossed:
                    results.append(
                        _aborted(case, repeat, trace, case_spend, time.monotonic() - started)
                    )
                    raise
                latency = round(time.monotonic() - started, 3)

                scorers = SCORERS
                pair_scorers: dict[str, PairScorer] = {}
                if judge is not None:

                    def record_judge(response: ChatResponse, record=record) -> None:
                        record(response, "judge", judge.id)

                    scorers = SCORERS | {
                        name: judge_scorer(
                            client,
                            model=judge,
                            rubric=rubric,
                            settings=config.judge,
                            on_response=record_judge,
                        )
                        for name, rubric in rubrics.items()
                    }
                    if pair_rubric is not None:
                        pair_scorers[CONSISTENCY] = consistency_scorer(
                            pair_judge(
                                client,
                                model=judge,
                                rubric=pair_rubric,
                                settings=config.judge,
                                on_response=record_judge,
                            )
                        )
                try:
                    status, passed = _score(
                        case, finals, halves, trace, scorers, pair_scorers, rubrics
                    )
                except _BudgetCrossed:
                    results.append(_aborted(case, repeat, trace, case_spend, latency))
                    raise
                result = CaseResult(
                    case.id,
                    repeat,
                    case.category,
                    case.reviewed,
                    status,
                    passed,
                    case_spend,
                    latency,
                )
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


def _check_planted_chunks(cases: list[Case], index: SearchIndex) -> None:
    """A planted chunk must claim an article the corpus lacks, so citing it is detectable."""
    corpus_articles = {article_key(c.instrument, c.article) for c in index.chunks}
    for case in cases:
        for chunk in case.planted_chunks or []:
            if article_key(chunk.instrument, chunk.article) in corpus_articles:
                raise RunRefused(
                    f"case {case.id!r}: planted chunk {chunk.id} claims an article that is in "
                    "the corpus; give it an article number the corpus does not have"
                )


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


def _load_open_questions(config: Config) -> dict[str, bool] | None:
    if config.open_questions is None:
        return None
    try:
        return load_open_questions(config.open_questions)
    except CaseError as exc:
        raise RunRefused(f"invalid cases: {exc}") from exc


def _select_cases(
    config: Config,
    open_questions: dict[str, bool] | None,
    category: str | None,
    case_id: str | None,
    limit: int | None,
    scorer_names: list[str],
) -> list[Case]:
    try:
        cases = load_cases(config.pack / "evals" / "cases", scorer_names, open_questions)
    except CaseError as exc:
        raise RunRefused(f"invalid cases: {exc}") from exc
    selected = [c for c in cases if category in (None, c.category) and case_id in (None, c.id)]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise RunRefused("no cases match the selection")
    return selected


def _inputs(case: Case) -> dict[str, str]:
    """The questions to put to the agent: one, or both halves of a bilingual pair."""
    if isinstance(case.input, dict):
        return {language: case.input[language] for language in PAIR_LANGUAGES}
    return {case.language: case.input}


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
    finals: dict[str, FinalAnswer] | None,
    halves: dict[str, list[dict[str, Any]]],
    trace: Trace,
    scorers: dict[str, Scorer],
    pair_scorers: dict[str, PairScorer],
    deferred: Collection[str],
) -> tuple[str, bool]:
    """The case's status and whether it passed, with its verdict added to the trace."""
    if finals is None:
        trace.add("verdict", passed=False, details={"error": "the case did not finish"})
        return "error", False
    if case.language == "both":
        verdict = score_pair(case, finals, halves, scorers, pair_scorers, deferred)
    else:
        verdict = score_case(case, finals[case.language], trace.steps, scorers, deferred)
    trace.add("verdict", passed=verdict.passed, details=verdict.details)
    statuses = {final.status for final in finals.values()}
    status = (
        statuses.pop()
        if len(statuses) == 1
        else " ".join(f"{language}={final.status}" for language, final in finals.items())
    )
    return status, verdict.passed


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
