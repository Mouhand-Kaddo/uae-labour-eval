from pathlib import Path

import pytest

from eval_harness.config import load_config
from eval_harness.fetch import source_path, verified
from eval_harness.ingest import (
    MAX_PART_CHARS,
    check_article_sets,
    chunk_text,
    extract_pdf_text,
    source_text,
)
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
    index = SearchIndex(chunks, [[0.0]] * len(chunks))

    def bm25_only(query):
        return index.search(query, [0.0], 3)

    assert bm25_only("maximum probation period")[0].article == "9"
    assert bm25_only("end of service gratuity basic wage")[0].article == "51"
    assert "29" in {c.article for c in bm25_only("annual leave days")}


[LABOUR_LAW_AR] = [s for s in MANIFEST.sources if s.id == "labour-law-ar"]
PDF_AR = source_path(CONFIG.sources_dir, LABOUR_LAW_AR)


@pytest.fixture(scope="module")
def arabic_text():
    if not verified(PDF_AR, LABOUR_LAW_AR):
        pytest.skip("Arabic Labour Law not fetched; run `eval fetch`")
    return source_text(PDF_AR, LABOUR_LAW_AR)


@pytest.fixture(scope="module")
def arabic_chunks(arabic_text):
    return chunk_text(arabic_text, LABOUR_LAW_AR)


def article(chunks, number):
    return "\n".join(c.text for c in chunks if c.article == number)


def test_the_arabic_labour_law_is_indexed_and_every_article_is_chunked_in_order(arabic_chunks):
    assert LABOUR_LAW_AR.indexed
    assert list(dict.fromkeys(c.article for c in arabic_chunks)) == [str(n) for n in range(1, 75)]
    assert all(c.language == "ar" and c.instrument == "labour-law" for c in arabic_chunks)


def test_repaired_arabic_text_has_no_replacement_characters_and_reads_in_order(arabic_text):
    assert "�" not in arabic_text
    assert "مرسوم بقانون اتحادي رقم (33) لسنة 2021" in arabic_text


def test_repaired_arabic_articles_contain_known_phrases(arabic_chunks):
    assert "الأجر الأساسي :" in article(arabic_chunks, "1")
    assert "الأجر : الأجر الأساسي، مُضافًا إليه البدلات النقدية" in article(arabic_chunks, "1")
    assert article(arabic_chunks, "9").startswith("المادة (9)\nفترة التجربة\n1. لصاحب العمل")
    assert "مدة لا تزيد على (6) ستة أشهر" in article(arabic_chunks, "9")
    assert "أ. أجر (21) واحد وعشرين يوم عن كل سنة من سنوات الخدمة الخمس الأولى." in article(
        arabic_chunks, "51"
    )
    assert "كل خلاف بين صاحب عمل والعامل" in article(arabic_chunks, "1")


def test_arabic_page_footers_and_split_yeh_tails_are_gone(arabic_chunks):
    text = "\n".join(c.text for c in arabic_chunks)

    assert "بشأن تنظيم علاقات العمل 27" not in text
    assert "الأساس ي" not in text
    assert "يتقاض ى" not in text


def test_arabic_and_english_article_sets_match(chunks, arabic_chunks):
    check_article_sets(chunks + arabic_chunks)


def test_bm25_finds_arabic_articles_despite_spelling_variants(arabic_chunks):
    index = SearchIndex(arabic_chunks, [[0.0]] * len(arabic_chunks))

    def bm25_only(query):
        return [c.article for c in index.search(query, [0.0], 3)]

    assert bm25_only("فتره التجربه")[0] == "9"
    assert "51" in bm25_only("مكافاة نهاية الخدمة")
    assert "29" in bm25_only("الاجازة السنويه")
