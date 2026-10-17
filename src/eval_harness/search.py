"""Hybrid search over the chunks (ADR-0003), and the `search_sources` and `get_section` tools."""

import re
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import bm25s
import numpy as np

from eval_harness.agent import Tool
from eval_harness.embeddings import cached_vectors
from eval_harness.ingest import Chunk, IngestError, read_chunks

TOP_K = 8
RRF_K = 60
TOKEN = re.compile(r"\w+")
ARABIC_DIACRITICS_AND_TATWEEL = re.compile("[ـً-ٰٟ]")
ARABIC_LETTER_VARIANTS = str.maketrans("أإآٱىة", "اااايه")


def tokenize(text: str) -> list[str]:
    """Search terms, the same for chunks and queries: casefolded, with Arabic normalised."""
    return TOKEN.findall(normalize_arabic(text.casefold()))


def normalize_arabic(text: str) -> str:
    """Strip diacritics and tatweel, unify alef forms, ى→ي and ة→ه (ADR-0003)."""
    return ARABIC_DIACRITICS_AND_TATWEEL.sub("", text).translate(ARABIC_LETTER_VARIANTS)


class SearchIndex:
    def __init__(self, chunks: list[Chunk], vectors: Sequence[Sequence[float]]):
        if len(vectors) != len(chunks):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} embedding vectors")
        self.chunks = chunks
        self._bm25 = bm25s.BM25()
        self._bm25.index([tokenize(c.text) for c in chunks], show_progress=False)
        self._unit_vectors = _unit_rows(np.asarray(vectors, dtype=float))

    @classmethod
    def load(cls, index_dir: Path, embedding_model: str) -> "SearchIndex":
        """The ingested chunks with their cached vectors; IngestError if any vector is missing."""
        chunks = read_chunks(index_dir)
        vectors = cached_vectors(index_dir, embedding_model)
        missing = [c.id for c in chunks if c.text_sha256 not in vectors]
        if missing:
            raise IngestError(
                f"{len(missing)} chunk(s) have no {embedding_model} embedding "
                f"(first: {missing[0]}); run embed first"
            )
        return cls(chunks, [vectors[c.text_sha256] for c in chunks])

    def search(self, query: str, query_vector: Sequence[float], k: int = TOP_K) -> list[Chunk]:
        """The k best chunks by reciprocal rank fusion of BM25 and embedding similarity.

        Chunks that share no term with the query and whose embedding is not similar to it
        (cosine <= 0) are left out.
        """
        keyword_scores = self._bm25.get_scores(tokenize(query))
        similarities = self._unit_vectors @ _unit_rows(np.asarray([query_vector], dtype=float))[0]
        fused = np.zeros(len(self.chunks))
        for scores in (keyword_scores, similarities):
            ranked = [i for i in np.argsort(-scores, kind="stable") if scores[i] > 0]
            for rank, i in enumerate(ranked, start=1):
                fused[i] += 1 / (RRF_K + rank)
        best = np.argsort(-fused, kind="stable")[:k]
        return [self.chunks[i] for i in best if fused[i] > 0]

    def section(self, instrument: str, article: str, language: str) -> list[Chunk]:
        """Every part of one article in one language, in part order."""
        parts = [
            c
            for c in self.chunks
            if (c.instrument, c.article, c.language) == (instrument, article, language)
        ]
        return sorted(parts, key=lambda c: c.part)

    @property
    def languages(self) -> list[str]:
        return sorted({c.language for c in self.chunks})


def search_tools(
    index: SearchIndex,
    instruments: dict[str, str],
    on_retrieve: Callable[[str, list[Chunk]], None],
    embed_query: Callable[[str], Sequence[float]],
) -> list[Tool]:
    """The retrieval tools; every chunk they return is reported to `on_retrieve` first.

    `embed_query` turns a search query into its embedding vector.
    """
    citable = ", ".join(f'"{key}" ({title})' for key, title in instruments.items())
    cite_hint = f" Cite results by instrument ID and article number. Instruments: {citable}."

    def retrieved(tool: str, chunks: list[Chunk]) -> list[dict[str, Any]]:
        on_retrieve(tool, chunks)
        return [_tool_view(c) for c in chunks]

    def search_sources(args: dict[str, Any]) -> list[dict[str, Any]]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        return retrieved("search_sources", index.search(query, embed_query(query), TOP_K))

    def get_section(args: dict[str, Any]) -> list[dict[str, Any]]:
        instrument, article, language = (args.get(k) for k in ("instrument", "article", "language"))
        if instrument not in instruments:
            raise ValueError(f"unknown instrument {instrument!r}; use one of {list(instruments)}")
        if not isinstance(article, str | int) or not str(article).strip():
            raise ValueError("article must be an article number such as '51'")
        if language not in index.languages:
            raise ValueError(f"language must be one of {index.languages}")
        parts = index.section(instrument, str(article).strip(), language)
        if not parts:
            raise ValueError(
                f"article {article} of {instrument} in {language} is not in the corpus"
            )
        return retrieved("get_section", parts)

    return [
        Tool(
            name="search_sources",
            description=f"Search the corpus and return the {TOP_K} best chunks.{cite_hint}",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            run=search_sources,
        ),
        Tool(
            name="get_section",
            description=f"Return the full text of one article in one language.{cite_hint}",
            parameters={
                "type": "object",
                "properties": {
                    "instrument": {"type": "string", "enum": list(instruments)},
                    "article": {"type": "string"},
                    "language": {"type": "string", "enum": index.languages},
                },
                "required": ["instrument", "article", "language"],
                "additionalProperties": False,
            },
            run=get_section,
        ),
    ]


def _tool_view(chunk: Chunk) -> dict[str, Any]:
    view = asdict(chunk)
    del view["text_sha256"], view["source"]
    return view


def _unit_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)
