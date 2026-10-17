"""The ledger: one JSONL record per paid call, with OpenRouter's reported cost."""

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def append(
        self,
        *,
        run_id: str,
        purpose: str,
        model: str,
        usage: dict[str, Any],
        case_id: str | None = None,
        category: str | None = None,
        repeat: int | None = None,
    ) -> dict[str, Any]:
        prompt_details = usage.get("prompt_tokens_details") or {}
        record = {
            "time": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "purpose": purpose,
            "model": model,
            "case_id": case_id,
            "category": category,
            "repeat": repeat,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "cached_tokens": prompt_details.get("cached_tokens", 0),
            "cache_write_tokens": prompt_details.get("cache_write_tokens", 0),
            "cost": float(usage["cost"]),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def total(self) -> float:
        return sum(r["cost"] for r in self.records())

    def per_case_average(self, *, model: str, category: str | None) -> float | None:
        """Average agent cost per case for this model and category; None without history."""
        per_case: dict[tuple, float] = defaultdict(float)
        for r in self.records():
            if r["purpose"] != "agent" or r["model"] != model:
                continue
            if category is not None and r["category"] != category:
                continue
            per_case[(r["run_id"], r["case_id"], r["repeat"])] += r["cost"]
        if not per_case:
            return None
        return sum(per_case.values()) / len(per_case)
