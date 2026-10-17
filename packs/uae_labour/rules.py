"""Conventions shared by the UAE calculation tools: instruments, Art 67 periods, the daily rate."""

import math
from fractions import Fraction

from eval_harness.refs import Ref

LABOUR_LAW = "Labour Law"
EXECUTIVE_REGULATIONS = "Executive Regulations"

PERIODS = Ref(LABOUR_LAW, "67")
DAYS_IN_YEAR = 365
DAYS_IN_MONTH = 30

DAILY_RATE_QUESTION = "OQ-001"


def daily_basic_wage(monthly_basic_wage: Fraction) -> Fraction:
    """A day's basic wage: monthly × 12 ÷ 365 (Art 67 year, decided in OQ-001)."""
    return monthly_basic_wage * 12 / DAYS_IN_YEAR


def money(amount: Fraction) -> float:
    """Round an amount to fils (two decimals), halves rounded up."""
    return math.floor(amount * 100 + Fraction(1, 2)) / 100
