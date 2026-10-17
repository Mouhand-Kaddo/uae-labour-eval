"""The structured final answer every case ends with (ADR-0007)."""

from dataclasses import dataclass, field

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
    def limit(cls) -> "FinalAnswer":
        """The runner-assigned answer for a case that hit a turn or token cap."""
        return cls(answer="", status=LIMIT)
