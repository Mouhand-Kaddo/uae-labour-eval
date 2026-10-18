"""Ingest: source PDF -> text -> articles (by the source's heading pattern) -> chunks."""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

lazy from pdfminer.high_level import extract_text

from eval_harness.fetch import source_path, verified
from eval_harness.manifest import Manifest, Source
lazy from eval_harness.pdf_text import REPLACEMENT, pdf_text

MAX_PART_CHARS = 1500
CLAUSE_START = re.compile(r"\d+\.\s")
CHUNKS_FILE = "chunks.jsonl"
RIGHT_TO_LEFT_LANGUAGES = {"ar"}
TATWEEL = "\u0640"


class IngestError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    id: str
    instrument: str
    article: str
    part: int
    language: str
    text: str
    text_sha256: str
    source: str


def chunk_text(text: str, source: Source, *, max_chars: int = MAX_PART_CHARS) -> list[Chunk]:
    """Split one source's text into article chunks; long articles become several parts.

    Raises IngestError if the text still holds U+FFFD (a glyph with no known letters).
    """
    if REPLACEMENT in text:
        raise IngestError(
            f"{source.id}: {text.count(REPLACEMENT)} unmapped glyph(s) (U+FFFD) in the text; "
            "add them to the source's glyph table"
        )
    chunks = []
    for article, lines in _split_articles(_clean_lines(text, source), source):
        for part, part_text in enumerate(_parts(lines, max_chars), start=1):
            chunks.append(
                Chunk(
                    id=f"{source.instrument}:{source.language}:{article}:{part}",
                    instrument=source.instrument,
                    article=article,
                    part=part,
                    language=source.language,
                    text=part_text,
                    text_sha256=hashlib.sha256(part_text.encode("utf-8")).hexdigest(),
                    source=source.id,
                )
            )
    return chunks


def _clean_lines(text: str, source: Source) -> list[str]:
    lines = (" ".join(line.split()) for line in text.splitlines())
    drop = source.drop_line_pattern
    return [line for line in lines if line and not (drop and drop.fullmatch(line))]


def _split_articles(lines: list[str], source: Source) -> list[tuple[str, list[str]]]:
    if source.heading_pattern is None:
        raise IngestError(f"{source.id}: no heading_pattern in the manifest")
    articles: list[tuple[str, list[str]]] = []
    for line in lines:
        match = source.heading_pattern.fullmatch(line)
        number = int(match.group(1)) if match else None
        expected = len(articles) + 1
        if number == expected:
            articles.append((str(number), [line]))
        elif number is not None and number > expected:
            raise IngestError(
                f"{source.id}: heading for article {expected} not found before {line!r}"
            )
        elif articles:
            articles[-1][1].append(line)
    if not articles:
        raise IngestError(f"{source.id}: no article headings match the heading pattern")
    return articles


def _parts(lines: list[str], max_chars: int) -> list[str]:
    blocks: list[list[str]] = [[]]
    for line in lines:
        if CLAUSE_START.match(line) and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    units: list[str] = []
    for block in blocks:
        joined = "\n".join(block)
        units.extend([joined] if len(joined) <= max_chars else block)

    parts: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + 1 + len(unit) > max_chars:
            parts.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
    parts.append(current)
    return parts


def extract_pdf_text(path: Path) -> str:
    return extract_text(path)


def source_text(path: Path, source: Source) -> str:
    """A source's text; right-to-left languages are rebuilt glyph by glyph (ADR-0004), with
    presentation forms folded to plain letters (NFKC) and justification tatweel removed."""
    if source.language in RIGHT_TO_LEFT_LANGUAGES:
        text = unicodedata.normalize("NFKC", pdf_text(path, source.glyphs))
        return text.replace(TATWEEL, "")
    return extract_pdf_text(path)


def check_article_sets(chunks: list[Chunk]) -> None:
    """Raise IngestError unless every language of an instrument has the same articles."""
    articles: dict[str, dict[str, set[str]]] = {}
    for chunk in chunks:
        articles.setdefault(chunk.instrument, {}).setdefault(chunk.language, set()).add(
            chunk.article
        )
    for instrument, by_language in articles.items():
        union = set().union(*by_language.values())
        differences = {
            language: sorted(union - found, key=int)
            for language, found in sorted(by_language.items())
            if union - found
        }
        if differences:
            raise IngestError(f"{instrument}: article sets differ; missing {differences}")


def ingest(manifest: Manifest, sources_dir: Path, index_dir: Path) -> list[Chunk]:
    """Chunk every indexed source and write them to the index directory."""
    chunks: list[Chunk] = []
    for source in manifest.indexed_sources:
        path = source_path(sources_dir, source)
        if not verified(path, source):
            raise IngestError(f"{source.id}: {path} is missing or fails its hash; run fetch")
        chunks.extend(chunk_text(source_text(path, source), source))
    check_article_sets(chunks)
    write_chunks(chunks, index_dir)
    return chunks


def write_chunks(chunks: list[Chunk], index_dir: Path) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks)
    (index_dir / CHUNKS_FILE).write_text("".join(lines), encoding="utf-8")


def read_chunks(index_dir: Path) -> list[Chunk]:
    """Read the chunks ingest wrote; raises IngestError if they are missing or malformed."""
    path = index_dir / CHUNKS_FILE
    try:
        return [Chunk(**json.loads(line)) for line in path.read_text("utf-8").splitlines()]
    except FileNotFoundError as exc:
        raise IngestError(f"{path} not found; run fetch and ingest first") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise IngestError(f"{path} is unreadable: {exc}") from exc
