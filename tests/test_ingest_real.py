from pathlib import Path

import pytest

from eval_harness.config import load_config
from eval_harness.fetch import source_path, verified
from eval_harness.ingest import MAX_PART_CHARS, chunk_text, extract_pdf_text
from eval_harness.manifest import load_manifest
from eval_harness.search import SearchIndex

REPO = Path(__file__).resolve().parent.parent
CONFIG = load_config(REPO / "config.toml")
MANIFEST = load_manifest(CONFIG.pack)
[LABOUR_LAW_EN] = [s for s in MANIFEST.sources if s.id == "labour-law-en"]
PDF = source_path(CONFIG.sources_dir, LABOUR_LAW_EN)


@pytest.fixture(scope="module")
def chunks():
    if not verified(PDF, LABOUR_LAW_EN):
        pytest.skip("English Labour Law not fetched; run `eval fetch`")
    return chunk_text(extract_pdf_text(PDF), LABOUR_LAW_EN)


def test_every_article_of_the_english_labour_law_is_chunked_in_order(chunks):
    articles = list(dict.fromkeys(c.article for c in chunks))

    assert articles == [str(n) for n in range(1, 75)]
    assert all(c.instrument == "labour-law" and c.language == "en" for c in chunks)


def test_article_text_is_complete_and_free_of_page_footers(chunks):
    article_51 = "\n".join(c.text for c in chunks if c.article == "51")

    assert article_51.startswith("Article (51)\nEnd-of-Service Gratuity for Full-Time Workers")
    assert "The wage of twenty-one (21) days for each year of the first five years" in article_51
    assert "does\nnot exceed two years' wage." in article_51
    assert not any("Concerning Regulating Labor Relations" in c.text for c in chunks)


def test_long_articles_are_split_into_parts_that_fit(chunks):
    assert max(c.part for c in chunks if c.article == "1") > 1
    assert all(len(c.text) <= MAX_PART_CHARS for c in chunks)


def test_bm25_finds_the_right_article_for_plain_questions(chunks):
    index = SearchIndex(chunks)

    assert index.search("maximum probation period", 3)[0].article == "9"
    assert index.search("end of service gratuity basic wage", 3)[0].article == "51"
    assert "29" in {c.article for c in index.search("annual leave days", 3)}
