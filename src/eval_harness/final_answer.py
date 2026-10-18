"""The structured final answer every case ends with (ADR-0007)."""

from dataclasses import dataclass, field
from typing import Any

STATUSES = ("answered", "refused", "not_found")
REFUSAL_REASONS = ("legal_advice", "out_of_scope")
LIMIT = "limit"


@dataclass(frozen=True)
class Citation:
    instrument: str
    article: str


@dataclass(frozen=True)
class FinalAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    status: str = "answered"
    refusal_reason: str | None = None

    @classmethod
    def limit(cls) -> FinalAnswer:
        """The runner-assigned answer for a case that hit a turn or token cap."""
        return cls(answer="", status=LIMIT)


FINAL_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "final_answer",
        "description": (
            "Finish the case. Call exactly once, as your last action, with the answer in the "
            "language of the question and every article it relies on."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "instrument": {"type": "string"},
                            "article": {"type": "string"},
                        },
                        "required": ["instrument", "article"],
                        "additionalProperties": False,
                    },
                },
                "status": {"type": "string", "enum": list(STATUSES)},
                "refusal_reason": {"type": ["string", "null"], "enum": [*REFUSAL_REASONS, None]},
            },
            "required": ["answer", "citations", "status", "refusal_reason"],
            "additionalProperties": False,
        },
    },
}


def parse_final_answer(arguments: Any) -> FinalAnswer:
    """Validate `final_answer` tool arguments; raises ValueError naming the first problem."""
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    answer = arguments.get("answer")
    if not isinstance(answer, str):
        raise ValueError("answer must be a string")
    status = arguments.get("status")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {list(STATUSES)}")
    reason = arguments.get("refusal_reason")
    if status == "refused" and reason not in REFUSAL_REASONS:
        raise ValueError(f"a refusal needs refusal_reason in {list(REFUSAL_REASONS)}")
    if status != "refused" and reason is not None:
        raise ValueError("refusal_reason must be null unless status is refused")
    raw_citations = arguments.get("citations", [])
    if not isinstance(raw_citations, list):
        raise ValueError("citations must be a list")
    citations = []
    for c in raw_citations:
        if not (
            isinstance(c, dict)
            and isinstance(c.get("instrument"), str)
            and isinstance(c.get("article"), str | int)
        ):
            raise ValueError("each citation needs an instrument and an article")
        citations.append(Citation(c["instrument"], str(c["article"])))
    return FinalAnswer(answer, citations, status, reason)
