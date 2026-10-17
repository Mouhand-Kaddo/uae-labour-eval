"""Gratuity calculation: Labour Law Arts 51, 52 and 67, Executive Regulations Art 30."""

from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import (
    check_names,
    hours_ratio_arg,
    ordered_dates_arg,
    wages_args,
    whole_days_arg,
    work_pattern_arg,
)
from .rules import (
    DAILY_RATE_QUESTION,
    DAYS_IN_YEAR,
    EXECUTIVE_REGULATIONS,
    FLEXIBLE,
    FULL_TIME,
    JOB_SHARING,
    LABOUR_LAW,
    PART_TIME,
    PERIODS,
    TEMPORARY,
    daily_rate,
    money,
)

NATIONAL_WORKER = Ref(LABOUR_LAW, "51", "1")
QUALIFYING_YEAR_AND_RATES = Ref(LABOUR_LAW, "51", "2")
PART_YEARS = Ref(LABOUR_LAW, "51", "3")
UNPAID_ABSENCE = Ref(LABOUR_LAW, "51", "4")
LAST_BASIC_WAGE = Ref(LABOUR_LAW, "51", "5")
CAP = Ref(LABOUR_LAW, "51", "6")
OTHER_WORK_PATTERNS = Ref(LABOUR_LAW, "52")
PRO_RATA = Ref(EXECUTIVE_REGULATIONS, "30", "1")
TEMPORARY_WORK = Ref(EXECUTIVE_REGULATIONS, "30", "2")

CAP_QUESTION = "OQ-002"
PRO_RATA_QUESTION = "OQ-008"
TEMPORARY_WORK_QUESTION = "OQ-006"
FLEXIBLE_WORK_QUESTION = "OQ-009"

FIRST_YEARS_DAYS = 5 * DAYS_IN_YEAR
DAYS_PER_YEAR_FIRST_FIVE = 21
DAYS_PER_YEAR_AFTER_FIVE = 30
CAP_MONTHS = 24
PRO_RATA_PATTERNS = (PART_TIME, JOB_SHARING)


@dataclass(frozen=True)
class GratuityResult:
    outcome: str
    gratuity: float | None
    refs: list[Ref]
    open_questions: list[str] = field(default_factory=list)
    service_days: int | None = None
    unpaid_absence_days: int | None = None
    counted_service_days: int | None = None
    service_days_at_21_day_rate: int | None = None
    service_days_at_30_day_rate: int | None = None
    gratuity_days: float | None = None
    daily_basic_wage: float | None = None
    uncapped_gratuity: float | None = None
    cap: float | None = None
    cap_applied: bool | None = None
    part_time_hours_ratio: float | None = None


def calculate_gratuity(
    *,
    start_date: date,
    end_date: date,
    monthly_basic_wage: float,
    nationality: str,
    work_pattern: str,
    unpaid_absence_days: int = 0,
    part_time_hours_ratio: float | None = None,
) -> GratuityResult:
    """Gratuity for service from the first day to the last day of service, both inclusive."""
    if nationality == "national":
        return GratuityResult("national_worker", None, [NATIONAL_WORKER])
    if work_pattern == TEMPORARY:
        return GratuityResult("temporary_work", None, [TEMPORARY_WORK], [TEMPORARY_WORK_QUESTION])
    if work_pattern == FLEXIBLE:
        return GratuityResult(
            "flexible_work_undecided",
            None,
            [OTHER_WORK_PATTERNS, PRO_RATA],
            [FLEXIBLE_WORK_QUESTION],
        )

    service_days = (end_date - start_date).days + 1
    counted_days = service_days - unpaid_absence_days
    service = {
        "service_days": service_days,
        "unpaid_absence_days": unpaid_absence_days,
        "counted_service_days": counted_days,
    }
    refs = [QUALIFYING_YEAR_AND_RATES, PERIODS]
    if unpaid_absence_days:
        refs.append(UNPAID_ABSENCE)
    if counted_days < DAYS_IN_YEAR:
        return GratuityResult("under_one_year", 0.0, refs, **service)

    if counted_days % DAYS_IN_YEAR:
        refs.append(PART_YEARS)
    refs += [LAST_BASIC_WAGE, CAP]
    open_questions = [DAILY_RATE_QUESTION, CAP_QUESTION]

    basic = Fraction(str(monthly_basic_wage))
    daily = daily_rate(basic)
    days_at_21 = min(counted_days, FIRST_YEARS_DAYS)
    days_at_30 = counted_days - days_at_21
    gratuity_days = Fraction(
        days_at_21 * DAYS_PER_YEAR_FIRST_FIVE + days_at_30 * DAYS_PER_YEAR_AFTER_FIVE,
        DAYS_IN_YEAR,
    )
    uncapped = gratuity_days * daily
    cap = CAP_MONTHS * basic
    amount = min(uncapped, cap)

    if work_pattern in PRO_RATA_PATTERNS:
        refs.append(PRO_RATA)
        open_questions.append(PRO_RATA_QUESTION)
        amount *= Fraction(str(part_time_hours_ratio))

    return GratuityResult(
        "calculated",
        money(amount),
        refs,
        open_questions,
        **service,
        service_days_at_21_day_rate=days_at_21,
        service_days_at_30_day_rate=days_at_30,
        gratuity_days=round(float(gratuity_days), 4),
        daily_basic_wage=money(daily),
        uncapped_gratuity=money(uncapped),
        cap=money(cap),
        cap_applied=uncapped > cap,
        part_time_hours_ratio=part_time_hours_ratio,
    )


