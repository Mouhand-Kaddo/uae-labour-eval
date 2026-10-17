"""Notice period check and pay in lieu of notice: Labour Law Art 43 and Art 67."""

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any

from eval_harness.agent import Tool
from eval_harness.refs import Ref

from .arguments import check_names, number_arg, whole_days_arg
from .rules import DAILY_RATE_QUESTION, LABOUR_LAW, PERIODS, daily_rate, money

NOTICE_RANGE = Ref(LABOUR_LAW, "43", "1")
PAY_IN_LIEU = Ref(LABOUR_LAW, "43", "3")
LAST_WAGE = Ref(LABOUR_LAW, "43", "4")

OUT_OF_RANGE_QUESTION = "OQ-012"

MINIMUM_NOTICE_DAYS = 30
MAXIMUM_NOTICE_DAYS = 90


@dataclass(frozen=True)
class NoticePeriodResult:
    outcome: str
    pay_in_lieu: float | None
    refs: list[Ref]
    open_questions: list[str] = field(default_factory=list)
    notice_days: int = 0
    minimum_notice_days: int = MINIMUM_NOTICE_DAYS
    maximum_notice_days: int = MAXIMUM_NOTICE_DAYS
    notice_days_worked: int = 0
    unserved_days: int = 0
    daily_wage: float | None = None


def check_notice_period(
    *,
    notice_days: int,
    notice_days_worked: int = 0,
    monthly_wage: float | None = None,
) -> NoticePeriodResult:
    """Check a contract's notice period against Art 43(1); price the unserved days if in range."""
    facts = {
        "notice_days": notice_days,
        "notice_days_worked": notice_days_worked,
        "unserved_days": notice_days - notice_days_worked,
    }
    if notice_days < MINIMUM_NOTICE_DAYS or notice_days > MAXIMUM_NOTICE_DAYS:
        outcome = "below_minimum" if notice_days < MINIMUM_NOTICE_DAYS else "above_maximum"
        return NoticePeriodResult(outcome, None, [NOTICE_RANGE], [OUT_OF_RANGE_QUESTION], **facts)
    if monthly_wage is None:
        return NoticePeriodResult("within_range", None, [NOTICE_RANGE], **facts)

    daily = daily_rate(Fraction(str(monthly_wage)))
    return NoticePeriodResult(
        "within_range",
        money(facts["unserved_days"] * daily),
        [NOTICE_RANGE, PAY_IN_LIEU, LAST_WAGE, PERIODS],
        [DAILY_RATE_QUESTION],
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
        "notice_days_worked": {
            "type": "integer",
            "description": "Days of the notice period actually worked or honoured. Default 0.",
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
    worked = whole_days_arg(args, "notice_days_worked")
    if worked > notice_days:
        raise ValueError("notice_days_worked cannot exceed notice_days")
    wage = args.get("monthly_wage")
    if wage is not None and number_arg(args, "monthly_wage") <= 0:
        raise ValueError("monthly_wage must be positive")

    return asdict(
        check_notice_period(notice_days=notice_days, notice_days_worked=worked, monthly_wage=wage)
    )


NOTICE_PERIOD_TOOL = Tool(
    name="check_notice_period",
    description=(
        "Check whether an employment contract's notice period is within the UAE Labour Law's "
        "limits and, given the last wage, compute the pay in lieu of notice owed for the days "
        "not worked. Returns the articles applied and any open questions the result rests on."
    ),
    parameters=PARAMETERS,
    run=_run,
)
