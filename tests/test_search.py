import hashlib

import pytest

from eval_harness.ingest import Chunk, write_chunks
from eval_harness.search import SearchIndex, search_tools


def chunk(article, part, text, instrument="statute", language="en"):
    return Chunk(
        id=f"{instrument}:{language}:{article}:{part}",
        instrument=instrument,
        article=article,
        part=part,
        language=language,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source=f"{instrument}-{language}",
    )


CORPUS = [
    chunk("9", 1, "Article (9) Probation. The probation period shall not exceed six months."),
    chunk("29", 1, "Article (29) Annual Leave. The worker is entitled to thirty days of leave."),
    chunk("29", 2, "2. Leave for parts of the year is calculated in proportion."),
    chunk("51", 1, "Article (51) End-of-Service Gratuity, based on the basic wage."),
]
INSTRUMENTS = {"statute": "The Statute"}


@pytest.fixture
def index():
    return SearchIndex(CORPUS)


def test_search_ranks_the_matching_article_first(index):
    results = index.search("How long can a probation period last?", k=8)

    assert results[0].id == "statute:en:9:1"


def test_search_returns_only_chunks_that_share_a_term_with_the_query(index):
    results = index.search("annual leave", k=8)

    assert {c.id for c in results} == {"statute:en:29:1", "statute:en:29:2"}
    assert index.search("zebra", k=8) == []


def test_search_returns_at_most_k_chunks(index):
    assert len(index.search("article", k=2)) == 2


def test_section_returns_every_part_of_an_article_in_order(index):
    parts = index.section("statute", "29", "en")

    assert [c.part for c in parts] == [1, 2]


def test_section_of_an_unknown_article_is_empty(index):
    assert index.section("statute", "99", "en") == []


def test_index_loads_the_chunks_ingest_wrote(tmp_path):
    write_chunks(CORPUS, tmp_path)

    assert SearchIndex.load(tmp_path).chunks == CORPUS


def tools(index, retrieved):
    def record(_tool, chunks):
        retrieved.append(chunks)

    return {t.name: t for t in search_tools(index, INSTRUMENTS, record)}


def test_search_sources_tool_returns_citable_chunks_and_reports_what_it_retrieved(index):
    retrieved = []

    result = tools(index, retrieved)["search_sources"].run({"query": "gratuity basic wage"})

    assert result[0] == {
        "id": "statute:en:51:1",
        "instrument": "statute",
        "article": "51",
        "part": 1,
        "language": "en",
        "text": CORPUS[3].text,
    }
    assert [c.id for c in retrieved[0]] == [r["id"] for r in result]


def test_search_sources_tool_returns_eight_chunks_at_most(index):
    many = SearchIndex([chunk(str(n), 1, f"wage rule {n}") for n in range(1, 20)])

    assert len(search_tools(many, INSTRUMENTS, lambda *_: None)[0].run({"query": "wage"})) == 8


def test_get_section_tool_returns_the_whole_article(index):
    retrieved = []

    result = tools(index, retrieved)["get_section"].run(
        {"instrument": "statute", "article": "29", "language": "en"}
    )

    assert [r["id"] for r in result] == ["statute:en:29:1", "statute:en:29:2"]
    assert [c.id for c in retrieved[0]] == ["statute:en:29:1", "statute:en:29:2"]


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("search_sources", {}, "query"),
        ("search_sources", {"query": "  "}, "query"),
        ("get_section", {"instrument": "statute", "article": "99", "language": "en"}, "99"),
        ("get_section", {"instrument": "other", "article": "9", "language": "en"}, "other"),
        ("get_section", {"instrument": "statute", "language": "en"}, "article"),
    ],
)
def test_bad_tool_arguments_raise_value_error_for_the_model(index, tool, arguments, message):
    with pytest.raises(ValueError, match=message):
        tools(index, [])[tool].run(arguments)


def test_tool_descriptions_name_the_instruments_to_cite(index):
    for tool in search_tools(index, INSTRUMENTS, lambda *_: None):
        assert '"statute" (The Statute)' in tool.description
