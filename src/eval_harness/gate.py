"""The threshold gate: a run passes only if each reviewed category's pass rate and the safety
pass rate meet the pack's `evals/thresholds.toml`.

The file's top level holds the thresholds for a full run: `safety = <rate>` and a `[headline]`
table of `<category> = <rate>`. The `[ci]` table holds the fixed CI subset in the same shape plus
`cases = [<case IDs>]`. Rates are fractions between 0 and 1.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval_harness.report_stats import ReportNumbers, Score

CI = "ci"
SECTION_KEYS = {"safety", "headline"}
FLOAT_NOISE = 1e-9


class ThresholdsError(Exception):
    pass


@dataclass(frozen=True)
class Thresholds:
    safety: float
    headline: dict[str, float]
    cases: list[str] | None = None


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


def load_thresholds(pack: Path, section: str | None = None) -> Thresholds:
    """The full-run thresholds, or the `[ci]` ones when `section` is "ci". The whole file is
    validated either way; raises ThresholdsError naming the problem."""
    path = thresholds_path(pack)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ThresholdsError(f"cannot read {path}: {exc}") from exc
    full = _section(path.name, {k: v for k, v in raw.items() if k != CI}, SECTION_KEYS)
    if CI not in raw:
        if section == CI:
            raise ThresholdsError(f"{path.name} has no [{CI}] section")
        return full
    ci = _section(f"{path.name} [{CI}]", raw[CI], SECTION_KEYS | {"cases"})
    return ci if section == CI else full


def _section(label: str, raw: Any, allowed: set[str]) -> Thresholds:
    if not isinstance(raw, dict):
        raise ThresholdsError(f"{label} must be a table")
    unknown = sorted(raw.keys() - allowed)
    if unknown:
        raise ThresholdsError(f"{label}: unknown keys {unknown}")
    missing = sorted(allowed - raw.keys())
    if missing:
        raise ThresholdsError(f"{label}: missing {missing}")
    headline = raw["headline"]
    if not isinstance(headline, dict) or not headline:
        raise ThresholdsError(f"{label}: headline must be a table of category = rate")
    cases = raw.get("cases")
    if cases is not None and not (
        isinstance(cases, list)
        and cases
        and all(isinstance(c, str) and c.strip() for c in cases)
        and len(set(cases)) == len(cases)
    ):
        raise ThresholdsError(f"{label}: cases must be a non-empty list of distinct case IDs")
    return Thresholds(
        safety=_rate(f"{label}: safety", raw["safety"]),
        headline={name: _rate(f"{label}: {name}", rate) for name, rate in headline.items()},
        cases=cases,
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
