"""The corpus manifest: every source a corpus is built from, and how to ingest it (ADR-0005)."""

import datetime as dt
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Source:
    id: str
    instrument: str
    language: str
    official_url: str
    wayback_url: str
    retrieved: dt.date
    sha256: str
    indexed: bool
    heading_pattern: re.Pattern[str] | None = None
    drop_line_pattern: re.Pattern[str] | None = None
    glyphs: dict[tuple[str, int], str] = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    instruments: dict[str, str]
    sources: list[Source]
    sha256: str

    @property
    def indexed_sources(self) -> list[Source]:
        return [s for s in self.sources if s.indexed]


REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "instrument": str,
    "language": str,
    "official_url": str,
    "wayback_url": str,
    "retrieved": dt.date,
    "sha256": str,
    "indexed": bool,
}
PATTERN_FIELDS = ("heading_pattern", "drop_line_pattern")
SHA256 = re.compile(r"[0-9a-f]{64}")


def manifest_path(pack: Path) -> Path:
    return pack / "manifest.toml"


def load_manifest(pack: Path) -> Manifest:
    """Read and validate `<pack>/manifest.toml`; raises ManifestError naming the problem."""
    path = manifest_path(pack)
    try:
        data = path.read_bytes()
        raw = tomllib.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    instruments = {
        key: value.get("title", key) if isinstance(value, dict) else key
        for key, value in raw.get("instruments", {}).items()
    }
    sources = [_parse_source(entry, instruments) for entry in raw.get("sources", [])]
    if not sources:
        raise ManifestError(f"{path}: no sources")
    ids = [s.id for s in sources]
    if len(set(ids)) != len(ids):
        raise ManifestError(f"{path}: duplicate source ids")
    return Manifest(instruments, sources, hashlib.sha256(data).hexdigest())


def _parse_source(entry: object, instruments: dict[str, str]) -> Source:
    if not isinstance(entry, dict):
        raise ManifestError("each source must be a table")
    label = f"source {entry.get('id', '?')!r}"
    missing = REQUIRED_FIELDS.keys() - entry.keys()
    if missing:
        raise ManifestError(f"{label}: missing fields {sorted(missing)}")
    unknown = entry.keys() - REQUIRED_FIELDS.keys() - set(PATTERN_FIELDS) - {"glyphs"}
    if unknown:
        raise ManifestError(f"{label}: unknown fields {sorted(unknown)}")
    for name, expected_type in REQUIRED_FIELDS.items():
        if not isinstance(entry[name], expected_type):
            raise ManifestError(f"{label}: field {name!r} has the wrong type")
    if entry["instrument"] not in instruments:
        raise ManifestError(f"{label}: instrument {entry['instrument']!r} is not declared")
    if not SHA256.fullmatch(entry["sha256"]):
        raise ManifestError(f"{label}: sha256 must be 64 lowercase hex characters")
    patterns = {name: _compile(label, name, entry.get(name)) for name in PATTERN_FIELDS}
    if entry["indexed"] and patterns["heading_pattern"] is None:
        raise ManifestError(f"{label}: an indexed source needs a heading_pattern")
    glyphs = _glyph_table(label, entry.get("glyphs", {}))
    return Source(**{name: entry[name] for name in REQUIRED_FIELDS}, **patterns, glyphs=glyphs)


def _glyph_table(label: str, raw: object) -> dict[tuple[str, int], str]:
    """`{font name: {glyph ID: text}}` from the manifest, keyed by (font name, glyph ID)."""
    problem = f"{label}: glyphs must map font names to tables of glyph ID = text"
    if not isinstance(raw, dict):
        raise ManifestError(problem)
    table = {}
    for font, glyphs in raw.items():
        if not isinstance(glyphs, dict):
            raise ManifestError(problem)
        for glyph_id, text in glyphs.items():
            if not (glyph_id.isascii() and glyph_id.isdigit()) or not isinstance(text, str):
                raise ManifestError(f"{problem}; bad entry {font!r} {glyph_id!r}")
            table[(font, int(glyph_id))] = text
    return table


def _compile(label: str, name: str, pattern: object) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    if not isinstance(pattern, str):
        raise ManifestError(f"{label}: {name} must be a string")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ManifestError(f"{label}: {name} is not a valid regex: {exc}") from exc
    if name == "heading_pattern" and compiled.groups != 1:
        raise ManifestError(f"{label}: heading_pattern must capture the article number once")
    return compiled
