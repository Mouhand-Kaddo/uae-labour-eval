import json
from datetime import date

import pytest
from uae_labour.gratuity import GRATUITY_TOOL, calculate_gratuity

DAILY_1200 = 36500


def service(start, end, monthly_basic_wage, **extra):
    return {
        "start_date": start,
        "end_date": end,
        "monthly_basic_wage": monthly_basic_wage,
        "nationality": "foreign",
        "work_pattern": "full_time",
        **extra,
    }


FULL_TIME_AMOUNTS = [
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30), DAILY_1200),
        364,
        0.00,
        "364 days < 365: no year of continuous service completed, nothing due",
        id="Art51(2)-under-one-year",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 31), DAILY_1200),
        365,
        25200.00,
        "daily 36,500 × 12 ÷ 365 = 1,200; 21 days × 1,200 = 25,200",
        id="Art51(2)(a)-exactly-one-year",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 7, 1), DAILY_1200),
        547,
        37765.48,
        "365 (2021) + 31+28+31+30+31+30+1 = 547 days; 547 × 21 ÷ 365 = 11,487/365 days; "
        "× 1,200 = 13,784,400 / 365 = 37,765.479 → 37,765.48",
        id="Art51(3)-part-year-after-one-year",
    ),
    pytest.param(
        service(date(2019, 1, 1), date(2023, 12, 30), DAILY_1200),
        1825,
        126000.00,
        "365+366+365+365+364 = 1,825 days = 5 years; 5 × 21 = 105 days × 1,200 = 126,000",
        id="Art51(2)(a)-five-year-boundary",
    ),
    pytest.param(
        service(date(2018, 1, 1), date(2023, 12, 30), DAILY_1200),
        2190,
        162000.00,
        "1,825 + 365 = 2,190 days; 105 days + 1 year × 30 days = 135 days × 1,200 = 162,000",
        id="Art51(2)(b)-sixth-year-at-30-days",
    ),
    pytest.param(
        service(date(2019, 1, 1), date(2024, 6, 22), DAILY_1200),
        2000,
        143260.27,
        "1,826 days to 2023-12-31 + 174 days of 2024 = 2,000; 1,825 at 21 → 105 days; "
        "175 at 30 → 5,250/365 days; 126,000 + 5,250 × 1,200 / 365 = 126,000 + 17,260.27",
        id="Art51(2)(b)+Art51(3)-part-year-beyond-five",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 31), 10000),
        365,
        6904.11,
        "daily 10,000 × 12 ÷ 365 = 328.767; 21 × 10,000 × 12 / 365 = 2,520,000 / 365 = 6,904.11 "
        "(÷30 would give 7,000)",
        id="Art51(2)(a)+OQ-001-daily-rate-is-monthly-x12-div365",
    ),
    pytest.param(
        service(date(2024, 1, 1), date(2024, 12, 31), DAILY_1200),
        366,
        25269.04,
        "leap year 366 days; a year is 365 days, so 366 × 21 / 365 days × 1,200 "
        "= 9,223,200 / 365 = 25,269.04",
        id="Art67-year-is-365-days-in-a-leap-year",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 12, 31), DAILY_1200, unpaid_absence_days=30),
        700,
        48328.77,
        "730 calendar days − 30 unpaid = 700; 700 × 21 / 365 days × 1,200 "
        "= 17,640,000 / 365 = 48,328.77",
        id="Art51(4)-unpaid-absence-excluded",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2024, 1, 10), DAILY_1200, unpaid_absence_days=11),
        364,
        0.00,
        "365 + 10 = 375 calendar days − 11 unpaid = 364 < 365: no year completed",
        id="Art51(4)+Art51(2)-unpaid-absence-keeps-service-under-one-year",
    ),
    pytest.param(
        service(date(1980, 1, 1), date(2009, 12, 31), DAILY_1200),
        10958,
        876000.00,
        "30 years incl. 8 leap days = 10,958 days; 105 days + (10,958 − 1,825) × 30 / 365 "
        "= 105 + 750.66 = 855.66 days × 1,200 = 1,026,789.04; cap 24 × 36,500 = 876,000",
        id="Art51(6)+OQ-002-cap-is-two-years-basic-wage",
    ),
    pytest.param(
        service(date(2000, 1, 1), date(2024, 12, 25), DAILY_1200),
        9126,
        846098.63,
        "9,126 days; 105 + (9,126 − 1,825) × 30 / 365 = 105 + 219,030/365 days; "
        "126,000 + 219,030 × 1,200 / 365 = 126,000 + 720,098.63 = 846,098.63",
        id="Art51(6)-just-under-the-cap",
    ),
]


