import json
from datetime import date

import pytest
from uae_labour.annual_leave import ANNUAL_LEAVE_TOOL, calculate_annual_leave

DAILY_1200 = 36500


def service(start, end, **extra):
    return {"start_date": start, "end_date": end, **extra}


FULL_TIME_ENTITLEMENT = [
    pytest.param(
        service(date(2024, 1, 1), date(2024, 6, 27)),
        179,
        0.00,
        ["OQ-011"],
        "31+29+31+30+31+27 = 179 days, not more than six 30-day months (180): (b) gives nothing",
        id="Art29(1)(b)+OQ-011-under-six-months",
    ),
    pytest.param(
        service(date(2024, 1, 1), date(2024, 6, 28)),
        180,
        0.00,
        ["OQ-005"],
        "180 days = exactly six months (Art 67); (b) needs more than six months",
        id="Art29(1)(b)+OQ-005-exactly-six-months",
    ),
    pytest.param(
        service(date(2024, 1, 1), date(2024, 6, 29)),
        181,
        12.07,
        ["OQ-005"],
        "181 days = 6 months 1 day; 181 × 2 / 30 = 12.067 days, part month pro rata",
        id="Art29(1)(b)+OQ-005-part-month",
    ),
    pytest.param(
        service(date(2024, 1, 1), date(2024, 7, 28)),
        210,
        14.00,
        [],
        "182 days to 30 June + 28 = 210 days = 7 months × 2 days = 14",
        id="Art29(1)(b)-whole-months",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30)),
        364,
        24.27,
        ["OQ-005"],
        "364 days < 365: still (b); 364 × 2 / 30 = 24.267 days",
        id="Art29(1)(b)+Art67-one-day-short-of-a-year",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 31)),
        365,
        30.00,
        [],
        "365 days = one year (Art 67): 30 days",
        id="Art29(1)(a)-exactly-one-year",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2023, 12, 31)),
        1095,
        90.00,
        [],
        "365 + 365 + 365 = 1,095 days = 3 years × 30 = 90 days",
        id="Art29(1)(a)-whole-years",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 7, 1)),
        547,
        44.96,
        ["OQ-005"],
        "547 days = 1 year + 182 days; 30 + 182 × 30 / 365 = 30 + 14.959 = 44.959",
        id="Art29(1)(c)+OQ-005-part-of-the-last-year",
    ),
    pytest.param(
        service(date(2024, 1, 1), date(2024, 12, 31)),
        366,
        30.08,
        ["OQ-005"],
        "leap year 366 days = 1 year + 1 day; 30 + 30 / 365 = 30.082",
        id="Art67-year-is-365-days-in-a-leap-year",
    ),
]


@pytest.mark.parametrize(
    ("facts", "service_days", "expected", "open_questions", "working"), FULL_TIME_ENTITLEMENT
)
def test_full_time_annual_leave_entitlement(facts, service_days, expected, open_questions, working):
    result = calculate_annual_leave(**facts)

    assert result.service_days == service_days
    assert result.entitlement_days == expected, working
    assert result.open_questions == open_questions


ONE_YEAR = (date(2023, 1, 1), date(2023, 12, 31))

PART_TIME_ENTITLEMENT = [
    pytest.param(
        service(*ONE_YEAR, work_pattern="part_time", part_time_hours_ratio=0.5),
        15,
        "30 full-time days × 50% = 15",
        id="ER18(4)-hours-percentage",
    ),
    pytest.param(
        service(*ONE_YEAR, work_pattern="part_time", part_time_hours_ratio=0.55),
        17,
        "30 × 55% = 16.5; part of a day counts as a full day → 17",
        id="ER18-part-day-is-a-full-day",
    ),
    pytest.param(
        service(*ONE_YEAR, work_pattern="part_time", part_time_hours_ratio=0.1),
        5,
        "30 × 10% = 3, below the minimum of five days a year → 5",
        id="ER18-minimum-five-days-a-year",
    ),
    pytest.param(
        service(
            date(2023, 1, 1),
            date(2023, 12, 30),
            work_pattern="part_time",
            part_time_hours_ratio=0.5,
        ),
        13,
        "364 days: full time 364 × 2 / 30 = 24.267; × 50% = 12.133 → 13",
        id="ER18+Art29(1)(b)-part-time-under-one-year",
    ),
]


@pytest.mark.parametrize(("facts", "expected", "working"), PART_TIME_ENTITLEMENT)
def test_part_time_annual_leave_follows_actual_hours(facts, expected, working):
    result = calculate_annual_leave(**facts)

    assert result.entitlement_days == expected, working
    assert "OQ-010" in result.open_questions


CASH_OUT = [
    pytest.param(
        service(*ONE_YEAR, monthly_basic_wage=DAILY_1200),
        36000.00,
        "30 days × (36,500 × 12 / 365 = 1,200) = 36,000",
        id="ER19(2)+OQ-003-whole-balance-on-basic-wage",
    ),
    pytest.param(
        service(
            date(2021, 1, 1), date(2023, 12, 31), monthly_basic_wage=DAILY_1200, leave_days_taken=70
        ),
        24000.00,
        "90 days − 70 taken = 20 days × 1,200 = 24,000",
        id="ER19(2)-balance-after-leave-taken",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30), monthly_basic_wage=DAILY_1200),
        29120.00,
        "364 × 2 / 30 = 728/30 days × 1,200 = 728 × 40 = 29,120",
        id="ER19(2)+Art29(1)(b)-balance-under-one-year",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 7, 1), monthly_basic_wage=10000, leave_days_taken=30),
        4918.00,
        "44.959 − 30 = 182 × 30 / 365 = 14.959 days × 10,000 × 12 / 365 "
        "= 655,200,000 / 133,225 = 4,917.996 → 4,918.00",
        id="ER19(2)+OQ-001-daily-basic-wage-x12-div365",
    ),
    pytest.param(
        service(*ONE_YEAR, monthly_basic_wage=DAILY_1200, leave_days_taken=30),
        0.00,
        "all 30 days taken: nothing to pay",
        id="ER19(2)-no-balance-left",
    ),
]


