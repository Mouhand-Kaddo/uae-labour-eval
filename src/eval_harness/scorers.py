"""Scorers: (case, final answer, trace) -> verdict. A case passes only if all its scorers pass."""

import re
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


NUMBER = re.compile(r"\d+(?:[,٬]\d{3})*(?:[.٫]\d+)?")
FLOAT_NOISE = 1e-9


def numbers_in(text: str) -> list[float]:
    """Numbers written in Western or Arabic-Indic digits, with or without thousands separators."""
    return [
        float(match.translate(str.maketrans({",": None, "٬": None, "٫": "."})))
        for match in NUMBER.findall(text)
    ]


def score_numeric(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when every expected number appears in the answer text, within the case's tolerance."""
    tolerance = case.expected.get("tolerance", 0)
    found = numbers_in(final.answer)
    missing = [
        number
        for number in case.expected["numbers"]
        if not any(abs(number - f) <= tolerance + FLOAT_NOISE for f in found)
    ]
    return Verdict(
        final.status == "answered" and not missing,
        {"missing": missing, "found": found, "tolerance": tolerance},
    )


def score_tool_call(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when the named tool was called at least once with every expected argument value."""
    name = case.expected["tool_call"]["name"]
    expected_arguments = case.expected["tool_call"]["arguments"]
    calls = [
        step.get("arguments")
        for step in trace
        if step["type"] == "tool_call" and step["name"] == name
    ]
    passed = any(
        isinstance(arguments, dict)
        and all(
            key in arguments and _same(value, arguments[key])
            for key, value in expected_arguments.items()
        )
        for arguments in calls
    )
    return Verdict(passed, {"name": name, "expected": expected_arguments, "calls": calls})


def _same(expected: Any, actual: Any) -> bool:
    if _is_number(expected) and _is_number(actual):
        return abs(expected - actual) <= FLOAT_NOISE
    return expected == actual


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


SCORERS: dict[str, Callable[[Case, FinalAnswer, Trace], Verdict]] = {
    "status": score_status,
    "numeric": score_numeric,
    "tool_call": score_tool_call,
}


def score_case(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Run every scorer the case names; the case passes only if all of them pass."""
    verdicts = {name: SCORERS[name](case, final, trace) for name in case.scoring}
    return Verdict(
        all(v.passed for v in verdicts.values()),
        {name: {"passed": v.passed, **v.details} for name, v in verdicts.items()},
    )
