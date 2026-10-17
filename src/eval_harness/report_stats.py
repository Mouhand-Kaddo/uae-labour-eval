"""The numbers behind the report, computed from a run's case results. No HTML here."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

Z_95 = 1.959964


def wilson_interval(passed: float, n: int, z: float = Z_95) -> tuple[float, float] | None:
    """Wilson score interval for `passed` out of `n`; None when n is 0."""
    if n == 0:
        return None
    p = passed / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0-100); None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class Score:
    """A pass rate over n distinct cases.

    `passed` sums each case's share of passing repeats, so the rate is the mean case score
    and repeats never inflate n.
    """

    label: str
    passed: float
    n: int

    @property
    def rate(self) -> float | None:
        return self.passed / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson_interval(self.passed, self.n)


@dataclass(frozen=True)
class ReportNumbers:
    headline: list[Score]
    headline_average: float | None
    safety: Score
    unreviewed: list[Score]
    latency_p50: float | None
    latency_p95: float | None
    cost_p50: float | None
    cost_p95: float | None
    failures: list[dict[str, Any]]
    flaky: list["Flaky"]


@dataclass(frozen=True)
class Flaky:
    case_id: str
    category: str
    passed: int
    runs: int


SAFETY_CATEGORIES = ("refuse", "inject")


def report_numbers(results: list[dict[str, Any]]) -> ReportNumbers:
    """Summarise a run's case results (summary.json `cases`) for the report."""
    reviewed = _case_scores(r for r in results if r["reviewed"])
    headline = _scores_by_category(reviewed)
    rates = [s.rate for s in headline if s.rate is not None]
    safety = [score for category, score in reviewed if category in SAFETY_CATEGORIES]
    latencies = [r["latency_s"] for r in results]
    costs = [r["cost_usd"] for r in results]
    return ReportNumbers(
        headline=headline,
        headline_average=sum(rates) / len(rates) if rates else None,
        safety=Score("safety", sum(safety), len(safety)),
        unreviewed=_scores_by_category(_case_scores(r for r in results if not r["reviewed"])),
        latency_p50=percentile(latencies, 50),
        latency_p95=percentile(latencies, 95),
        cost_p50=percentile(costs, 50),
        cost_p95=percentile(costs, 95),
        failures=sorted((r for r in results if not r["passed"]), key=_failure_rank),
        flaky=_flaky(results),
    )


def _failure_rank(result: dict[str, Any]) -> tuple[int, bool]:
    if result["category"] in SAFETY_CATEGORIES:
        group = 0
    elif result["category"] == "calc":
        group = 1
    else:
        group = 2
    return group, not result["reviewed"]


def _flaky(results: list[dict[str, Any]]) -> list[Flaky]:
    flaky = []
    for case_id, runs in _runs_by_case(results).items():
        passed = sum(bool(r["passed"]) for r in runs)
        if 0 < passed < len(runs):
            flaky.append(Flaky(case_id, runs[0]["category"], passed, len(runs)))
    return flaky


def _runs_by_case(results: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_case.setdefault(r["case_id"], []).append(r)
    return by_case


def _case_scores(results: Iterable[dict[str, Any]]) -> list[tuple[str, float]]:
    """(category, share of the case's repeats that passed) for each distinct case."""
    return [
        (runs[0]["category"], sum(bool(r["passed"]) for r in runs) / len(runs))
        for runs in _runs_by_case(results).values()
    ]


def _scores_by_category(case_scores: list[tuple[str, float]]) -> list[Score]:
    by_category: dict[str, list[float]] = {}
    for category, score in case_scores:
        by_category.setdefault(category, []).append(score)
    return [
        Score(category, sum(by_category[category]), len(by_category[category]))
        for category in sorted(by_category)
    ]
