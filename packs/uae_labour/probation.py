"""Probation period check: Labour Law Art 9 and Art 67."""

from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import (
    check_date_order,
    check_names,
    date_arg,
    optional_date_arg,
    positive_number_arg,
)
from .rules import DAILY_RATE_QUESTION, DAYS_IN_MONTH, LABOUR_LAW, PERIODS, daily_rate, money

MAXIMUM_AND_EMPLOYER_NOTICE = Ref(LABOUR_LAW, "9", "1")
WORKER_MOVING_IN_UAE = Ref(LABOUR_LAW, "9", "3")
WORKER_LEAVING_UAE = Ref(LABOUR_LAW, "9", "4")
SHORT_NOTICE_COMPENSATION = Ref(LABOUR_LAW, "9", "5")

MAXIMUM_MONTHS = 6
MAXIMUM_DAYS = MAXIMUM_MONTHS * DAYS_IN_MONTH
NOTICE = {
    "employer": (14, [MAXIMUM_AND_EMPLOYER_NOTICE]),
    "worker_moving_in_uae": (
        DAYS_IN_MONTH,
        [MAXIMUM_AND_EMPLOYER_NOTICE, WORKER_MOVING_IN_UAE, PERIODS],
    ),
    "worker_leaving_uae": (14, [MAXIMUM_AND_EMPLOYER_NOTICE, WORKER_LEAVING_UAE]),
}


@dataclass(frozen=True)
class ProbationResult:
    probation_within_maximum: bool
    required_notice_days: int
    refs: list[Ref]
    open_questions: list[str] = field(default_factory=list)
    probation_days: int = 0
    maximum_days: int = MAXIMUM_DAYS
    maximum_months: int = MAXIMUM_MONTHS
    ended_by: str = ""
    notice_days_given: int | None = None
    notice_shortfall_days: int | None = None
    daily_wage: float | None = None
    compensation: float | None = None


def check_probation(
    *,
    start_date: date,
    ended_by: str,
    probation_end_date: date | None = None,
    notice_date: date | None = None,
    termination_date: date | None = None,
    monthly_wage: float | None = None,
) -> ProbationResult:
    """Check the probation length and the written notice owed by the party ending it.

    The probation runs from the first day of work to its last day in the contract or, without
    one, to the termination date, both inclusive. Six months are 180 days (Art 67).
    """
    last_day = probation_end_date or termination_date
    if last_day is None:
        raise ValueError("give probation_end_date or termination_date to measure the probation")
    required, notice_refs = NOTICE[ended_by]
    refs = [*notice_refs, *([] if PERIODS in notice_refs else [PERIODS])]
    probation_days = (last_day - start_date).days + 1
    checked = {
        "probation_within_maximum": probation_days <= MAXIMUM_DAYS,
        "required_notice_days": required,
        "probation_days": probation_days,
        "ended_by": ended_by,
    }
    if notice_date is None or termination_date is None:
        return ProbationResult(refs=list(refs), **checked)

    given = (termination_date - notice_date).days
    shortfall = max(required - given, 0)
    notice = {"notice_days_given": given, "notice_shortfall_days": shortfall}
    if monthly_wage is None:
        return ProbationResult(refs=list(refs), **checked, **notice)

    daily = daily_rate(Fraction(str(monthly_wage)))
    return ProbationResult(
        refs=[*refs, SHORT_NOTICE_COMPENSATION],
        open_questions=[DAILY_RATE_QUESTION],
        **checked,
        **notice,
        daily_wage=money(daily),
        compensation=money(shortfall * daily),
    )


PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start_date": {
            "type": "string",
            "description": "First day of work, when the probation period starts, YYYY-MM-DD.",
        },
        "probation_end_date": {
            "type": ["string", "null"],
            "description": (
                "Last day of the probation period in the contract, YYYY-MM-DD. Without it, the "
                "probation is measured to the termination date."
            ),
        },
        "ended_by": {
            "type": "string",
            "enum": list(NOTICE),
            "description": (
                "Who ends the contract during probation: the employer, a worker moving to "
                "another employer in the UAE, or a foreign worker leaving the UAE."
            ),
        },
        "notice_date": {
            "type": ["string", "null"],
            "description": "Date written notice was given, YYYY-MM-DD.",
        },
        "termination_date": {
            "type": ["string", "null"],
            "description": ("Date set for the end of the contract during probation, YYYY-MM-DD."),
        },
        "monthly_wage": {
            "type": ["number", "null"],
            "description": (
                "Monthly wage in AED, basic wage plus allowances. Give it to price short notice."
            ),
        },
    },
    "required": ["start_date", "ended_by"],
    "additionalProperties": False,
}


DATE_ORDER = [
    ("start_date", "probation_end_date"),
    ("start_date", "termination_date"),
    ("notice_date", "termination_date"),
    ("termination_date", "probation_end_date"),
]


def _run(args: dict[str, Any]) -> dict[str, Any]:
    check_names(args, PARAMETERS)
    if args["ended_by"] not in NOTICE:
        raise ValueError(f"ended_by must be one of {list(NOTICE)}")
    dates = {"start_date": date_arg(args, "start_date")} | {
        name: optional_date_arg(args, name)
        for name in ("probation_end_date", "notice_date", "termination_date")
    }
    if dates["notice_date"] is not None and dates["termination_date"] is None:
        raise ValueError("notice_date needs the termination_date the notice is for")
    for first, last in DATE_ORDER:
        check_date_order(dates, first, last)
    wage = positive_number_arg(args, "monthly_wage")

    return asdict(check_probation(**dates, ended_by=args["ended_by"], monthly_wage=wage))


PROBATION_TOOL = Tool(
    name="check_probation",
    description=(
        "Check a probation period, from its dates, against the UAE Labour Law: its six-month "
        "maximum (180 days), the written notice owed by the employer or the worker ending it, "
        "and, given the notice "
        "dates and wage, the compensation for short notice. Returns the articles applied and "
        "the interpretation questions the result rests on, each marked decided or open."
    ),
    parameters=PARAMETERS,
    run=_run,
)
