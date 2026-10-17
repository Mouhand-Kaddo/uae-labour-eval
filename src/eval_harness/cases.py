"""Cases: frozen test inputs with their expected result and scoring methods."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    language: str
    input: str | dict[str, str]
    expected: dict[str, Any]
    scoring: list[str]
    reviewed: bool
    refs: list[str]
    depends_on: list[str]
    rationale: str