@pytest.mark.parametrize(("facts", "counted_days", "expected", "working"), FULL_TIME_AMOUNTS)
def test_full_time_foreign_worker_gratuity(facts, counted_days, expected, working):
    result = calculate_gratuity(**facts)

    assert result.counted_service_days == counted_days
    assert result.gratuity == expected, working


THREE_YEARS = (date(2021, 1, 1), date(2023, 12, 31), DAILY_1200)

PRO_RATA_AMOUNTS = [
    pytest.param(
        service(*THREE_YEARS, work_pattern="part_time", part_time_hours_ratio=0.5),
        75600.00,
        "own basic 36,500 at 50% hours → full-time equivalent 73,000, daily 2,400; "
        "1,095 days → 63 days × 2,400 = 151,200 under a full-time contract; × 50% = 75,600",
        id="ER30(1)+OQ-008-part-time-on-the-full-time-equivalent-wage",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="job_sharing", part_time_hours_ratio=0.25),
        75600.00,
        "own basic 36,500 at 25% → full-time equivalent 146,000, daily 4,800; "
        "63 × 4,800 = 302,400; × 25% = 75,600",
        id="ER30(1)+ER5(1)(b)+OQ-008-job-sharing-on-the-full-time-equivalent-wage",
    ),
    pytest.param(
        service(
            date(2020, 1, 1),
            date(2022, 12, 31),
            7300,
            work_pattern="part_time",
            part_time_hours_ratio=0.6,
        ),
        15133.81,
        "1,096 days; own basic 7,300 is 60% of 12,166.67; under a full-time contract "
        "1,096 × 21 / 365 days × 12,166.67 × 12 / 365 = 25,223.01; × 60% = 15,133.81 "
        "(Art 51 on the own wage: 1,096 × 21 / 365 × 240 = 5,523,840 / 365)",
        id="ER30(1)+OQ-008-hours-reduction-applied-once",
    ),
    pytest.param(
        service(
            date(1980, 1, 1),
            date(2009, 12, 31),
            DAILY_1200,
            work_pattern="part_time",
            part_time_hours_ratio=0.5,
        ),
        876000.00,
        "full-time equivalent 73,000: 855.66 days × 2,400 = 2,053,578.08, capped at "
        "24 × 73,000 = 1,752,000; × 50% = 876,000",
        id="ER30(1)+Art51(6)-pro-rata-of-the-capped-full-time-value",
    ),
    pytest.param(
        service(
            date(2023, 1, 1),
            date(2023, 12, 30),
            DAILY_1200,
            work_pattern="part_time",
            part_time_hours_ratio=0.5,
        ),
        0.00,
        "364 days: full-time value is 0 (Art 51(2)), and 50% of 0 is 0",
        id="ER30(1)+Art51(2)-part-time-under-one-year",
    ),
]


@pytest.mark.parametrize(("facts", "expected", "working"), PRO_RATA_AMOUNTS)
def test_part_time_and_job_sharing_gratuity(facts, expected, working):
    assert calculate_gratuity(**facts).gratuity == expected, working


def test_er_30_1_result_shows_the_full_time_equivalent_wage_and_full_time_value():
    result = calculate_gratuity(
        **service(*THREE_YEARS, work_pattern="part_time", part_time_hours_ratio=0.5)
    )

    assert result.full_time_equivalent_basic_wage == 73000.00
    assert result.daily_basic_wage == 2400.00
    assert result.uncapped_gratuity == 151200.00
    assert result.gratuity == 75600.00


NOT_APPLICABLE = [
    pytest.param(
        service(*THREE_YEARS, nationality="national"),
        "national_worker",
        id="Art51(1)-national-worker-under-pensions-law",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="flexible"),
        "flexible_hours_not_stated",
        id="Art52+OQ-009-flexible-work-without-contracted-hours",
    ),
]


