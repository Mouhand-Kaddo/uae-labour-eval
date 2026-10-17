import pytest

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


def calc_case(expected, scoring):
    return Case(
        id="calc-en-001",
        category="calc",
        language="en",
        input="What is my gratuity?",
        expected=expected,
        scoring=scoring,
        reviewed=False,
        refs=[],
        depends_on=[],
        rationale="21 days × 1,200 = 25,200.",
    )


def answered(text):
    return FinalAnswer(answer=text, citations=[], status="answered")


NUMERIC = [
    ("Your gratuity is AED 25,200.00.", {"numbers": [25200]}, True),
    ("مكافأتك ٢٥٬٢٠٠ درهم.", {"numbers": [25200]}, True),
    ("مكافأتك ٦٬٩٠٤٫١١ درهم.", {"numbers": [6904.11]}, True),
    ("مكافأتك 25,200 درهم.", {"numbers": [25200]}, True),
    ("About AED 6,904.", {"numbers": [6904.11], "tolerance": 1}, True),
    ("About AED 6,904.", {"numbers": [6904.11]}, False),
    ("AED 6,904.11 over 365 days.", {"numbers": [6904.11, 365]}, True),
    ("AED 6,904.11.", {"numbers": [6904.11, 365]}, False),
    ("You are owed 7,000.", {"numbers": [6904.11], "tolerance": 1}, False),
]


@pytest.mark.parametrize(("answer", "expected", "passes"), NUMERIC)
def test_numeric_scorer_finds_each_expected_number_in_the_answer(answer, expected, passes):
    verdict = score_case(calc_case(expected, ["numeric"]), answered(answer), [])

    assert verdict.passed is passes


def test_numeric_scorer_reports_what_it_found():
    verdict = score_case(
        calc_case({"numbers": [25200]}, ["numeric"]), answered("AED 7,000 for 1 year"), []
    )

    assert verdict.details["numeric"]["missing"] == [25200]
    assert verdict.details["numeric"]["found"] == [7000, 1]


def test_numeric_scorer_fails_a_case_that_hit_a_cap():
    verdict = score_case(calc_case({"numbers": [0]}, ["numeric"]), FinalAnswer.limit(), [])

    assert not verdict.passed


EXPECTED_CALL = {
    "tool_call": {
        "name": "calculate_gratuity",
        "arguments": {"start_date": "2023-01-01", "monthly_basic_wage": 36500},
    }
}


def tool_step(name, **arguments):
    return {"type": "tool_call", "name": name, "arguments": arguments, "result": {}}


def test_tool_call_scorer_passes_when_the_tool_got_the_expected_arguments():
    trace = [
        tool_step(
            "calculate_gratuity",
            start_date="2023-01-01",
            monthly_basic_wage=36500.0,
            nationality="foreign",
        )
    ]

    verdict = score_case(calc_case(EXPECTED_CALL, ["tool_call"]), answered("..."), trace)

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


def test_tool_call_scorer_fails_on_a_wrong_argument():
    trace = [tool_step("calculate_gratuity", start_date="2023-01-01", monthly_basic_wage=50000)]

    verdict = score_case(calc_case(EXPECTED_CALL, ["tool_call"]), answered("..."), trace)

    assert not verdict.passed
    assert verdict.details["tool_call"]["calls"] == [
        {"start_date": "2023-01-01", "monthly_basic_wage": 50000}
    ]


def test_tool_call_scorer_fails_when_the_tool_was_not_called():
    trace = [tool_step("search_sources", query="gratuity")]

    verdict = score_case(calc_case(EXPECTED_CALL, ["tool_call"]), answered("..."), trace)

    assert not verdict.passed


def test_tool_call_scorer_passes_when_a_retry_got_it_right():
    trace = [
        tool_step("calculate_gratuity", start_date="01/01/2023", monthly_basic_wage=36500),
        tool_step("calculate_gratuity", start_date="2023-01-01", monthly_basic_wage=36500),
    ]

    verdict = score_case(calc_case(EXPECTED_CALL, ["tool_call"]), answered("..."), trace)

    assert verdict.passed
