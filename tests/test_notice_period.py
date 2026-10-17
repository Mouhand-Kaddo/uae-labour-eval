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


def test_pay_in_lieu_is_left_out_when_the_notice_period_is_outside_the_range():
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
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        NOTICE_PERIOD_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="notice_days"):
        NOTICE_PERIOD_TOOL.run({"monthly_wage": 36500})
