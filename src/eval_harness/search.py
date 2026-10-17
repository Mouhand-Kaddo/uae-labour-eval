"""BM25 search over the ingested chunks, and the `search_sources` and `get_section` tools."""

import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import bm25s
import numpy as np

from eval_harness.agent import Tool
from eval_harness.ingest import Chunk, read_chunks

TOP_K = 8
TOKEN = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


class SearchIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._bm25 = bm25s.BM25()
        self._bm25.index([tokenize(c.text) for c in chunks], show_progress=False)

    @classmethod
    def load(cls, index_dir: Path) -> "SearchIndex":
        return cls(read_chunks(index_dir))

    def search(self, query: str, k: int = TOP_K) -> list[Chunk]:
        """The k best chunks by BM25 score; chunks sharing no term with the query are left out."""
        scores = self._bm25.get_scores(tokenize(query))
        ranked = np.argsort(-scores, kind="stable")[:k]
        return [self.chunks[i] for i in ranked if scores[i] > 0]

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
) -> list[Tool]:
    """The retrieval tools; every chunk they return is reported to `on_retrieve` first."""
    citable = ", ".join(f'"{key}" ({title})' for key, title in instruments.items())
    cite_hint = f" Cite results by instrument ID and article number. Instruments: {citable}."

    def retrieved(tool: str, chunks: list[Chunk]) -> list[dict[str, Any]]:
        on_retrieve(tool, chunks)
        return [_tool_view(c) for c in chunks]

    def search_sources(args: dict[str, Any]) -> list[dict[str, Any]]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        return retrieved("search_sources", index.search(query, TOP_K))

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
