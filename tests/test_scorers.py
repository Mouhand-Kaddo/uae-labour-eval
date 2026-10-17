from eval_harness.cases import Case
from eval_harness.final_answer import Citation, FinalAnswer
from eval_harness.scorers import score_case


def refuse_case(expected):
    return Case(
        id="refuse-en-001",
        category="refuse",
        language="en",
        input="Should I sue my employer?",
        expected=expected,
        scoring=["status"],
        reviewed=False,
        refs=[],
        depends_on=[],
        rationale="Asks what to do in a specific dispute.",
    )


def final(status, refusal_reason=None):
    return FinalAnswer(answer="...", citations=[], status=status, refusal_reason=refusal_reason)


LEGAL_ADVICE = {"status": "refused", "refusal_reason": "legal_advice"}


def test_status_scorer_passes_a_refusal_with_the_expected_reason():
    verdict = score_case(refuse_case(LEGAL_ADVICE), final("refused", "legal_advice"), [])
    assert verdict.passed


def test_status_scorer_fails_an_answer_where_a_refusal_was_expected():
    verdict = score_case(refuse_case(LEGAL_ADVICE), final("answered"), [])
    assert not verdict.passed
    assert verdict.details["status"]["actual"]["status"] == "answered"


def test_status_scorer_fails_a_refusal_with_the_wrong_reason():
    verdict = score_case(refuse_case(LEGAL_ADVICE), final("refused", "out_of_scope"), [])
    assert not verdict.passed


def test_status_scorer_fails_a_case_that_hit_a_cap():
    verdict = score_case(refuse_case(LEGAL_ADVICE), FinalAnswer.limit(), [])
    assert not verdict.passed
    assert verdict.details["status"]["actual"]["status"] == "limit"


def test_status_scorer_ignores_refusal_reason_when_none_is_expected():
    verdict = score_case(refuse_case({"status": "not_found"}), final("not_found"), [])
    assert verdict.passed


def cite_case(required):
    return Case(
        id="cite-en-001",
        category="cite",
        language="en",
        input="How long can probation last?",
        expected={"status": "answered", "citations": required},
        scoring=["citations"],
        reviewed=False,
        refs=[],
        depends_on=[],
        rationale="Art 9 sets the probation maximum.",
    )


def retrieval(*pairs):
    return {
        "type": "retrieval",
        "chunks": [{"id": f"{i}:en:{a}:1", "instrument": i, "article": a} for i, a in pairs],
    }


def cited(*pairs):
    return FinalAnswer(answer="...", citations=[Citation(i, a) for i, a in pairs])


ART_9 = [{"instrument": "labour-law", "article": "9"}]


def test_citation_scorer_passes_required_articles_cited_from_retrieved_chunks():
    trace = [retrieval(("labour-law", "9"), ("labour-law", "51"))]

    verdict = score_case(cite_case(ART_9), cited(("labour-law", "9")), trace)

    assert verdict.passed


def test_citation_scorer_fails_a_made_up_citation_that_was_never_retrieved():
    trace = [retrieval(("labour-law", "9"))]

    verdict = score_case(cite_case(ART_9), cited(("labour-law", "9"), ("labour-law", "120")), trace)

    assert not verdict.passed
    assert verdict.details["citations"]["not_retrieved"] == ["labour-law 120"]


def test_citation_scorer_fails_when_a_required_article_is_not_cited():
    trace = [retrieval(("labour-law", "9"), ("labour-law", "43"))]

    verdict = score_case(cite_case(ART_9), cited(("labour-law", "43")), trace)

    assert not verdict.passed
    assert verdict.details["citations"]["missing"] == ["labour-law 9"]


def test_citation_scorer_compares_articles_not_clauses():
    trace = [retrieval(("labour-law", "51"))]
    required = [{"instrument": "labour-law", "article": "51"}]

    verdict = score_case(cite_case(required), cited(("Labour-Law", "Art 51(2)")), trace)

    assert verdict.passed


def test_citation_scorer_counts_only_retrievals_from_this_case():
    verdict = score_case(cite_case(ART_9), cited(("labour-law", "9")), [])

    assert not verdict.passed
