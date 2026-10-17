"""The runner: resolve prices, select cases, ask the budget guard, run, score, record."""

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from eval_harness.agent import run_agent
from eval_harness.budget import decide_start, estimate_run_cost, remaining_budget, should_abort
from eval_harness.cases import Case, CaseError, load_cases
from eval_harness.config import Config
from eval_harness.final_answer import FinalAnswer
from eval_harness.ledger import Ledger
from eval_harness.openrouter import ChatResponse, OpenRouterClient, OpenRouterError
from eval_harness.pack import PackError, load_pack_tools
from eval_harness.scorers import SCORERS, score_case
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
    limit: int | None = None,
    repeats: int = 1,
    echo: Callable[[str], None] = print,
) -> RunResult:
    """Run the selected cases against one model. Raises RunRefused if the guard says no."""
    models = client.models()
    if model_id not in models:
        raise RunRefused(f"model {model_id!r} is not in the OpenRouter models list")
    model = models[model_id]

    cases = _select_cases(config, category, limit)
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

                def record(response: ChatResponse, case: Case = case, repeat: int = repeat) -> None:
                    nonlocal run_spend, case_spend
                    ledger.append(
                        run_id=run_id,
                        purpose="agent",
                        model=model_id,
                        usage=response.usage,
                        case_id=case.id,
                        category=case.category,
                        repeat=repeat,
                    )
                    run_spend += response.cost
                    case_spend += response.cost
                    if should_abort(run_spend_usd=run_spend, remaining_usd=decision.remaining_usd):
                        raise _BudgetCrossed

                trace = Trace(run_dir / "traces" / f"{case.id}.{repeat}.jsonl")
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
                        tools=tools,
                        settings=config.agent,
                        trace=trace,
                        on_response=record,
                    )
                except OpenRouterError as exc:
                    trace.add("error", message=str(exc))
                    final = None
                except _BudgetCrossed:
                    trace.add("aborted", reason="run spend crossed the remaining budget")
                    results.append(
                        CaseResult(
                            case.id,
                            repeat,
                            case.category,
                            case.reviewed,
                            "aborted",
                            False,
                            case_spend,
                            round(time.monotonic() - started, 3),
                        )
                    )
                    raise
                latency = round(time.monotonic() - started, 3)

                result = _score(case, repeat, final, trace, case_spend, latency)
                results.append(result)
                echo(_case_line(result))
    except _BudgetCrossed:
        status = "aborted"

    cumulative = max(ledger.total(), key_usage + run_spend)
    remaining = remaining_budget(config.budget.ceiling_usd, ledger.total(), key_usage + run_spend)

    run = RunResult(run_id, status, results, run_spend, cumulative, remaining)
    _write_summary(
        run_dir,
        run,
        {
            "started_at": started_at.isoformat(),
            "model": model_id,
            "models": {
                "agent": config.agent_model,
                "judge": config.judge_model,
                "embedding": config.embedding_model,
            },
            "pricing": asdict(model) | {"supported_parameters": sorted(model.supported_parameters)},
            "selection": {"category": category, "limit": limit, "repeats": repeats},
            "estimate_usd": estimate,
            "ledger_total_at_start_usd": ledger_total,
            "key_usage_at_start_usd": key_usage,
        },
    )
    passed = sum(r.passed for r in results)
    echo(f"run {run_id} {status}: {len(results)} case(s), {passed} passed")
    echo(
        f"run spend USD {run_spend:.6f}; cumulative USD {cumulative:.6f}; "
        f"remaining USD {remaining:.6f}"
    )
    return run


def _select_cases(config: Config, category: str | None, limit: int | None) -> list[Case]:
    try:
        cases = load_cases(config.pack / "evals" / "cases", SCORERS)
    except CaseError as exc:
        raise RunRefused(f"invalid cases: {exc}") from exc
    selected = [c for c in cases if category is None or c.category == category]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise RunRefused("no cases match the selection")
    unsupported = [c.id for c in selected if not isinstance(c.input, str)]
    if unsupported:
        raise RunRefused(f"bilingual inputs are not supported by the runner yet: {unsupported}")
    return selected


def _score(
    case: Case,
    repeat: int,
    final: FinalAnswer | None,
    trace: Trace,
    cost: float,
    latency: float,
) -> CaseResult:
    if final is None:
        trace.add("verdict", passed=False, details={"error": "the case did not finish"})
        return CaseResult(
            case.id, repeat, case.category, case.reviewed, "error", False, cost, latency
        )
    verdict = score_case(case, final, trace.steps)
    trace.add("verdict", passed=verdict.passed, details=verdict.details)
    return CaseResult(
        case.id, repeat, case.category, case.reviewed, final.status, verdict.passed, cost, latency
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
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
