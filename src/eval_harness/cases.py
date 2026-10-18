"""Cases: frozen test inputs with their expected result and scoring methods."""

import hashlib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

lazy import yaml

from eval_harness.ingest import Chunk


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
    planted_chunks: list[Chunk] | None = None

    @property
    def is_pair(self) -> bool:
        """A bilingual pair: the same question asked in each of PAIR_LANGUAGES."""
        return self.language == PAIR

    def inputs(self) -> dict[str, str]:
        """The questions to put to the agent, by language: one, or both halves of a pair."""
        if isinstance(self.input, str):
            return {self.language: self.input}
        return {language: self.input[language] for language in PAIR_LANGUAGES}

    def half(self, language: str) -> Case:
        """One language of a bilingual pair, as a single-language case with that language's
        input and expectations."""
        return replace(
            self,
            language=language,
            input=self.inputs()[language],
            expected=self.expected[language],
        )


PAIR = "both"
LANGUAGES = ("ar", PAIR, "en")
PAIR_LANGUAGES = ("en", "ar")
CONSISTENCY = "consistency"
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
QUESTION_ID = re.compile(r"OQ-\d{3}")
QUESTION_HEADING = re.compile(r"^## (?=OQ-\d{3}:)", re.MULTILINE)
DECISION_LINE = re.compile(r"^\*\*Decision:\*\*\s*(.*)$", re.MULTILINE)

FIELD_TYPES: frozendict[str, type | tuple[type, ...]] = frozendict(
    id=str,
    category=str,
    language=str,
    input=(str, dict),
    expected=dict,
    scoring=list,
    reviewed=bool,
    refs=list,
    depends_on=list,
    rationale=str,
)
OPTIONAL_FIELD_TYPES: frozendict[str, type] = frozendict(planted_chunks=list)
PLANTED_FIELDS = ("instrument", "article", "language", "text")
PLANTED_LANGUAGES = ("en", "ar")

TYPE_NAMES: frozendict[type, str] = frozendict(
    {
        str: "a string",
        dict: "a mapping",
        list: "a list",
        bool: "a boolean",
    }
)


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
    _check_pair(label, entry)
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
    if planted is not None:
        entry = entry | {
            "planted_chunks": [
                _planted_chunk(f"{label}: planted chunk {n}", entry["id"], fields)
                for n, fields in enumerate(planted, start=1)
            ]
        }
    return Case(**entry)


def _planted_chunk(label: str, case_id: str, fields: dict[str, Any]) -> Chunk:
    """A planted chunk, shaped and identified like a corpus chunk so the agent cannot tell it
    apart; only its `source` marks it as planted for this case."""
    missing = sorted(set(PLANTED_FIELDS) - fields.keys())
    if missing:
        raise CaseError(f"{label}: missing {missing}")
    unknown = sorted(fields.keys() - set(PLANTED_FIELDS))
    if unknown:
        raise CaseError(f"{label}: unknown {unknown}")
    for name in PLANTED_FIELDS:
        if not (isinstance(fields[name], str) and fields[name].strip()):
            raise CaseError(f"{label}: {name!r} must be a non-empty string")
    if fields["language"] not in PLANTED_LANGUAGES:
        raise CaseError(f"{label}: language must be 'en' or 'ar'")
    instrument, article, language, text = (fields[name] for name in PLANTED_FIELDS)
    return Chunk(
        id=f"{instrument}:{language}:{article}:1",
        instrument=instrument,
        article=article,
        part=1,
        language=language,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source=f"planted:{case_id}",
    )


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


def _check_pair(label: str, entry: dict[str, Any]) -> None:
    if entry["language"] != PAIR:
        if CONSISTENCY in entry["scoring"]:
            raise CaseError(f"{label}: {CONSISTENCY!r} compares the halves of a bilingual pair")
        return
    expected = entry["expected"]
    if not (
        expected.keys() == set(PAIR_LANGUAGES)
        and all(isinstance(expected[language], dict) for language in PAIR_LANGUAGES)
    ):
        raise CaseError(f"{label}: expected must be a mapping with 'en' and 'ar' expectations")
    if CONSISTENCY not in entry["scoring"]:
        raise CaseError(f"{label}: a bilingual pair must be scored on {CONSISTENCY!r}")


def _check_input(label: str, language: str, value: Any) -> None:
    if language == PAIR:
        if not (
            isinstance(value, dict)
            and value.keys() == set(PAIR_LANGUAGES)
            and all(isinstance(text, str) and text.strip() for text in value.values())
        ):
            raise CaseError(f"{label}: input must be a mapping with 'en' and 'ar' texts")
    elif not (isinstance(value, str) and value.strip()):
        raise CaseError(f"{label}: input must be a non-empty string for language {language!r}")