TEMPORARY_AMOUNTS = [
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30), DAILY_1200, work_pattern="temporary"),
        "temporary_under_one_year",
        0.00,
        "364 days < 365: temporary work under a year earns nothing (ER 30(2), Arabic)",
        id="ER30(2)+OQ-006-temporary-under-one-year",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="temporary"),
        "calculated",
        75600.00,
        "1,095 days on full-time hours: Art 51 as for full time, 63 days × 1,200 = 75,600",
        id="ER30(2)+OQ-006-temporary-one-year-or-more-on-full-time-hours",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2024, 6, 30), 9000, work_pattern="temporary"),
        "calculated",
        9312.04,
        "366 + 181 = 547 days; 547 × 21 / 365 = 11,487 / 365 days × (9,000 × 12 / 365) "
        "= 1,240,596,000 / 133,225 = 9,312.04",
        id="ER30(2)+Art51(3)+OQ-006-temporary-part-year-after-one-year",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="temporary", part_time_hours_ratio=0.5),
        "calculated",
        75600.00,
        "reduced hours: own basic 36,500 at 50% → full-time equivalent 73,000; "
        "63 × 2,400 = 151,200 × 50% = 75,600 (Art 51 × hours ratio, OQ-006 and OQ-008)",
        id="ER30(1)+OQ-006-temporary-on-reduced-hours",
    ),
]

FLEXIBLE_AMOUNTS = [
    pytest.param(
        service(*THREE_YEARS, work_pattern="flexible", part_time_hours_ratio=0.5),
        "calculated",
        75600.00,
        "contracted hours 50%: full-time equivalent 73,000, 63 × 2,400 = 151,200 × 50% = 75,600",
        id="Art52+ER30(1)+OQ-009-flexible-on-contracted-hours",
    ),
    pytest.param(
        service(
            date(2023, 1, 1),
            date(2023, 12, 30),
            DAILY_1200,
            work_pattern="flexible",
            part_time_hours_ratio=0.5,
        ),
        "under_one_year",
        0.00,
        "364 days < 365: the full-time value is 0 (Art 51(2)), so 50% of it is 0",
        id="Art51(2)+ER30(1)+OQ-009-flexible-under-one-year",
    ),
]


@pytest.mark.parametrize(("facts", "outcome", "expected", "working"), FLEXIBLE_AMOUNTS)
def test_flexible_work_is_pro_rated_on_contracted_hours(facts, outcome, expected, working):
    result = calculate_gratuity(**facts)

    assert result.outcome == outcome
    assert result.gratuity == expected, working


@pytest.mark.parametrize(("facts", "outcome", "expected", "working"), TEMPORARY_AMOUNTS)
def test_temporary_work_earns_gratuity_only_from_one_year(facts, outcome, expected, working):
    result = calculate_gratuity(**facts)

    assert result.outcome == outcome
    assert result.gratuity == expected, working


@pytest.mark.parametrize(("facts", "outcome"), NOT_APPLICABLE)
def test_labour_law_gratuity_does_not_apply(facts, outcome):
    result = calculate_gratuity(**facts)

    assert result.outcome == outcome
    assert result.gratuity is None


CALCULATED = {
    "Labour Law Art 51(2)",
    "Labour Law Art 51(5)",
    "Labour Law Art 51(6)",
    "Labour Law Art 67",
}

