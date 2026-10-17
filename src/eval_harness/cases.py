"""Cases: frozen test inputs with their expected result and scoring methods."""

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class CaseError(Exception):
    pass


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


FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "category": str,
    "language": str,
    "input": (str, dict),
    "expected": dict,
    "scoring": list,
    "reviewed": bool,
    "refs": list,
    "depends_on": list,
    "rationale": str,
}


def load_cases(directory: Path, scorer_names: Collection[str]) -> list[Case]:
    """Load every case from the YAML files in `directory`; each file holds a list of cases."""
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            entries = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise CaseError(f"{path.name}: invalid YAML: {exc}") from exc
        if not isinstance(entries, list):
            raise CaseError(f"{path.name}: expected a list of cases")
        cases.extend(_parse_case(path.name, entry, scorer_names) for entry in entries)
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise CaseError(f"duplicate case id {case.id!r}")
        seen.add(case.id)
    return cases


def _parse_case(filename: str, entry: Any, scorer_names: Collection[str]) -> Case:
    if not isinstance(entry, dict):
        raise CaseError(f"{filename}: each case must be a mapping")
    label = f"{filename}: case {entry.get('id', '?')!r}"
    missing = FIELD_TYPES.keys() - entry.keys()
    if missing:
        raise CaseError(f"{label}: missing fields {sorted(missing)}")
    unknown = entry.keys() - FIELD_TYPES.keys()
    if unknown:
        raise CaseError(f"{label}: unknown fields {sorted(unknown)}")
    for name, expected_type in FIELD_TYPES.items():
        if not isinstance(entry[name], expected_type):
            raise CaseError(f"{label}: field {name!r} has the wrong type")
    if not entry["scoring"]:
        raise CaseError(f"{label}: scoring must name at least one scorer")
    unknown_scorers = set(entry["scoring"]) - set(scorer_names)
    if unknown_scorers:
        raise CaseError(f"{label}: unknown scorers {sorted(unknown_scorers)}")
    return Case(**entry)
