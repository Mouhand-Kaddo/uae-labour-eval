"""A trace: the step-by-step JSONL record of one case in a run, written as it happens."""

import json
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: Path):
        self.path = path
        self.steps: list[dict[str, Any]] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def add(self, step_type: str, **fields: Any) -> None:
        step = {"type": step_type, **fields}
        self.steps.append(step)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(step, ensure_ascii=False, default=str) + "\n")
