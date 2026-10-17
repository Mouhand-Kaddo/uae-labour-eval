"""Annual leave and its cash-out: Labour Law Art 29 and Art 67, Executive Regulations Arts 18–19."""

import math
from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import check_names, date_arg, number_arg, wages_args, whole_days_arg
from .rules import (
    DAILY_RATE_QUESTION,
    DAYS_IN_MONTH,
    DAYS_IN_YEAR,
    EXECUTIVE_REGULATIONS,
    LABOUR_LAW,
    PERIODS,
    daily_rate,
    money,
)

SERVICE_LENGTH = Ref(LABOUR_LAW, "29", "1")
PART_TIME_LEAVE = Ref(LABOUR_LAW, "29", "2")
LEAVING_BEFORE_LEAVE_IS_USED = Ref(LABOUR_LAW, "29", "9")
PART_TIME_HOURS = Ref(EXECUTIVE_REGULATIONS, "18")
CASH_OUT_ON_TERMINATION = Ref(EXECUTIVE_REGULATIONS, "19", "2")

BOUNDARIES_QUESTION = "OQ-005"
PART_TIME_QUESTION = "OQ-010"
SIX_MONTHS_OR_LESS_QUESTION = "OQ-011"
CASH_OUT_WAGE_QUESTION = "OQ-003"

SIX_MONTHS_DAYS = 6 * DAYS_IN_MONTH
DAYS_PER_MONTH_UNDER_ONE_YEAR = 2
DAYS_PER_YEAR = 30
PART_TIME_MINIMUM_DAYS_PER_YEAR = 5
WORK_PATTERNS = ("full_time", "part_time")


@dataclass(frozen=True)
class AnnualLeaveResult:
    entitlement_days: float
    balance_days: float
    cash_out: float | None
    refs: list[Ref]
    open_questions: list[str] = field(default_factory=list)
    service_days: int = 0
    whole_years: int = 0
    part_year_days: int = 0
    full_time_entitlement_days: float = 0.0
    part_time_hours_ratio: float | None = None
    leave_days_taken: int = 0
    daily_basic_wage: float | None = None


def calculate_annual_leave(
    *,
    start_date: date,
    end_date: date,
    work_pattern: str = "full_time",
    part_time_hours_ratio: float | None = None,
    leave_days_taken: int = 0,
    monthly_basic_wage: float | None = None,
) -> AnnualLeaveResult:
    """Leave earned from the first to the last day of service (both inclusive), and its cash-out.

    Raises ValueError when the leave taken exceeds the leave earned.
    """
    service_days = (end_date - start_date).days + 1
    whole_years, part_year_days = divmod(service_days, DAYS_IN_YEAR)
    refs = [SERVICE_LENGTH, PERIODS]
    open_questions = []

    if service_days < SIX_MONTHS_DAYS:
        full_time_days = Fraction(0)
        open_questions.append(SIX_MONTHS_OR_LESS_QUESTION)
    elif service_days == SIX_MONTHS_DAYS:
        full_time_days = Fraction(0)
        open_questions.append(BOUNDARIES_QUESTION)
    elif not whole_years:
        full_time_days = Fraction(service_days * DAYS_PER_MONTH_UNDER_ONE_YEAR, DAYS_IN_MONTH)
        if service_days % DAYS_IN_MONTH:
            open_questions.append(BOUNDARIES_QUESTION)
    else:
        full_time_days = whole_years * DAYS_PER_YEAR + Fraction(
            part_year_days * DAYS_PER_YEAR, DAYS_IN_YEAR
        )
        if part_year_days:
            open_questions.append(BOUNDARIES_QUESTION)

    entitlement = full_time_days
    if work_pattern == "part_time":
        refs += [PART_TIME_LEAVE, PART_TIME_HOURS]
        open_questions.append(PART_TIME_QUESTION)
        share = max(
            Fraction(str(part_time_hours_ratio)),
            Fraction(PART_TIME_MINIMUM_DAYS_PER_YEAR, DAYS_PER_YEAR),
        )
        entitlement = Fraction(math.ceil(full_time_days * share))

    if leave_days_taken > entitlement:
        raise ValueError(
            f"leave_days_taken ({leave_days_taken}) exceeds the leave earned "
            f"({float(entitlement):.2f} days)"
        )
    balance = entitlement - leave_days_taken

    cash_out = daily = None
    if monthly_basic_wage is not None:
        refs += [LEAVING_BEFORE_LEAVE_IS_USED, CASH_OUT_ON_TERMINATION]
        open_questions += [DAILY_RATE_QUESTION, CASH_OUT_WAGE_QUESTION]
        daily = daily_rate(Fraction(str(monthly_basic_wage)))
        cash_out = money(balance * daily)

    return AnnualLeaveResult(
        entitlement_days=round(float(entitlement), 2),
        balance_days=round(float(balance), 2),
        cash_out=cash_out,
        refs=refs,
        open_questions=open_questions,
        service_days=service_days,
        whole_years=whole_years,
        part_year_days=part_year_days,
        full_time_entitlement_days=round(float(full_time_days), 2),
        part_time_hours_ratio=part_time_hours_ratio,
        leave_days_taken=leave_days_taken,
        daily_basic_wage=None if daily is None else money(daily),
    )


PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start_date": {
            "type": "string",
            "description": "First day of service, YYYY-MM-DD.",
        },
        "end_date": {
            "type": "string",
            "description": (
                "Last day of service (or the date to count leave up to), YYYY-MM-DD; "
                "counted as a day of service."
            ),
        },
        "work_pattern": {
            "type": "string",
            "enum": list(WORK_PATTERNS),
            "description": "Default full_time.",
        },
        "part_time_hours_ratio": {
            "type": ["number", "null"],
            "description": (
                "Part-time only: contracted annual working hours divided by full-time annual "
                "working hours, between 0 and 1."
            ),
        },
        "leave_days_taken": {
            "type": "integer",
            "description": "Days of annual leave already taken over the service. Default 0.",
        },
        "monthly_basic_wage": {
            "type": ["number", "null"],
            "description": (
                "Monthly basic wage in AED, without allowances. Give it to get the cash value "
                "of the untaken leave."
            ),
        },
        "monthly_wage": {
            "type": ["number", "null"],
            "description": "Monthly wage in AED: basic wage plus allowances, if stated.",
        },
    },
    "required": ["start_date", "end_date"],
    "additionalProperties": False,
}


def _run(args: dict[str, Any]) -> dict[str, Any]:
    check_names(args, PARAMETERS)
    start = date_arg(args, "start_date")
    end = date_arg(args, "end_date")
    if end < start:
        raise ValueError("end_date must not be before start_date")
    basic = wages_args(args)
    taken = whole_days_arg(args, "leave_days_taken")

    pattern = args.get("work_pattern") or "full_time"
    if pattern not in WORK_PATTERNS:
        raise ValueError(f"work_pattern must be one of {list(WORK_PATTERNS)}")
    ratio = args.get("part_time_hours_ratio")
    if pattern == "part_time":
        if ratio is None or not 0 < number_arg(args, "part_time_hours_ratio") <= 1:
            raise ValueError("part_time_hours_ratio between 0 and 1 is needed for part_time")
    elif ratio is not None:
        raise ValueError("part_time_hours_ratio applies only to part_time")

    return asdict(
        calculate_annual_leave(
            start_date=start,
            end_date=end,
            work_pattern=pattern,
            part_time_hours_ratio=ratio,
            leave_days_taken=taken,
            monthly_basic_wage=basic,
        )
    )


ANNUAL_LEAVE_TOOL = Tool(
    name="calculate_annual_leave",
    description=(
        "Compute a worker's annual leave entitlement under the UAE Labour Law and its "
        "Executive Regulations from the service dates, the leave still due after leave taken, "
        "and, given the basic wage, its cash value on leaving. Returns the intermediate values, "
        "the articles applied and any open questions the result rests on."
    ),
    parameters=PARAMETERS,
    run=_run,
)
