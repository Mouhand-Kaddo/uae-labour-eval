"""Probation period check: Labour Law Art 9 and Art 67."""

from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import check_names, number_arg, ordered_dates_arg, positive_number_arg
from .rules import DAILY_RATE_QUESTION, DAYS_IN_MONTH, LABOUR_LAW, PERIODS, daily_rate, money

MAXIMUM_AND_EMPLOYER_NOTICE = Ref(LABOUR_LAW, "9", "1")
WORKER_MOVING_IN_UAE = Ref(LABOUR_LAW, "9", "3")
WORKER_LEAVING_UAE = Ref(LABOUR_LAW, "9", "4")
SHORT_NOTICE_COMPENSATION = Ref(LABOUR_LAW, "9", "5")

MAXIMUM_MONTHS = 6
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
    probation_months: float = 0
    maximum_months: int = MAXIMUM_MONTHS
    ended_by: str = ""
    notice_days_given: int | None = None
    notice_shortfall_days: int | None = None
    daily_wage: float | None = None
    compensation: float | None = None


def check_probation(
    *,
    probation_months: float,
    ended_by: str,
    notice_date: date | None = None,
    termination_date: date | None = None,
    monthly_wage: float | None = None,
) -> ProbationResult:
    """Check the probation length and the written notice owed by the party ending it."""
    required, refs = NOTICE[ended_by]
    checked = {
        "probation_within_maximum": probation_months <= MAXIMUM_MONTHS,
        "required_notice_days": required,
        "probation_months": probation_months,
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
        refs=[*refs, SHORT_NOTICE_COMPENSATION, *([] if PERIODS in refs else [PERIODS])],
        open_questions=[DAILY_RATE_QUESTION],
        **checked,
        **notice,
        daily_wage=money(daily),
        compensation=money(shortfall * daily),
    )


PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "probation_months": {
            "type": "number",
            "description": "Length of the probation period in the contract, in months.",
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
            "description": "Date set for the end of the contract, YYYY-MM-DD.",
        },
        "monthly_wage": {
            "type": ["number", "null"],
            "description": (
                "Monthly wage in AED, basic wage plus allowances. Give it to price short notice."
            ),
        },
    },
    "required": ["probation_months", "ended_by"],
    "additionalProperties": False,
}


def _run(args: dict[str, Any]) -> dict[str, Any]:
    check_names(args, PARAMETERS)
    if number_arg(args, "probation_months") <= 0:
        raise ValueError("probation_months must be positive")
    if args["ended_by"] not in NOTICE:
        raise ValueError(f"ended_by must be one of {list(NOTICE)}")

    has_dates = [args.get(name) is not None for name in ("notice_date", "termination_date")]
    notice_date = termination_date = None
    if any(has_dates):
        if not all(has_dates):
            raise ValueError("give both notice_date and termination_date, or neither")
        notice_date, termination_date = ordered_dates_arg(args, "notice_date", "termination_date")

    wage = positive_number_arg(args, "monthly_wage")

    return asdict(
        check_probation(
            probation_months=args["probation_months"],
            ended_by=args["ended_by"],
            notice_date=notice_date,
            termination_date=termination_date,
            monthly_wage=wage,
        )
    )


PROBATION_TOOL = Tool(
    name="check_probation",
    description=(
        "Check a probation period against the UAE Labour Law: its six-month maximum, the "
        "written notice owed by the employer or the worker ending it, and, given the notice "
        "dates and wage, the compensation for short notice. Returns the articles applied and "
        "the interpretation questions the result rests on, each marked decided or open."
    ),
    parameters=PARAMETERS,
    run=_run,
)
