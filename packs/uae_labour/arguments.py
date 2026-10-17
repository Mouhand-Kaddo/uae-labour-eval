"""Validation of the JSON arguments a model passes to the calculation tools."""

import math
from collections.abc import Sequence
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


def optional_date_arg(args: dict[str, Any], name: str) -> date | None:
    return None if args.get(name) is None else date_arg(args, name)


def check_date_order(dates: dict[str, date | None], first: str, last: str) -> None:
    """Reject the date named `last` falling before the one named `first`, when both are given."""
    earlier, later = dates[first], dates[last]
    if earlier is not None and later is not None and later < earlier:
        raise ValueError(f"{last} must not be before {first}")


def ordered_dates_arg(args: dict[str, Any], first: str, last: str) -> tuple[date, date]:
    """Two dates, the second not before the first."""
    earlier, later = date_arg(args, first), date_arg(args, last)
    if later < earlier:
        raise ValueError(f"{last} must not be before {first}")
    return earlier, later


def number_arg(args: dict[str, Any], name: str) -> float:
    value = args[name]
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number")
    return value


def positive_number_arg(args: dict[str, Any], name: str) -> float | None:
    """An optional number that must be more than 0 when given."""
    if args.get(name) is None:
        return None
    value = number_arg(args, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def work_pattern_arg(
    args: dict[str, Any], supported: Sequence[str], default: str | None = None
) -> str:
    pattern = args.get("work_pattern") or default
    if pattern not in supported:
        raise ValueError(f"work_pattern must be one of {list(supported)}")
    return pattern


def hours_ratio_arg(
    args: dict[str, Any], pattern: str, pro_rata_patterns: Sequence[str]
) -> float | None:
    """The part-time hours ratio: required in (0, 1] for a pro-rata pattern, else absent."""
    ratio = args.get("part_time_hours_ratio")
    if pattern in pro_rata_patterns:
        if ratio is None or not 0 < number_arg(args, "part_time_hours_ratio") <= 1:
            raise ValueError(f"part_time_hours_ratio between 0 and 1 is needed for {pattern}")
    elif ratio is not None:
        raise ValueError(f"part_time_hours_ratio applies only to {' or '.join(pro_rata_patterns)}")
    return ratio


def whole_days_arg(args: dict[str, Any], name: str) -> int:
    value = args.get(name) or 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a whole number of days, 0 or more")
    return value


def wages_args(args: dict[str, Any]) -> float | None:
    """The monthly basic wage, if given, checked positive and not above the monthly wage (Art 1)."""
    basic = positive_number_arg(args, "monthly_basic_wage")
    if basic is None:
        return None
    if args.get("monthly_wage") is not None and number_arg(args, "monthly_wage") < basic:
        raise ValueError("monthly_wage is the basic wage plus allowances (Art 1), so >= basic")
    return basic
