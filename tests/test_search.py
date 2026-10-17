import hashlib

import pytest
from fake_openrouter import fake_embedding

from eval_harness.embeddings import append_vectors
from eval_harness.ingest import Chunk, IngestError, write_chunks
from eval_harness.search import SearchIndex, search_tools, tokenize


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
    chunk("43", 1, "Article (43) Warning Period. Either party may end the contract in writing."),
    chunk("9", 1, "المادة (9) فترة التجربة لا تزيد على ستة أشهر.", language="ar"),
    chunk("43", 1, "المادة (43) فترة الإنذار من ثلاثين يوماً إلى تسعين يوماً.", language="ar"),
]
INSTRUMENTS = {"statute": "The Statute"}


def embedded(chunks):
    return SearchIndex(chunks, [fake_embedding(c.text) for c in chunks])


@pytest.fixture
def index():
    return embedded(CORPUS)


def search(index, query, k=8):
    return index.search(query, fake_embedding(query), k)


def ids(chunks):
    return [c.id for c in chunks]


def test_search_ranks_the_matching_article_first(index):
    assert search(index, "How long can a probation period last?")[0].id == "statute:en:9:1"


def test_search_fuses_keyword_and_embedding_rankings_by_reciprocal_rank():
    keyword_only = chunk("1", 1, "wage")
    both = chunk("2", 1, "wage paid monthly to the worker")
    embedding_only = chunk("3", 1, "salary")
    index = SearchIndex([keyword_only, both, embedding_only], [[0.0, 1.0], [1.0, 0.0], [0.8, 0.6]])

    results = index.search("wage", [1.0, 0.0], k=8)

    assert ids(results) == ["statute:en:2:1", "statute:en:1:1", "statute:en:3:1"]


def test_an_english_question_finds_the_arabic_chunk_of_the_same_article(index):
    assert "statute:ar:43:1" in ids(search(index, "What notice must be given?"))


def test_an_arabic_question_finds_the_english_chunk_of_the_same_article(index):
    assert "statute:en:9:1" in ids(search(index, "ما مدة التجربة؟"))


def test_embeddings_find_an_article_whose_wording_shares_no_keyword_with_the_question(index):
    results = search(index, "notice")

    assert ids(results)[:2] == ["statute:en:43:1", "statute:ar:43:1"]


def test_search_returns_the_chunks_with_all_their_metadata(index):
    assert search(index, "gratuity")[0] == CORPUS[3]


def test_search_leaves_out_chunks_unrelated_to_the_query_in_both_rankings(index):
    assert ids(search(index, "annual leave")) == ["statute:en:29:1", "statute:en:29:2"]
    assert search(index, "zebra") == []


def test_section_returns_every_part_of_an_article_in_order(index):
    parts = index.section("statute", "29", "en")

    assert [c.part for c in parts] == [1, 2]


def test_section_of_an_unknown_article_is_empty(index):
    assert index.section("statute", "99", "en") == []


def test_index_loads_the_chunks_ingest_wrote_with_their_cached_vectors(tmp_path):
    write_chunks(CORPUS, tmp_path)
    append_vectors(tmp_path, "bge", [(c.text_sha256, fake_embedding(c.text)) for c in CORPUS])

    loaded = SearchIndex.load(tmp_path, "bge")

    assert loaded.chunks == CORPUS
    assert ids(search(loaded, "notice")) == ids(search(embedded(CORPUS), "notice"))


def test_index_refuses_to_load_chunks_without_a_vector_for_the_model(tmp_path):
    write_chunks(CORPUS, tmp_path)
    append_vectors(tmp_path, "other", [(c.text_sha256, fake_embedding(c.text)) for c in CORPUS])

    with pytest.raises(IngestError, match="7 chunk.*bge.*embed"):
        SearchIndex.load(tmp_path, "bge")


def tools(index, retrieved):
    def record(_tool, chunks):
        retrieved.append(chunks)

    return {t.name: t for t in search_tools(index, INSTRUMENTS, record, fake_embedding)}


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
    many = embedded([chunk(str(n), 1, f"wage rule {n}") for n in range(1, 20)])
    [search_sources, _] = search_tools(many, INSTRUMENTS, lambda *_: None, fake_embedding)

    assert len(search_sources.run({"query": "wage"})) == 8


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
    for tool in search_tools(index, INSTRUMENTS, lambda *_: None, fake_embedding):
        assert '"statute" (The Statute)' in tool.description


def test_tokenize_normalises_arabic_spelling_variants():
    text = "الأَجْرُ الأساسيّ إلى الإجـــازة آخر ٱلعمل"

    assert tokenize(text) == ["الاجر", "الاساسي", "الي", "الاجازه", "اخر", "العمل"]


def test_tokenize_casefolds_english():
    assert tokenize("Basic WAGE, Art 51") == ["basic", "wage", "art", "51"]
