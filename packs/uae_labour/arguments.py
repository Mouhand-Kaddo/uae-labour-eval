"""Validation of the JSON arguments a model passes to the calculation tools."""

import math
from datetime import date
from typing import Any


def check_names(args: dict[str, Any], parameters: dict[str, Any]) -> None:
    """Reject arguments the schema doesn't define and required ones that are missing."""
    unknown = args.keys() - parameters["properties"].keys()
    if unknown:
        raise ValueError(f"unknown arguments {sorted(unknown)}")
    missing = set(parameters["required"]) - args.keys()
    if missing:
        raise ValueError(f"missing arguments {sorted(missing)}")


def date_arg(args: dict[str, Any], name: str) -> date:
    try:
        return date.fromisoformat(args[name])
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a date in YYYY-MM-DD form") from None


def number_arg(args: dict[str, Any], name: str) -> float:
    value = args[name]
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number")
    return value


def whole_days_arg(args: dict[str, Any], name: str) -> int:
    value = args.get(name) or 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a whole number of days, 0 or more")
    return value


def wages_args(args: dict[str, Any]) -> float | None:
    """The monthly basic wage, if given, checked positive and not above the monthly wage (Art 1)."""
    if args.get("monthly_basic_wage") is None:
        return None
    basic = number_arg(args, "monthly_basic_wage")
    if basic <= 0:
        raise ValueError("monthly_basic_wage must be positive")
    if args.get("monthly_wage") is not None and number_arg(args, "monthly_wage") < basic:
        raise ValueError("monthly_wage is the basic wage plus allowances (Art 1), so >= basic")
    return basic
