"""Scorers: (case, final answer, trace) -> verdict. A case passes only if all its scorers pass."""

import re
from collections.abc import Callable, Mapping
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


def score_citations(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when every required article is cited and every cited article was retrieved
    during this case (ADR-0007). Articles are compared at article level, not clause level."""
    required = {article_key(c["instrument"], c["article"]) for c in case.expected["citations"]}
    cited = {article_key(c.instrument, c.article) for c in final.citations}
    retrieved = {
        article_key(chunk["instrument"], chunk["article"])
        for step in trace
        if step["type"] == "retrieval"
        for chunk in step["chunks"]
    }
    missing = sorted(required - cited)
    not_retrieved = sorted(cited - retrieved)
    return Verdict(
        not missing and not not_retrieved,
        {
            "cited": sorted(cited),
            "missing": missing,
            "not_retrieved": not_retrieved,
        },
    )


ARTICLE_NUMBER = re.compile(r"\d+")


def article_key(instrument: str, article: str) -> str:
    number = ARTICLE_NUMBER.search(str(article))
    return f"{instrument.strip().casefold()} {number.group() if number else str(article).strip()}"


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


def score_answer_language(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when most letters of the answer are in the case's script (Arabic or Latin)."""
    arabic = sum(1 for c in final.answer if c.isalpha() and "\u0600" <= c <= "\u06ff")
    latin = sum(1 for c in final.answer if c.isascii() and c.isalpha())
    detected = "ar" if arabic > latin else "en" if latin > arabic else None
    return Verdict(
        detected == case.language,
        {"expected": case.language, "detected": detected, "arabic": arabic, "latin": latin},
    )


Scorer = Callable[[Case, FinalAnswer, Trace], Verdict]

SCORERS: dict[str, Scorer] = {
    "status": score_status,
    "citations": score_citations,
    "numeric": score_numeric,
    "tool_call": score_tool_call,
    "answer_language": score_answer_language,
}


def score_case(
    case: Case, final: FinalAnswer, trace: Trace, scorers: Mapping[str, Scorer] = SCORERS
) -> Verdict:
    """Run every scorer the case names; the case passes only if all of them pass."""
    verdicts = {name: scorers[name](case, final, trace) for name in case.scoring}
    return Verdict(
        all(v.passed for v in verdicts.values()),
        {name: {"passed": v.passed, **v.details} for name, v in verdicts.items()},
    )