REFS_AND_QUESTIONS = [
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30), DAILY_1200),
        {"Labour Law Art 51(2)", "Labour Law Art 67"},
        [],
        id="Art51(2)-under-one-year",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 31), DAILY_1200),
        CALCULATED,
        ["OQ-001", "OQ-002"],
        id="Art51(2)-whole-years",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 7, 1), DAILY_1200),
        CALCULATED | {"Labour Law Art 51(3)"},
        ["OQ-001", "OQ-002"],
        id="Art51(3)-part-year",
    ),
    pytest.param(
        service(date(2021, 1, 1), date(2022, 12, 31), DAILY_1200, unpaid_absence_days=30),
        CALCULATED | {"Labour Law Art 51(3)", "Labour Law Art 51(4)"},
        ["OQ-001", "OQ-002"],
        id="Art51(4)-unpaid-absence",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="part_time", part_time_hours_ratio=0.5),
        CALCULATED | {"Executive Regulations Art 30(1)"},
        ["OQ-001", "OQ-002", "OQ-008"],
        id="ER30(1)-part-time",
    ),
    pytest.param(
        service(*THREE_YEARS, nationality="national"),
        {"Labour Law Art 51(1)"},
        [],
        id="Art51(1)-national-worker",
    ),
    pytest.param(
        service(
            date(2023, 1, 1),
            date(2023, 12, 30),
            DAILY_1200,
            work_pattern="part_time",
            part_time_hours_ratio=0.5,
        ),
        {
            "Labour Law Art 51(2)",
            "Labour Law Art 51(3)",
            "Executive Regulations Art 30(1)",
            "Labour Law Art 67",
        },
        [],
        id="Art51(2)(3)+ER30(1)-part-time-under-one-year-not-ER30(2)",
    ),
    pytest.param(
        service(date(2023, 1, 1), date(2023, 12, 30), DAILY_1200, work_pattern="temporary"),
        {"Executive Regulations Art 30(2)", "Labour Law Art 67"},
        [],
        id="ER30(2)-temporary-under-one-year-same-in-both-languages",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="temporary"),
        CALCULATED | {"Executive Regulations Art 30(2)"},
        ["OQ-001", "OQ-002", "OQ-006"],
        id="ER30(2)+OQ-006-temporary-one-year-or-more",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="temporary", part_time_hours_ratio=0.5),
        CALCULATED | {"Executive Regulations Art 30(1)", "Executive Regulations Art 30(2)"},
        ["OQ-001", "OQ-002", "OQ-008", "OQ-006"],
        id="ER30(1)+ER30(2)+OQ-006+OQ-008-temporary-on-reduced-hours",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="flexible"),
        {"Labour Law Art 52", "Executive Regulations Art 30(1)"},
        ["OQ-009"],
        id="Art52+OQ-009-flexible-work-without-contracted-hours",
    ),
    pytest.param(
        service(*THREE_YEARS, work_pattern="flexible", part_time_hours_ratio=0.5),
        CALCULATED | {"Labour Law Art 52", "Executive Regulations Art 30(1)"},
        ["OQ-001", "OQ-002", "OQ-008", "OQ-009"],
        id="Art52+ER30(1)+OQ-009-flexible-on-contracted-hours",
    ),
    pytest.param(
        service(
            date(2023, 1, 1),
            date(2023, 12, 30),
            DAILY_1200,
            work_pattern="flexible",
            part_time_hours_ratio=0.5,
        ),
        {
            "Labour Law Art 51(2)",
            "Labour Law Art 51(3)",
            "Labour Law Art 52",
            "Executive Regulations Art 30(1)",
            "Labour Law Art 67",
        },
        ["OQ-009"],
        id="Art51(2)+Art52+ER30(1)+OQ-009-flexible-under-one-year",
    ),
]


@pytest.mark.parametrize(("facts", "refs", "open_questions"), REFS_AND_QUESTIONS)
def test_result_returns_the_articles_and_open_questions_it_used(facts, refs, open_questions):
    result = calculate_gratuity(**facts)

    assert {str(ref) for ref in result.refs} == refs
    assert result.open_questions == open_questions


def test_art_51_6_result_shows_days_at_each_rate_and_the_cap():
    result = calculate_gratuity(**service(date(1980, 1, 1), date(2009, 12, 31), DAILY_1200))

    assert result.service_days == 10958
    assert result.service_days_at_21_day_rate == 1825
    assert result.service_days_at_30_day_rate == 9133
    assert result.daily_basic_wage == 1200.00
    assert result.uncapped_gratuity == 1026789.04
    assert result.cap == 876000.00
    assert result.cap_applied is True
    assert result.gratuity == 876000.00


TOOL_ARGS = {
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "monthly_basic_wage": 36500,
    "monthly_wage": 50000,
    "unpaid_absence_days": 0,
    "work_pattern": "full_time",
    "part_time_hours_ratio": None,
    "nationality": "foreign",
}


def test_tool_takes_json_arguments_and_returns_refs_as_data():
    result = GRATUITY_TOOL.run(TOOL_ARGS)

    assert GRATUITY_TOOL.name == "calculate_gratuity"
    assert result["gratuity"] == 25200.00
    assert result["outcome"] == "calculated"
    assert {"instrument": "Labour Law", "article": "51", "clause": "2"} in result["refs"]
    assert result["open_questions"] == ["OQ-001", "OQ-002"]
    json.dumps(result)


