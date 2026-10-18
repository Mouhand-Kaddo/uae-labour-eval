import json

import pytest
from uae_labour.notice_period import NOTICE_PERIOD_TOOL, check_notice_period

DAILY_1200 = 36500

RANGE = [
    pytest.param(29, "below_minimum", ["OQ-012"], id="Art43(1)+OQ-012-29-days-below-30"),
    pytest.param(30, "within_range", [], id="Art43(1)-30-days-minimum"),
    pytest.param(90, "within_range", [], id="Art43(1)-90-days-maximum"),
    pytest.param(91, "above_maximum", ["OQ-012"], id="Art43(1)+OQ-012-91-days-above-90"),
]


@pytest.mark.parametrize(("notice_days", "outcome", "open_questions"), RANGE)
def test_contract_notice_period_must_be_30_to_90_days(notice_days, outcome, open_questions):
    result = check_notice_period(notice_days=notice_days)

    assert result.outcome == outcome
    assert result.open_questions == open_questions


PAY_IN_LIEU = [
    pytest.param(
        {"notice_days": 30, "monthly_wage": DAILY_1200},
        30,
        36000.00,
        "no notice worked: 30 days × (36,500 × 12 / 365 = 1,200) = 36,000",
        id="Art43(3)+OQ-001-entire-notice-period",
    ),
    pytest.param(
        {"notice_days": 60, "monthly_wage": DAILY_1200, "notice_days_worked": 45},
        15,
        18000.00,
        "60 − 45 worked = 15 days × 1,200 = 18,000",
        id="Art43(3)-remaining-part-of-the-notice",
    ),
    pytest.param(
        {"notice_days": 90, "monthly_wage": 10000},
        90,
        29589.04,
        "90 × 10,000 × 12 / 365 = 10,800,000 / 365 = 29,589.04",
        id="Art43(4)+OQ-001-last-wage-x12-div365",
    ),
    pytest.param(
        {"notice_days": 30, "monthly_wage": DAILY_1200, "notice_days_worked": 30},
        0,
        0.00,
        "whole notice worked: nothing owed",
        id="Art43(2)-notice-honoured",
    ),
]


@pytest.mark.parametrize(("facts", "unserved", "expected", "working"), PAY_IN_LIEU)
def test_pay_in_lieu_of_notice_is_the_wage_for_the_unserved_days(
    facts, unserved, expected, working
):
    result = check_notice_period(**facts)

    assert result.unserved_days == unserved
    assert result.pay_in_lieu == expected, working
    assert result.open_questions == ["OQ-001"]


APPLICABLE_PERIOD = [
    pytest.param(
        15, "employer", 30, id="Art43(1)+Art65(3)+OQ-012-short-term-hurts-worker-employer-ends"
    ),
    pytest.param(15, "worker", 15, id="Art65(3)+OQ-012-short-term-helps-resigning-worker-stands"),
    pytest.param(120, "employer", 120, id="Art65(3)+OQ-012-long-term-helps-worker-employer-ends"),
    pytest.param(120, "worker", 90, id="Art43(1)+Art65(3)+OQ-012-long-term-hurts-resigning-worker"),
    pytest.param(60, "employer", 60, id="Art43(1)-in-range-term-applies-employer-ends"),
    pytest.param(60, "worker", 60, id="Art43(1)-in-range-term-applies-worker-resigns"),
    pytest.param(60, None, 60, id="Art43(1)-in-range-term-applies-whoever-ends"),
    pytest.param(15, None, None, id="OQ-012-out-of-range-needs-who-terminates"),
]


@pytest.mark.parametrize(("notice_days", "terminated_by", "applicable"), APPLICABLE_PERIOD)
def test_applicable_notice_period_follows_the_worker_favourable_split(
    notice_days, terminated_by, applicable
):
    result = check_notice_period(notice_days=notice_days, terminated_by=terminated_by)

    assert result.applicable_notice_days == applicable


OUT_OF_RANGE_PAY_IN_LIEU = [
    pytest.param(
        {"notice_days": 15, "terminated_by": "employer", "monthly_wage": DAILY_1200},
        36000.00,
        "15 days hurts the worker: 30 apply; 30 × 1,200 = 36,000",
        id="Art43(3)+OQ-012-employer-owes-the-30-day-minimum",
    ),
    pytest.param(
        {"notice_days": 15, "terminated_by": "worker", "monthly_wage": DAILY_1200},
        18000.00,
        "15 days helps the resigning worker and stands: 15 × 1,200 = 18,000",
        id="Art43(3)+OQ-012-resigning-worker-owes-the-shorter-term",
    ),
    pytest.param(
        {"notice_days": 120, "terminated_by": "employer", "monthly_wage": 10000},
        39452.05,
        "120 days helps the worker and stands: 120 × 10,000 × 12 / 365 = 14,400,000 / 365",
        id="Art43(3)+Art43(4)+OQ-012-employer-owes-the-longer-term",
    ),
    pytest.param(
        {
            "notice_days": 120,
            "terminated_by": "worker",
            "monthly_wage": DAILY_1200,
            "notice_days_worked": 30,
        },
        72000.00,
        "120 days hurts the resigning worker: capped at 90; 90 − 30 worked = 60 × 1,200 = 72,000",
        id="Art43(3)+OQ-012-resigning-worker-owes-at-most-90-days",
    ),
]


