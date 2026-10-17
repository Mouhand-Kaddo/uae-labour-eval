"""Cases: frozen test inputs with their expected result and scoring methods."""

import hashlib
import re
from collections.abc import Collection, Mapping
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
    planted_chunks: list[dict[str, Any]] | None = None


LANGUAGES = ("ar", "both", "en")
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
QUESTION_ID = re.compile(r"OQ-\d{3}")
QUESTION_HEADING = re.compile(r"^## (?=OQ-\d{3}:)", re.MULTILINE)
DECISION_LINE = re.compile(r"^\*\*Decision:\*\*\s*(.*)$", re.MULTILINE)

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
OPTIONAL_FIELD_TYPES: dict[str, type] = {"planted_chunks": list}

TYPE_NAMES = {str: "a string", dict: "a mapping", list: "a list", bool: "a boolean"}


def load_cases(
    directory: Path,
    scorer_names: Collection[str],
    open_questions: Mapping[str, bool] | None = None,
) -> list[Case]:
    """Load every case from the YAML files in `directory`; each file holds a list of cases.

    `open_questions` maps each recorded question ID to whether it is still open. Without it,
    no question counts as decided, so a reviewed case may not depend on any.
    """
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            entries = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise CaseError(f"{path.name}: invalid YAML: {exc}") from exc
        if not isinstance(entries, list):
            raise CaseError(f"{path.name}: expected a list of cases")
        for entry in entries:
            case = _parse_case(path.name, entry, scorer_names)
            _check_dependencies(f"{path.name}: case {case.id!r}", case, open_questions)
            cases.append(case)
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise CaseError(f"duplicate case id {case.id!r}")
        seen.add(case.id)
    return cases


def case_set_hash(directory: Path) -> str:
    """SHA-256 over the case files in name order, covering each file's name and bytes."""
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.yaml")):
        content = path.read_bytes()
        digest.update(f"{path.name}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def load_open_questions(path: Path) -> dict[str, bool]:
    """Read the open-questions doc: each `## OQ-NNN:` section maps to True while it is open.

    A question is decided once its section has a `**Decision:**` line that is not `_open_`.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseError(f"cannot read open questions {path}: {exc}") from exc
    questions: dict[str, bool] = {}
    for section in QUESTION_HEADING.split(text)[1:]:
        question, _, body = section.partition(":")
        decision = DECISION_LINE.search(body)
        questions[question] = decision is None or decision.group(1).startswith("_open_")
    return questions


def _check_dependencies(label: str, case: Case, open_questions: Mapping[str, bool] | None) -> None:
    if open_questions is not None:
        unrecorded = sorted(set(case.depends_on) - open_questions.keys())
        if unrecorded:
            raise CaseError(f"{label}: depends_on names unrecorded questions {unrecorded}")
    if case.reviewed:
        still_open = sorted(
            q for q in case.depends_on if open_questions is None or open_questions[q]
        )
        if still_open:
            raise CaseError(f"{label}: reviewed but depends on open questions {still_open}")


def _parse_case(filename: str, entry: Any, scorer_names: Collection[str]) -> Case:
    if not isinstance(entry, dict):
        raise CaseError(f"{filename}: each case must be a mapping")
    label = f"{filename}: case {entry.get('id', '?')!r}"
    missing = FIELD_TYPES.keys() - entry.keys()
    if missing:
        raise CaseError(f"{label}: missing fields {sorted(missing)}")
    unknown = entry.keys() - FIELD_TYPES.keys() - OPTIONAL_FIELD_TYPES.keys()
    if unknown:
        raise CaseError(f"{label}: unknown fields {sorted(unknown)}")
    for name, expected_type in (FIELD_TYPES | OPTIONAL_FIELD_TYPES).items():
        if name in entry and not isinstance(entry[name], expected_type):
            raise CaseError(f"{label}: field {name!r} must be {_type_name(expected_type)}")

    if not CASE_ID.fullmatch(entry["id"]):
        raise CaseError(f"{label}: id must be letters, digits, '-' or '_'")
    for name in ("category", "rationale"):
        if not entry[name].strip():
            raise CaseError(f"{label}: {name} must be a non-empty string")
    if entry["language"] not in LANGUAGES:
        raise CaseError(f"{label}: language must be one of {list(LANGUAGES)}")
    _check_input(label, entry["language"], entry["input"])
    _check_scoring(label, entry["scoring"], scorer_names)
    if not _non_empty_strings(entry["refs"]):
        raise CaseError(f"{label}: refs must be a list of non-empty strings")
    for question in entry["depends_on"]:
        if not (isinstance(question, str) and QUESTION_ID.fullmatch(question)):
            raise CaseError(
                f"{label}: depends_on entries must look like 'OQ-005', got {question!r}"
            )
    planted = entry.get("planted_chunks")
    if planted is not None and not (planted and all(isinstance(c, dict) for c in planted)):
        raise CaseError(f"{label}: planted_chunks must be a non-empty list of mappings")
    return Case(**entry)


def _type_name(expected_type: type | tuple[type, ...]) -> str:
    types = expected_type if isinstance(expected_type, tuple) else (expected_type,)
    return " or ".join(TYPE_NAMES[t] for t in types)


def _non_empty_strings(values: list[Any]) -> bool:
    return all(isinstance(value, str) and value.strip() for value in values)


def _check_scoring(label: str, scoring: list[Any], scorer_names: Collection[str]) -> None:
    if not scoring:
        raise CaseError(f"{label}: scoring must name at least one scorer")
    if not _non_empty_strings(scoring):
        raise CaseError(f"{label}: scoring must be a list of strings")
    unknown_scorers = set(scoring) - set(scorer_names)
    if unknown_scorers:
        raise CaseError(f"{label}: unknown scorers {sorted(unknown_scorers)}")


def _check_input(label: str, language: str, value: Any) -> None:
    if language == "both":
        if not (
            isinstance(value, dict)
            and value.keys() == {"en", "ar"}
            and all(isinstance(text, str) and text.strip() for text in value.values())
        ):
            raise CaseError(f"{label}: input must be a mapping with 'en' and 'ar' texts")
    elif not (isinstance(value, str) and value.strip()):
        raise CaseError(f"{label}: input must be a non-empty string for language {language!r}")
