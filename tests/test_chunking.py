import datetime as dt
import hashlib
import re

import pytest

from eval_harness.ingest import IngestError, check_article_sets, chunk_text
from eval_harness.manifest import Source

HEADING = re.compile(r"Article\s*[()]\s*(\d+)\s*[()]")
FOOTER = re.compile(r"The Statute of 2021|\d+")


def source(**overrides):
    fields = dict(
        id="statute-en",
        instrument="statute",
        language="en",
        official_url="https://official.example/en",
        wayback_url="https://web.archive.org/web/1id_/https://official.example/en",
        retrieved=dt.date(2026, 10, 17),
        sha256="0" * 64,
        indexed=True,
        heading_pattern=HEADING,
        drop_line_pattern=FOOTER,
    )
    return Source(**(fields | overrides))


TEXT = """The Statute of 2021
We, the President, have promulgated:

Article (1)
Definitions
Worker: a natural person.

Article )2 (
Scope
This applies to the private sector, see Article (1) for definitions.
The Statute of 2021

2

Article)3(
Leave
Article (1)
1.  Thirty   days a year.
"""


def test_articles_are_split_on_every_heading_style_and_the_preamble_is_dropped():
    chunks = chunk_text(TEXT, source())

    assert [c.article for c in chunks] == ["1", "2", "3"]
    assert chunks[0].text == "Article (1)\nDefinitions\nWorker: a natural person."


def test_page_furniture_lines_are_dropped_and_spaces_collapsed():
    chunks = chunk_text(TEXT, source())

    assert chunks[1].text == (
        "Article )2 (\nScope\nThis applies to the private sector, see Article (1) for definitions."
    )


def test_a_heading_line_that_goes_backwards_is_body_text():
    chunks = chunk_text(TEXT, source())

    assert chunks[2].text == "Article)3(\nLeave\nArticle (1)\n1. Thirty days a year."


def test_each_chunk_carries_instrument_article_part_language_and_text_hash():
    chunk = chunk_text(TEXT, source())[0]

    assert chunk.id == "statute:en:1:1"
    assert (chunk.instrument, chunk.article, chunk.part, chunk.language) == (
        "statute",
        "1",
        1,
        "en",
    )
    assert chunk.text_sha256 == hashlib.sha256(chunk.text.encode()).hexdigest()
    assert chunk.source == "statute-en"


def test_a_long_article_is_split_into_parts_at_clause_starts():
    clauses = "\n".join(f"{n}.  Clause {n} " + "word " * 30 for n in range(1, 7))
    text = f"Article (1)\nLong article\n{clauses}\n"

    chunks = chunk_text(text, source(), max_chars=400)

    assert [(c.article, c.part) for c in chunks] == [("1", 1), ("1", 2), ("1", 3)]
    assert [c.id for c in chunks] == ["statute:en:1:1", "statute:en:1:2", "statute:en:1:3"]
    assert chunks[0].text.startswith("Article (1)\nLong article\n1. Clause 1")
    assert chunks[1].text.startswith("3. Clause 3")
    assert all(len(c.text) <= 400 for c in chunks)
    assert "\n".join(c.text for c in chunks).count("Clause") == 6


def test_a_single_clause_longer_than_a_part_is_split_by_lines():
    lines = "\n".join("line " * 20 for _ in range(10))
    text = f"Article (1)\n1.  Start\n{lines}\n"

    chunks = chunk_text(text, source(), max_chars=300)

    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)


def test_a_skipped_article_number_stops_ingest():
    text = "Article (1)\nOne\nArticle (3)\nThree\n"

    with pytest.raises(IngestError, match="article 2"):
        chunk_text(text, source())


def test_text_without_any_heading_stops_ingest():
    with pytest.raises(IngestError, match="no article headings"):
        chunk_text("Just a preamble.\n", source())


def test_text_with_an_unmapped_glyph_stops_ingest():
    with pytest.raises(IngestError, match="2 unmapped glyph"):
        chunk_text("Article (1)\nA�B�\n", source())


def test_languages_of_one_instrument_with_different_articles_stop_ingest():
    english = chunk_text("Article (1)\nOne\nArticle (2)\nTwo\n", source())
    arabic = chunk_text("Article (1)\nواحد\n", source(id="statute-ar", language="ar"))

    with pytest.raises(
        IngestError, match=r"statute: article sets differ; missing \{'ar': \['2'\]\}"
    ):
        check_article_sets(english + arabic)


def test_languages_with_the_same_articles_pass_the_check():
    english = chunk_text("Article (1)\nOne\n", source())
    arabic = chunk_text("Article (1)\nواحد\n", source(id="statute-ar", language="ar"))

    check_article_sets(english + arabic)