@pytest.mark.parametrize(("facts", "expected", "working"), CASH_OUT)
def test_leave_cash_out_pays_the_balance_on_the_basic_wage(facts, expected, working):
    result = calculate_annual_leave(**facts)

    assert result.cash_out == expected, working
    assert {"OQ-001", "OQ-003"} <= set(result.open_questions)


def test_leave_cash_out_is_left_out_without_a_basic_wage():
    result = calculate_annual_leave(**service(*ONE_YEAR))

    assert result.cash_out is None
    assert result.balance_days == 30.00


def test_leave_taken_cannot_exceed_the_entitlement():
    with pytest.raises(ValueError, match="leave_days_taken"):
        calculate_annual_leave(**service(*ONE_YEAR, leave_days_taken=31))


ENTITLEMENT = {"Labour Law Art 29(1)", "Labour Law Art 67"}
CASH = {"Labour Law Art 29(9)", "Executive Regulations Art 19(2)"}
PART_TIME = {"Labour Law Art 29(2)", "Executive Regulations Art 18"}

REFS_AND_QUESTIONS = [
    pytest.param(service(*ONE_YEAR), ENTITLEMENT, [], id="Art29(1)-entitlement"),
    pytest.param(
        service(*ONE_YEAR, monthly_basic_wage=DAILY_1200),
        ENTITLEMENT | CASH,
        ["OQ-001", "OQ-003"],
        id="ER19(2)-cash-out",
    ),
    pytest.param(
        service(*ONE_YEAR, work_pattern="part_time", part_time_hours_ratio=0.5),
        ENTITLEMENT | PART_TIME,
        ["OQ-010"],
        id="Art29(2)+ER18-part-time",
    ),
    pytest.param(
        service(
            date(2021, 1, 1),
            date(2022, 7, 1),
            monthly_basic_wage=DAILY_1200,
            work_pattern="part_time",
            part_time_hours_ratio=0.5,
        ),
        ENTITLEMENT | CASH | PART_TIME,
        ["OQ-005", "OQ-010", "OQ-001", "OQ-003"],
        id="Art29(1)(c)+ER18+ER19(2)-everything",
    ),
]


@pytest.mark.parametrize(("facts", "refs", "open_questions"), REFS_AND_QUESTIONS)
def test_result_returns_the_articles_and_open_questions_it_used(facts, refs, open_questions):
    result = calculate_annual_leave(**facts)

    assert {str(ref) for ref in result.refs} == refs
    assert result.open_questions == open_questions


TOOL_ARGS = {
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "work_pattern": "full_time",
    "part_time_hours_ratio": None,
    "leave_days_taken": 10,
    "monthly_basic_wage": 36500,
    "monthly_wage": 50000,
}


def test_tool_takes_json_arguments_and_returns_refs_as_data():
    result = ANNUAL_LEAVE_TOOL.run(TOOL_ARGS)

    assert ANNUAL_LEAVE_TOOL.name == "calculate_annual_leave"
    assert result["entitlement_days"] == 30.00
    assert result["balance_days"] == 20.00
    assert result["cash_out"] == 24000.00
    assert {"instrument": "Executive Regulations", "article": "19", "clause": "2"} in result["refs"]
    json.dumps(result)


def test_tool_needs_only_the_service_dates():
    minimal = {"start_date": "2023-01-01", "end_date": "2023-12-31"}

    assert ANNUAL_LEAVE_TOOL.run(minimal)["entitlement_days"] == 30.00
    assert set(ANNUAL_LEAVE_TOOL.parameters["required"]) == set(minimal)


BAD_ARGUMENTS = [
    pytest.param({"start_date": "2023/01/01"}, "start_date", id="date-not-iso"),
    pytest.param({"end_date": "2022-12-31"}, "end_date", id="end-before-start"),
    pytest.param({"monthly_basic_wage": 0}, "monthly_basic_wage", id="basic-wage-not-positive"),
    pytest.param({"monthly_basic_wage": True}, "monthly_basic_wage", id="basic-wage-bool"),
    pytest.param({"monthly_wage": 30000}, "monthly_wage", id="wage-below-basic-wage-Art1"),
    pytest.param({"leave_days_taken": -1}, "leave_days_taken", id="negative-leave-taken"),
    pytest.param({"leave_days_taken": 31}, "leave_days_taken", id="leave-taken-over-entitlement"),
    pytest.param({"work_pattern": "flexible"}, "work_pattern", id="unknown-work-pattern"),
    pytest.param({"work_pattern": "part_time"}, "part_time_hours_ratio", id="part-time-no-ratio"),
    pytest.param(
        {"work_pattern": "part_time", "part_time_hours_ratio": 0},
        "part_time_hours_ratio",
        id="ratio-zero",
    ),
    pytest.param({"part_time_hours_ratio": 0.5}, "part_time_hours_ratio", id="ratio-for-full-time"),
    pytest.param({"reason_for_leaving": "resigned"}, "reason_for_leaving", id="unknown-argument"),
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        ANNUAL_LEAVE_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_rejects_missing_required_arguments():
    with pytest.raises(ValueError, match="end_date"):
        ANNUAL_LEAVE_TOOL.run({"start_date": "2023-01-01"})