@pytest.mark.parametrize(("facts", "expected", "working"), OUT_OF_RANGE_PAY_IN_LIEU)
def test_out_of_range_pay_in_lieu_uses_the_applicable_period_at_the_last_wage(
    facts, expected, working
):
    result = check_notice_period(**facts)

    assert result.pay_in_lieu == expected, working
    assert result.open_questions == ["OQ-012", "OQ-001"]
    assert "Labour Law Art 65(3)" in {str(ref) for ref in result.refs}


def test_out_of_range_pay_in_lieu_is_left_out_without_who_terminates():
    result = check_notice_period(notice_days=15, monthly_wage=DAILY_1200)

    assert result.pay_in_lieu is None
    assert result.open_questions == ["OQ-012"]


def test_pay_in_lieu_is_left_out_without_a_wage():
    assert check_notice_period(notice_days=30).pay_in_lieu is None


REFS = [
    pytest.param({"notice_days": 30}, {"Labour Law Art 43(1)"}, id="Art43(1)-range-only"),
    pytest.param(
        {"notice_days": 30, "monthly_wage": DAILY_1200},
        {
            "Labour Law Art 43(1)",
            "Labour Law Art 43(3)",
            "Labour Law Art 43(4)",
            "Labour Law Art 67",
        },
        id="Art43(3)(4)-pay-in-lieu",
    ),
]


@pytest.mark.parametrize(("facts", "refs"), REFS)
def test_result_returns_the_articles_it_used(facts, refs):
    assert {str(ref) for ref in check_notice_period(**facts).refs} == refs


TOOL_ARGS = {"notice_days": 60, "notice_days_worked": 45, "monthly_wage": 36500}


def test_tool_takes_json_arguments_and_returns_refs_as_data():
    result = NOTICE_PERIOD_TOOL.run(TOOL_ARGS)

    assert NOTICE_PERIOD_TOOL.name == "check_notice_period"
    assert result["outcome"] == "within_range"
    assert result["pay_in_lieu"] == 18000.00
    assert {"instrument": "Labour Law", "article": "43", "clause": "3"} in result["refs"]
    json.dumps(result)


def test_tool_needs_only_the_notice_days():
    assert NOTICE_PERIOD_TOOL.run({"notice_days": 30})["outcome"] == "within_range"
    assert NOTICE_PERIOD_TOOL.parameters["required"] == ["notice_days"]


BAD_ARGUMENTS = [
    pytest.param({"notice_days": 0}, "notice_days", id="notice-days-not-positive"),
    pytest.param({"notice_days": 30.5}, "notice_days", id="notice-days-not-whole"),
    pytest.param({"notice_days": "30"}, "notice_days", id="notice-days-not-number"),
    pytest.param({"notice_days_worked": -1}, "notice_days_worked", id="negative-days-worked"),
    pytest.param({"notice_days_worked": 61}, "notice_days_worked", id="worked-over-notice"),
    pytest.param({"monthly_wage": 0}, "monthly_wage", id="wage-not-positive"),
    pytest.param({"monthly_wage": False}, "monthly_wage", id="wage-bool"),
    pytest.param({"notice_months": 2}, "notice_months", id="unknown-argument"),
    pytest.param({"terminated_by": "both"}, "terminated_by", id="unknown-terminating-party"),
    pytest.param(
        {"notice_days": 15, "terminated_by": "employer", "notice_days_worked": 31},
        "notice_days_worked",
        id="worked-over-the-applicable-period",
    ),
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        NOTICE_PERIOD_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="notice_days"):
        NOTICE_PERIOD_TOOL.run({"monthly_wage": 36500})


def test_tool_prices_notice_worked_beyond_a_short_contract_term_against_the_minimum():
    result = NOTICE_PERIOD_TOOL.run(
        {
            "notice_days": 15,
            "terminated_by": "employer",
            "notice_days_worked": 20,
            "monthly_wage": 36500,
        }
    )

    assert (result["applicable_notice_days"], result["pay_in_lieu"]) == (30, 12000.00)
