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


def score_citations(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Pass when every required article is cited and every cited article was retrieved
    during this case (ADR-0007). Articles are compared at article level, not clause level."""
    required = {_article_key(c["instrument"], c["article"]) for c in case.expected["citations"]}
    cited = {_article_key(c.instrument, c.article) for c in final.citations}
    retrieved = {
        _article_key(chunk["instrument"], chunk["article"])
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


def _article_key(instrument: str, article: str) -> str:
    number = ARTICLE_NUMBER.search(str(article))
    return f"{instrument.strip().casefold()} {number.group() if number else str(article).strip()}"


SCORERS: dict[str, Callable[[Case, FinalAnswer, Trace], Verdict]] = {
    "status": score_status,
    "citations": score_citations,
}


def score_case(case: Case, final: FinalAnswer, trace: Trace) -> Verdict:
    """Run every scorer the case names; the case passes only if all of them pass."""
    verdicts = {name: SCORERS[name](case, final, trace) for name in case.scoring}
    return Verdict(
        all(v.passed for v in verdicts.values()),
        {name: {"passed": v.passed, **v.details} for name, v in verdicts.items()},
    )
