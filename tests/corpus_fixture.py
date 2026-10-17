"""A two-article corpus (manifest plus ingested chunks) for tests that run cases."""

import hashlib
from pathlib import Path

from eval_harness.ingest import Chunk, write_chunks

MANIFEST = """
[instruments.statute]
title = "The Statute"

[[sources]]
id = "statute-en"
instrument = "statute"
language = "en"
official_url = "https://official.example/en"
wayback_url = "https://web.archive.org/web/20260101000000id_/https://official.example/en"
retrieved = 2026-10-17
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
indexed = true
heading_pattern = 'Article \\((\\d+)\\)'
"""


def index_chunk(article, text):
    return Chunk(
        id=f"statute:en:{article}:1",
        instrument="statute",
        article=article,
        part=1,
        language="en",
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source="statute-en",
    )


INDEX = [
    index_chunk("9", "Article (9) Probation. Probation shall not exceed six months."),
    index_chunk("29", "Article (29) Annual leave of thirty days."),
]


def write_corpus(root: Path) -> None:
    """Write the manifest into `root/pack` and the chunks into the default index directory."""
    (root / "pack").mkdir(exist_ok=True)
    (root / "pack" / "manifest.toml").write_text(MANIFEST)
    write_chunks(INDEX, root / "data" / "index")
