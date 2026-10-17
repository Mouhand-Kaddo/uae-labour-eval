"""References from calculation rules to the legal text they apply (ADR-0010)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    instrument: str
    article: str
    clause: str | None = None

    def __str__(self) -> str:
        clause = f"({self.clause})" if self.clause else ""
        return f"{self.instrument} Art {self.article}{clause}"
