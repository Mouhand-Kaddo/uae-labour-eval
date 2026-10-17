"""Budget guard decisions (ADR-0008). Pure functions; the runner does the I/O."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    estimate_usd: float
    remaining_usd: float | None
    reason: str


def decide_start(
    *,
    estimate_usd: float,
    ledger_total_usd: float,
    key_usage_usd: float | None,
    ceiling_usd: float,
) -> BudgetDecision:
    """Allow a run only if its estimate fits the budget left after the larger recorded spend."""
    if key_usage_usd is None:
        return BudgetDecision(
            False, estimate_usd, None, "key usage is unreachable; refusing to run blind"
        )
    spent = max(ledger_total_usd, key_usage_usd)
    remaining = ceiling_usd - spent
    numbers = (
        f"estimate USD {estimate_usd:.4f}, remaining USD {remaining:.4f} "
        f"(ceiling {ceiling_usd:.4f} - max(ledger {ledger_total_usd:.4f}, "
        f"key usage {key_usage_usd:.4f}))"
    )
    if estimate_usd > remaining:
        return BudgetDecision(False, estimate_usd, remaining, f"over budget: {numbers}")
    return BudgetDecision(True, estimate_usd, remaining, numbers)


def estimate_run_cost(
    *,
    case_count: int,
    history_per_case_usd: float | None,
    prompt_price_usd: float,
    completion_price_usd: float,
    assumed_prompt_tokens: int,
    assumed_completion_tokens: int,
    margin: float,
) -> float:
    """Per-case cost from ledger history, else live prices x assumed tokens; x cases x margin."""
    if history_per_case_usd is None:
        per_case = (
            prompt_price_usd * assumed_prompt_tokens
            + completion_price_usd * assumed_completion_tokens
        )
    else:
        per_case = history_per_case_usd
    return per_case * case_count * margin


def should_abort(*, run_spend_usd: float, remaining_usd: float) -> bool:
    """A run aborts once its own spend crosses the budget that remained when it started."""
    return run_spend_usd > remaining_usd
