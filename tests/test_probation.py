import json
from datetime import date

import pytest
from uae_labour.probation import PROBATION_TOOL, check_probation

DAILY_1200 = 36500
START = date(2024, 1, 1)
SIX_MONTHS_LATER = date(2024, 6, 28)

MAXIMUM = [
    pytest.param(
        date(2025, 1, 1),
        date(2025, 3, 31),
        90,
        True,
        "1 Jan to 31 Mar 2025 inclusive = 31 + 28 + 31 = 90 days",
        id="Art9(1)-three-months",
    ),
    pytest.param(
        date(2025, 1, 1),
        date(2025, 6, 29),
        180,
        True,
        "31 + 28 + 31 + 30 + 31 + 29 = 180 days = six 30-day months (Art 67)",
        id="Art9(1)+Art67-180-days-is-the-maximum",
    ),
    pytest.param(
        date(2025, 1, 1),
        date(2025, 6, 30),
        181,
        False,
        "six calendar months here are 181 days, one more than six 30-day months (Art 67)",
        id="Art9(1)+Art67-181-days-exceeds",
    ),
    pytest.param(
        date(2024, 1, 1),
        date(2024, 6, 28),
        180,
        True,
        "leap year: 31 + 29 + 31 + 30 + 31 + 28 = 180 days",
        id="Art9(1)+Art67-leap-year-180-days",
    ),
    pytest.param(
        date(2025, 2, 1),
        date(2025, 9, 30),
        242,
        False,
        "1 Feb to 30 Sep 2025 = 28 + 31 + 30 + 31 + 30 + 31 + 31 + 30 = 242 days",
        id="Art9(1)-eight-months-exceeds",
    ),
]


@pytest.mark.parametrize(("start", "end", "days", "within", "working"), MAXIMUM)
def test_probation_may_not_exceed_six_30_day_months_from_the_start_of_work(
    start, end, days, within, working
):
    result = check_probation(start_date=start, probation_end_date=end, ended_by="employer")

    assert result.probation_days == days, working
    assert result.maximum_days == 180
    assert result.probation_within_maximum is within
    assert {"Labour Law Art 9(1)", "Labour Law Art 67"} <= {str(r) for r in result.refs}


def test_without_a_probation_end_date_the_probation_runs_to_the_termination_date():
    result = check_probation(
        start_date=date(2025, 1, 1), termination_date=date(2025, 3, 15), ended_by="employer"
    )

    assert result.probation_days == 74, "31 + 28 + 15 = 74 days"
    assert result.probation_within_maximum is True


def test_probation_needs_its_end_or_the_termination_date():
    with pytest.raises(ValueError, match="probation_end_date or termination_date"):
        check_probation(start_date=START, ended_by="employer")


REQUIRED_NOTICE = [
    pytest.param("employer", 14, "Labour Law Art 9(1)", id="Art9(1)-employer-14-days"),
    pytest.param(
        "worker_moving_in_uae", 30, "Labour Law Art 9(3)", id="Art9(3)+Art67-one-month-is-30-days"
    ),
    pytest.param("worker_leaving_uae", 14, "Labour Law Art 9(4)", id="Art9(4)-leaving-14-days"),
]


@pytest.mark.parametrize(("ended_by", "days", "ref"), REQUIRED_NOTICE)
def test_written_notice_owed_depends_on_who_ends_probation_and_why(ended_by, days, ref):
    result = check_probation(
        start_date=START, probation_end_date=SIX_MONTHS_LATER, ended_by=ended_by
    )

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
    result = check_probation(start_date=START, probation_end_date=SIX_MONTHS_LATER, **facts)

    assert result.notice_days_given == given
    assert result.notice_shortfall_days == short
    assert result.compensation == expected, working
    assert "Labour Law Art 9(5)" in {str(r) for r in result.refs}
    assert result.open_questions == ["OQ-013", "OQ-001"]


def test_shortfall_without_a_wage_has_no_compensation_figure():
    result = check_probation(
        start_date=START,
        ended_by="employer",
        notice_date=date(2024, 3, 1),
        termination_date=date(2024, 3, 11),
    )

    assert result.notice_shortfall_days == 4
    assert result.compensation is None


def test_without_notice_dates_only_the_required_notice_is_given():
    result = check_probation(
        start_date=START,
        probation_end_date=SIX_MONTHS_LATER,
        ended_by="employer",
        monthly_wage=DAILY_1200,
    )

    assert result.notice_days_given is None
    assert result.compensation is None
    assert {str(r) for r in result.refs} == {"Labour Law Art 9(1)", "Labour Law Art 67"}
    assert result.open_questions == ["OQ-013"]


TOOL_ARGS = {
    "start_date": "2024-01-01",
    "probation_end_date": "2024-06-28",
    "ended_by": "employer",
    "notice_date": "2024-03-01",
    "termination_date": "2024-03-11",
    "monthly_wage": 36500,
}


def test_tool_takes_json_arguments_and_returns_refs_as_data():
    result = PROBATION_TOOL.run(TOOL_ARGS)

    assert PROBATION_TOOL.name == "check_probation"
    assert result["compensation"] == 4800.00
    assert result["probation_days"] == 180
    assert {"instrument": "Labour Law", "article": "9", "clause": "5"} in result["refs"]
    json.dumps(result)


def test_tool_needs_only_the_start_date_who_ends_it_and_one_end_date():
    minimal = {"start_date": "2024-01-01", "ended_by": "employer"}

    for end in ("probation_end_date", "termination_date"):
        assert PROBATION_TOOL.run({**minimal, end: "2024-03-31"})["required_notice_days"] == 14
    assert set(PROBATION_TOOL.parameters["required"]) == set(minimal)


BAD_ARGUMENTS = [
    pytest.param({"start_date": "1 January 2024"}, "start_date", id="start-not-iso"),
    pytest.param({"start_date": None}, "start_date", id="start-missing"),
    pytest.param(
        {"probation_end_date": "2023-12-31"}, "probation_end_date", id="probation-ends-first"
    ),
    pytest.param(
        {"probation_end_date": "2024-03-10"},
        "probation_end_date",
        id="contract-ends-after-probation",
    ),
    pytest.param(
        {"probation_end_date": None, "termination_date": "2023-12-31"},
        "termination_date",
        id="termination-before-start",
    ),
    pytest.param(
        {"probation_end_date": None, "notice_date": None, "termination_date": None},
        "probation_end_date or termination_date",
        id="no-end-date",
    ),
    pytest.param({"ended_by": "worker"}, "ended_by", id="unknown-ended-by"),
    pytest.param({"notice_date": "1 March 2024"}, "notice_date", id="date-not-iso"),
    pytest.param({"termination_date": "2024-02-28"}, "termination_date", id="termination-first"),
    pytest.param({"termination_date": None}, "termination_date", id="notice-without-termination"),
    pytest.param({"monthly_wage": -1}, "monthly_wage", id="wage-not-positive"),
    pytest.param({"probation_months": 6}, "probation_months", id="unknown-argument"),
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        PROBATION_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="ended_by"):
        PROBATION_TOOL.run({"start_date": "2024-01-01", "probation_end_date": "2024-03-31"})
