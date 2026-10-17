import json
from datetime import date

import pytest
from uae_labour.probation import PROBATION_TOOL, check_probation

DAILY_1200 = 36500

MAXIMUM = [
    pytest.param(3, True, id="Art9(1)-three-months"),
    pytest.param(6, True, id="Art9(1)-six-months-is-the-maximum"),
    pytest.param(6.5, False, id="Art9(1)-six-and-a-half-months-exceeds"),
    pytest.param(7, False, id="Art9(1)-seven-months-exceeds"),
]


@pytest.mark.parametrize(("months", "within"), MAXIMUM)
def test_probation_may_not_exceed_six_months(months, within):
    result = check_probation(probation_months=months, ended_by="employer")

    assert result.probation_within_maximum is within


REQUIRED_NOTICE = [
    pytest.param("employer", 14, "Labour Law Art 9(1)", id="Art9(1)-employer-14-days"),
    pytest.param(
        "worker_moving_in_uae", 30, "Labour Law Art 9(3)", id="Art9(3)+Art67-one-month-is-30-days"
    ),
    pytest.param("worker_leaving_uae", 14, "Labour Law Art 9(4)", id="Art9(4)-leaving-14-days"),
]


@pytest.mark.parametrize(("ended_by", "days", "ref"), REQUIRED_NOTICE)
def test_written_notice_owed_depends_on_who_ends_probation_and_why(ended_by, days, ref):
    result = check_probation(probation_months=6, ended_by=ended_by)

    assert result.required_notice_days == days
    assert ref in {str(r) for r in result.refs}


SHORTFALL = [
    pytest.param(
        {
            "ended_by": "employer",
            "notice_date": date(2024, 3, 1),
            "termination_date": date(2024, 3, 15),
            "monthly_wage": DAILY_1200,
        },
        14,
        0,
        0.00,
        "1 March to 15 March = 14 days' notice; 14 required: nothing owed",
        id="Art9(1)-14-days-given",
    ),
    pytest.param(
        {
            "ended_by": "employer",
            "notice_date": date(2024, 3, 1),
            "termination_date": date(2024, 3, 11),
            "monthly_wage": DAILY_1200,
        },
        10,
        4,
        4800.00,
        "10 days given, 4 short × (36,500 × 12 / 365 = 1,200) = 4,800",
        id="Art9(5)+OQ-001-employer-short-notice",
    ),
    pytest.param(
        {
            "ended_by": "worker_moving_in_uae",
            "notice_date": date(2024, 3, 1),
            "termination_date": date(2024, 3, 21),
            "monthly_wage": DAILY_1200,
        },
        20,
        10,
        12000.00,
        "20 days given of 30 (one month, Art 67): 10 short × 1,200 = 12,000",
        id="Art9(3)+Art9(5)-moving-worker-short-notice",
    ),
    pytest.param(
        {
            "ended_by": "worker_leaving_uae",
            "notice_date": date(2024, 3, 1),
            "termination_date": date(2024, 3, 8),
            "monthly_wage": 10000,
        },
        7,
        7,
        2301.37,
        "7 days given of 14: 7 short × 10,000 × 12 / 365 = 840,000 / 365 = 2,301.37",
        id="Art9(4)+Art9(5)-leaving-worker-short-notice",
    ),
]


@pytest.mark.parametrize(("facts", "given", "short", "expected", "working"), SHORTFALL)
def test_short_notice_costs_the_wage_for_the_missing_days(facts, given, short, expected, working):
    result = check_probation(probation_months=6, **facts)

    assert result.notice_days_given == given
    assert result.notice_shortfall_days == short
    assert result.compensation == expected, working
    assert "Labour Law Art 9(5)" in {str(r) for r in result.refs}
    assert result.open_questions == ["OQ-001"]


def test_shortfall_without_a_wage_has_no_compensation_figure():
    result = check_probation(
        probation_months=6,
        ended_by="employer",
        notice_date=date(2024, 3, 1),
        termination_date=date(2024, 3, 11),
    )

    assert result.notice_shortfall_days == 4
    assert result.compensation is None


def test_without_notice_dates_only_the_required_notice_is_given():
    result = check_probation(probation_months=6, ended_by="employer", monthly_wage=DAILY_1200)

    assert result.notice_days_given is None
    assert result.compensation is None
    assert {str(r) for r in result.refs} == {"Labour Law Art 9(1)"}
    assert result.open_questions == []


TOOL_ARGS = {
    "probation_months": 6,
    "ended_by": "employer",
    "notice_date": "2024-03-01",
    "termination_date": "2024-03-11",
    "monthly_wage": 36500,
}


def test_tool_takes_json_arguments_and_returns_refs_as_data():
    result = PROBATION_TOOL.run(TOOL_ARGS)

    assert PROBATION_TOOL.name == "check_probation"
    assert result["compensation"] == 4800.00
    assert {"instrument": "Labour Law", "article": "9", "clause": "5"} in result["refs"]
    json.dumps(result)


def test_tool_needs_only_the_probation_length_and_who_ends_it():
    minimal = {"probation_months": 6, "ended_by": "employer"}

    assert PROBATION_TOOL.run(minimal)["required_notice_days"] == 14
    assert set(PROBATION_TOOL.parameters["required"]) == set(minimal)


BAD_ARGUMENTS = [
    pytest.param({"probation_months": 0}, "probation_months", id="months-not-positive"),
    pytest.param({"probation_months": "6"}, "probation_months", id="months-not-number"),
    pytest.param({"ended_by": "worker"}, "ended_by", id="unknown-ended-by"),
    pytest.param({"notice_date": "1 March 2024"}, "notice_date", id="date-not-iso"),
    pytest.param({"termination_date": "2024-02-28"}, "termination_date", id="termination-first"),
    pytest.param({"notice_date": None}, "notice_date", id="only-one-date"),
    pytest.param({"monthly_wage": -1}, "monthly_wage", id="wage-not-positive"),
    pytest.param({"start_date": "2024-01-01"}, "start_date", id="unknown-argument"),
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        PROBATION_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="ended_by"):
        PROBATION_TOOL.run({"probation_months": 6})