def test_tool_needs_only_dates_basic_wage_pattern_and_nationality():
    minimal = {
        k: TOOL_ARGS[k]
        for k in ("start_date", "end_date", "monthly_basic_wage", "work_pattern", "nationality")
    }

    assert GRATUITY_TOOL.run(minimal)["gratuity"] == 25200.00
    assert set(GRATUITY_TOOL.parameters["required"]) == set(minimal)


BAD_ARGUMENTS = [
    pytest.param({"start_date": "01/01/2023"}, "start_date", id="date-not-iso"),
    pytest.param({"end_date": "2022-12-31"}, "end_date", id="end-before-start"),
    pytest.param({"monthly_basic_wage": 0}, "monthly_basic_wage", id="basic-wage-not-positive"),
    pytest.param({"monthly_basic_wage": "36500"}, "monthly_basic_wage", id="basic-wage-not-number"),
    pytest.param({"monthly_basic_wage": None}, "monthly_basic_wage", id="basic-wage-null"),
    pytest.param({"monthly_wage": 30000}, "monthly_wage", id="wage-below-basic-wage-Art1"),
    pytest.param({"unpaid_absence_days": -1}, "unpaid_absence_days", id="negative-absence"),
    pytest.param({"unpaid_absence_days": 1.5}, "unpaid_absence_days", id="part-day-absence"),
    pytest.param({"unpaid_absence_days": 366}, "unpaid_absence_days", id="absence-over-service"),
    pytest.param({"work_pattern": "remote"}, "work_pattern", id="unknown-work-pattern"),
    pytest.param({"work_pattern": "part_time"}, "part_time_hours_ratio", id="part-time-no-ratio"),
    pytest.param(
        {"work_pattern": "part_time", "part_time_hours_ratio": 1.5},
        "part_time_hours_ratio",
        id="ratio-above-one",
    ),
    pytest.param({"part_time_hours_ratio": 0.5}, "part_time_hours_ratio", id="ratio-for-full-time"),
    pytest.param({"nationality": "emirati"}, "nationality", id="unknown-nationality"),
    pytest.param({"reason_for_leaving": "resigned"}, "reason_for_leaving", id="unknown-argument"),
]


@pytest.mark.parametrize(("changes", "named"), BAD_ARGUMENTS)
def test_tool_rejects_bad_arguments_with_a_message_naming_the_problem(changes, named):
    with pytest.raises(ValueError, match=named):
        GRATUITY_TOOL.run({**TOOL_ARGS, **changes})


def test_tool_answers_flexible_work_without_contracted_hours_with_no_amount_OQ_009():
    result = GRATUITY_TOOL.run({**TOOL_ARGS, "work_pattern": "flexible"})

    assert (result["outcome"], result["gratuity"]) == ("flexible_hours_not_stated", None)
    assert result["open_questions"] == ["OQ-009"]
    assert {"instrument": "Labour Law", "article": "52", "clause": None} in result["refs"]


def test_tool_rejects_missing_required_arguments():
    args = dict(TOOL_ARGS)
    del args["nationality"]

    with pytest.raises(ValueError, match="nationality"):
        GRATUITY_TOOL.run(args)


@pytest.mark.parametrize(
    "ratio",
    [pytest.param(None, id="full-time-hours"), pytest.param(0.5, id="reduced-hours")],
)
def test_tool_takes_an_optional_hours_ratio_for_temporary_work_OQ_006(ratio):
    result = GRATUITY_TOOL.run(
        {**TOOL_ARGS, "work_pattern": "temporary", "part_time_hours_ratio": ratio}
    )

    assert (result["outcome"], result["gratuity"]) == ("calculated", 25200.00)


def test_tool_computes_flexible_work_given_the_contracted_hours_ratio_OQ_009():
    result = GRATUITY_TOOL.run(
        {**TOOL_ARGS, "work_pattern": "flexible", "part_time_hours_ratio": 0.5}
    )

    assert (result["outcome"], result["gratuity"]) == ("calculated", 25200.00)
