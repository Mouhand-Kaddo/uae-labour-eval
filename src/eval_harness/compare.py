"""`eval compare`: two runs side by side as a Markdown table, from their summary.json files."""

from collections.abc import Callable
from typing import Any

from eval_harness.report import count, pct, seconds, usd
from eval_harness.report_stats import ReportNumbers, Score, report_numbers

MISSING = "–"


def compare_runs(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Per-category pass rates (reviewed, then unreviewed), safety, latency, cost and spend for
    run A and run B, with B minus A. A category one run lacks shows as missing."""
    numbers_a, numbers_b = report_numbers(a["cases"]), report_numbers(b["cases"])
    lines = [
        f"A: {a.get('run_id')} ({a.get('model')})",
        f"B: {b.get('run_id')} ({b.get('model')})",
    ]
    cases_a, cases_b = _case_ids(a), _case_ids(b)
    if cases_a != cases_b:
        lines.append(
            f"warning: the runs cover different cases ({len(cases_a - cases_b)} only in A, "
            f"{len(cases_b - cases_a)} only in B), so their rates are not like for like"
        )
    lines += ["", "| | A | B | B − A |", "|---|---|---|---|"]
    lines += _score_rows(numbers_a, numbers_b)
    lines += [
        _row(label, a_value, b_value, formatter)
        for label, a_value, b_value, formatter in [
            ("latency p50", numbers_a.latency_p50, numbers_b.latency_p50, seconds),
            ("latency p95", numbers_a.latency_p95, numbers_b.latency_p95, seconds),
            ("cost p50", numbers_a.cost_p50, numbers_b.cost_p50, usd),
            ("cost p95", numbers_a.cost_p95, numbers_b.cost_p95, usd),
            ("answers sent back", numbers_a.sent_back, numbers_b.sent_back, count),
            ("run spend", a.get("run_spend_usd"), b.get("run_spend_usd"), usd),
        ]
    ]
    return "\n".join(lines)


def _case_ids(summary: dict[str, Any]) -> set[str]:
    return {result["case_id"] for result in summary["cases"]}


def _score_rows(a: ReportNumbers, b: ReportNumbers) -> list[str]:
    rows = []
    for suffix, scores_a, scores_b, safety_a, safety_b in [
        ("", a.headline, b.headline, a.safety, b.safety),
        (" (unreviewed)", a.unreviewed, b.unreviewed, a.unreviewed_safety, b.unreviewed_safety),
    ]:
        by_label_a = {s.label: s for s in scores_a}
        by_label_b = {s.label: s for s in scores_b}
        for label in sorted(by_label_a.keys() | by_label_b.keys()):
            rows.append(_score_row(label + suffix, by_label_a.get(label), by_label_b.get(label)))
        if safety_a.n or safety_b.n:
            rows.append(_score_row("safety" + suffix, safety_a, safety_b))
    return rows


def _score_row(label: str, a: Score | None, b: Score | None) -> str:
    rate_a = a.rate if a else None
    rate_b = b.rate if b else None
    difference = (
        f"{(rate_b - rate_a) * 100:+.0f} pts"
        if rate_a is not None and rate_b is not None
        else MISSING
    )
    return f"| {label} | {_score(a)} | {_score(b)} | {difference} |"


def _score(score: Score | None) -> str:
    if score is None or not score.n:
        return MISSING
    return f"{pct(score.rate)} ({score.passed:g}/{score.n})"


def _row(label: str, a: float | None, b: float | None, formatter: Callable[[Any], str]) -> str:
    difference = MISSING
    if a is not None and b is not None:
        sign = "+" if b >= a else "-"
        difference = sign + formatter(abs(b - a))
    return f"| {label} | {formatter(a)} | {formatter(b)} | {difference} |"
