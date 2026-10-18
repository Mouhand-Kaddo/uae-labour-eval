"""The threshold gate: a run passes only if each reviewed category's pass rate and the safety
pass rate meet the pack's `evals/thresholds.toml`.

The file's top level holds the thresholds for a full run: `safety = <rate>` and a `[headline]`
table of `<category> = <rate>`. Rates are fractions between 0 and 1.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval_harness.report_stats import ReportNumbers, Score

KEYS = {"safety", "headline"}
FLOAT_NOISE = 1e-9


class ThresholdsError(Exception):
    pass


@dataclass(frozen=True)
class Thresholds:
    safety: float
    headline: dict[str, float]


@dataclass(frozen=True)
class GateRow:
    score: Score
    threshold: float | None

    @property
    def problem(self) -> str | None:
        """Why this row fails the gate, or None if it passes."""
        if self.threshold is None:
            return "no threshold"
        if self.score.rate is None:
            return "no reviewed cases"
        if self.score.rate < self.threshold - FLOAT_NOISE:
            return "below threshold"
        return None


def thresholds_path(pack: Path) -> Path:
    return pack / "evals" / "thresholds.toml"


def load_thresholds(pack: Path) -> Thresholds:
    """The pack's thresholds; raises ThresholdsError naming the problem."""
    path = thresholds_path(pack)
    label = path.name
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ThresholdsError(f"cannot read {path}: {exc}") from exc
    unknown = sorted(raw.keys() - KEYS)
    if unknown:
        raise ThresholdsError(f"{label}: unknown keys {unknown}")
    missing = sorted(KEYS - raw.keys())
    if missing:
        raise ThresholdsError(f"{label}: missing {missing}")
    headline = raw["headline"]
    if not isinstance(headline, dict) or not headline:
        raise ThresholdsError(f"{label}: headline must be a table of category = rate")
    return Thresholds(
        safety=_rate(f"{label}: safety", raw["safety"]),
        headline={name: _rate(f"{label}: {name}", rate) for name, rate in headline.items()},
    )


def _rate(label: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
        raise ThresholdsError(f"{label} must be a rate between 0 and 1, got {value!r}")
    return float(value)


def gate(numbers: ReportNumbers, thresholds: Thresholds) -> list[GateRow]:
    """One row per category named by the thresholds or scored in the run, then safety."""
    scores = {score.label: score for score in numbers.headline}
    categories = sorted(scores.keys() | thresholds.headline.keys())
    rows = [
        GateRow(scores.get(category, Score(category, 0, 0)), thresholds.headline.get(category))
        for category in categories
    ]
    return [*rows, GateRow(numbers.safety, thresholds.safety)]


def gate_table(rows: list[GateRow]) -> str:
    lines = ["| Score | n | Observed | Threshold | Result |", "|---|---|---|---|---|"]
    for row in rows:
        observed = "n/a" if row.score.rate is None else f"{row.score.rate:.0%}"
        threshold = "none" if row.threshold is None else f"{row.threshold:.0%}"
        if row.problem is None:
            result = "pass"
        elif row.problem == "below threshold":
            result = "FAIL"
        else:
            result = f"FAIL ({row.problem})"
        lines.append(f"| {row.score.label} | {row.score.n} | {observed} | {threshold} | {result} |")
    return "\n".join(lines)
