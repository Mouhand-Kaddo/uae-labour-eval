"""Scorers: (case, final answer, trace) -> verdict. A case passes only if all its scorers pass."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from eval_harness.cases import Case
from eval_harness.final_answer import FinalAnswer

Trace = list[dict[str, Any]]


@dataclass(frozen=True)
class Verdict:
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def score_status(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when the final status, and the refusal reason if one is expected, match the case."""
    expected = {"status": case.expected["status"]}
    actual = {"status": final.status}
    if "refusal_reason" in case.expected:
        expected["refusal_reason"] = case.expected["refusal_reason"]
        actual["refusal_reason"] = final.refusal_reason
    return Verdict(expected == actual, {"expected": expected, "actual": actual})


SCORERS: dict[str, Callable[[Case, FinalAnswer, Trace], Verdict]] = {
    "status": score_status,
}


def score_case(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Run every scorer the case names; the case passes only if all of them pass."""
    verdicts = {name: SCORERS[name](case, final, trace) for name in case.scoring}
    return Verdict(
        all(v.passed for v in verdicts.values()),
        {name: {"passed": v.passed, **v.details} for name, v in verdicts.items()},
    )
