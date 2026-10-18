"""Notice period check and pay in lieu of notice: Labour Law Art 43 and Art 67."""

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import check_names, positive_number_arg, whole_days_arg
from .rules import DAILY_RATE_QUESTION, LABOUR_LAW, PERIODS, daily_rate, money

NOTICE_RANGE = Ref(LABOUR_LAW, "43", "1")
PAY_IN_LIEU = Ref(LABOUR_LAW, "43", "3")
LAST_WAGE = Ref(LABOUR_LAW, "43", "4")
NULL_UNLESS_MORE_BENEFICIAL = Ref(LABOUR_LAW, "65", "3")

OUT_OF_RANGE_QUESTION = "OQ-012"

MINIMUM_NOTICE_DAYS = 30
MAXIMUM_NOTICE_DAYS = 90
TERMINATING_PARTIES = ("employer", "worker")


@dataclass(frozen=True)
class NoticePeriodResult:
    outcome: str
    pay_in_lieu: float | None
    refs: list[Ref]
    open_questions: list[str] = field(default_factory=list)
    notice_days: int = 0
    minimum_notice_days: int = MINIMUM_NOTICE_DAYS
    maximum_notice_days: int = MAXIMUM_NOTICE_DAYS
    terminated_by: str | None = None
    applicable_notice_days: int | None = None
    notice_days_worked: int = 0
    unserved_days: int | None = None
    daily_wage: float | None = None


def applicable_notice_days(notice_days: int, terminated_by: str | None) -> int | None:
    """The notice period that applies (OQ-012): a contract term outside 30–90 days that hurts
    the worker gives way to the nearest limit, one that helps the worker stands (Art 65(3)).

    A short term hurts the worker when the employer terminates; a long one when the worker
    resigns. Out of range and without the terminating party, it cannot be told.
    """
    if MINIMUM_NOTICE_DAYS <= notice_days <= MAXIMUM_NOTICE_DAYS:
        return notice_days
    if terminated_by is None:
        return None
    if notice_days < MINIMUM_NOTICE_DAYS:
        return MINIMUM_NOTICE_DAYS if terminated_by == "employer" else notice_days
    return MAXIMUM_NOTICE_DAYS if terminated_by == "worker" else notice_days


def check_notice_period(
    *,
    notice_days: int,
    terminated_by: str | None = None,
    notice_days_worked: int = 0,
    monthly_wage: float | None = None,
) -> NoticePeriodResult:
    """Check a contract's notice period against Art 43(1) and price the unserved applicable days."""
    applicable = applicable_notice_days(notice_days, terminated_by)
    facts = {
        "notice_days": notice_days,
        "terminated_by": terminated_by,
        "applicable_notice_days": applicable,
        "notice_days_worked": notice_days_worked,
        "unserved_days": None if applicable is None else applicable - notice_days_worked,
    }
    if notice_days < MINIMUM_NOTICE_DAYS:
        outcome = "below_minimum"
    elif notice_days > MAXIMUM_NOTICE_DAYS:
        outcome = "above_maximum"
    else:
        outcome = "within_range"
    in_range = outcome == "within_range"
    refs = [NOTICE_RANGE] if in_range else [NOTICE_RANGE, NULL_UNLESS_MORE_BENEFICIAL]
    open_questions = [] if in_range else [OUT_OF_RANGE_QUESTION]
    if monthly_wage is None or applicable is None:
        return NoticePeriodResult(outcome, None, refs, open_questions, **facts)

    daily = daily_rate(Fraction(str(monthly_wage)))
    return NoticePeriodResult(
        outcome,
        money(facts["unserved_days"] * daily),
        [*refs, PAY_IN_LIEU, LAST_WAGE, PERIODS],
        [*open_questions, DAILY_RATE_QUESTION],
        **facts,
        daily_wage=money(daily),
    )


PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "notice_days": {
            "type": "integer",
            "description": "Notice period agreed in the employment contract, in days.",
        },
        "terminated_by": {
            "type": ["string", "null"],
            "enum": [*TERMINATING_PARTIES, None],
            "description": (
                "Who ends the contract: the employer, or the worker by resigning. Needed when "
                "the contract's notice period is outside 30–90 days."
            ),
        },
        "notice_days_worked": {
            "type": "integer",
            "description": (
                "Days of the applicable notice period actually worked or honoured. Default 0."
            ),
        },
        "monthly_wage": {
            "type": ["number", "null"],
            "description": (
                "Last monthly wage in AED, basic wage plus allowances, for a worker paid by "
                "month, week, day or hour. Give it to price the unserved notice."
            ),
        },
    },
    "required": ["notice_days"],
    "additionalProperties": False,
}


def _run(args: dict[str, Any]) -> dict[str, Any]:
    check_names(args, PARAMETERS)
    notice_days = args["notice_days"]
    if not isinstance(notice_days, int) or isinstance(notice_days, bool) or notice_days <= 0:
        raise ValueError("notice_days must be a whole number of days, more than 0")
    terminated_by = args.get("terminated_by")
    if terminated_by is not None and terminated_by not in TERMINATING_PARTIES:
        raise ValueError(f"terminated_by must be one of {list(TERMINATING_PARTIES)}")
    worked = whole_days_arg(args, "notice_days_worked")
    if worked > (applicable_notice_days(notice_days, terminated_by) or notice_days):
        raise ValueError("notice_days_worked cannot exceed the applicable notice period")
    wage = positive_number_arg(args, "monthly_wage")

    return asdict(
        check_notice_period(
            notice_days=notice_days,
            terminated_by=terminated_by,
            notice_days_worked=worked,
            monthly_wage=wage,
        )
    )


NOTICE_PERIOD_TOOL = Tool(
    name="check_notice_period",
    description=(
        "Check whether an employment contract's notice period is within the UAE Labour Law's "
        "limits, find the period that applies when it is not (given who terminates), and, "
        "given the last wage, compute the pay in lieu of notice owed for the days not worked. "
        "Returns the articles applied and the interpretation questions "
        "the result rests on, each marked decided or open."
    ),
    parameters=PARAMETERS,
    run=_run,
)
