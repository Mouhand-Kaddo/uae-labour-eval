from eval_harness.cases import Case
from eval_harness.final_answer import FinalAnswer
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