WORK_PATTERNS = (FULL_TIME, *PRO_RATA_PATTERNS, TEMPORARY, FLEXIBLE)
NATIONALITIES = ("foreign", "national")

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start_date": {
            "type": "string",
            "description": "First day of service, YYYY-MM-DD.",
        },
        "end_date": {
            "type": "string",
            "description": "Last day of service, YYYY-MM-DD; counted as a day of service.",
        },
        "monthly_basic_wage": {
            "type": "number",
            "description": "Last monthly basic wage in AED, without allowances.",
        },
        "monthly_wage": {
            "type": ["number", "null"],
            "description": "Last monthly wage in AED: basic wage plus allowances, if stated.",
        },
        "unpaid_absence_days": {
            "type": "integer",
            "description": "Days of absence from work without pay. Default 0.",
        },
        "work_pattern": {"type": "string", "enum": list(WORK_PATTERNS)},
        "part_time_hours_ratio": {
            "type": ["number", "null"],
            "description": (
                "Part-time or job sharing only: contracted annual working hours divided by "
                "full-time annual working hours, between 0 and 1."
            ),
        },
        "nationality": {"type": "string", "enum": list(NATIONALITIES)},
    },
    "required": ["start_date", "end_date", "monthly_basic_wage", "work_pattern", "nationality"],
    "additionalProperties": False,
}


def _run(args: dict[str, Any]) -> dict[str, Any]:
    check_names(args, PARAMETERS)
    start, end = ordered_dates_arg(args, "start_date", "end_date")
    basic = wages_args(args)

    absence = whole_days_arg(args, "unpaid_absence_days")
    if absence > (end - start).days + 1:
        raise ValueError("unpaid_absence_days cannot exceed the days of service")

    pattern = work_pattern_arg(args, WORK_PATTERNS)
    ratio = hours_ratio_arg(args, pattern, PRO_RATA_PATTERNS)
    if args["nationality"] not in NATIONALITIES:
        raise ValueError(f"nationality must be one of {list(NATIONALITIES)}")

    return asdict(
        calculate_gratuity(
            start_date=start,
            end_date=end,
            monthly_basic_wage=basic,
            nationality=args["nationality"],
            work_pattern=pattern,
            unpaid_absence_days=absence,
            part_time_hours_ratio=ratio,
        )
    )


GRATUITY_TOOL = Tool(
    name="calculate_gratuity",
    description=(
        "Compute the end-of-service gratuity under the UAE Labour Law and its Executive "
        "Regulations from the worker's stated facts. Returns the amount in AED, the "
        "intermediate values, the articles applied and the interpretation questions "
        "the result rests on, each marked decided or open."
    ),
    parameters=PARAMETERS,
    run=_run,
)
