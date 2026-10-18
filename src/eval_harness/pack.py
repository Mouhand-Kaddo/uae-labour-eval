"""What a pack provides (ADR-0006): its cases, checked against the scorers it may use, and its
calculation tools, the `TOOLS` list in the pack folder's `__init__.py`."""

import dataclasses
import importlib.util
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from eval_harness.agent import Tool
from eval_harness.cases import CONSISTENCY, Case, load_cases, load_open_questions
from eval_harness.config import Config
from eval_harness.judge import PAIR_RUBRIC, Rubric
from eval_harness.scorers import SCORERS


class PackError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class PackCases:
    cases: list[Case]
    open_questions: dict[str, bool] | None


def load_pack_cases(config: Config, rubrics: Mapping[str, Rubric]) -> PackCases:
    """Every case in the pack, checked against the scorers a case may name (the built-in ones,
    `judge:<rubric>` for the pack's rubrics, and consistency) and against the open-questions doc
    if the config names one. `rubrics` is keyed by scorer name, as `load_rubrics` returns it.
    Raises CaseError."""
    open_questions = (
        None if config.open_questions is None else load_open_questions(config.open_questions)
    )
    scorer_names = [*SCORERS, *(name for name in rubrics if name != PAIR_RUBRIC), CONSISTENCY]
    cases = load_cases(config.pack / "evals" / "cases", scorer_names, open_questions)
    return PackCases(cases, open_questions)


def load_pack_tools(pack: Path) -> list[Tool]:
    """Import the pack folder as a package and return its tools; a pack without code has none."""
    init = pack / "__init__.py"
    if not init.is_file():
        return []
    spec = importlib.util.spec_from_file_location(
        pack.name, init, submodule_search_locations=[str(pack)]
    )
    if spec is None or spec.loader is None:
        raise PackError(f"cannot import the pack at {pack}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[pack.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PackError(f"cannot import the pack at {pack}: {exc!r}") from exc

    tools = getattr(module, "TOOLS", None)
    if not isinstance(tools, list) or not all(isinstance(t, Tool) for t in tools):
        raise PackError(f"{init} must define TOOLS as a list of Tool")
    names = [t.name for t in tools]
    if len(set(names)) != len(names) or "final_answer" in names:
        raise PackError(f"{init}: tool names must be unique and not final_answer: {names}")
    return tools


def mark_open_questions(tools: list[Tool], open_questions: Mapping[str, bool]) -> list[Tool]:
    """Tools whose result `open_questions` IDs become `{id, status}` with status decided or open.

    Status comes from the open-questions doc, the same source the case validator reads; an ID
    the doc does not record counts as open.
    """
    return [dataclasses.replace(tool, run=_marking(tool.run, open_questions)) for tool in tools]


def _marking(
    run: Callable[[dict[str, Any]], Any], open_questions: Mapping[str, bool]
) -> Callable[[dict[str, Any]], Any]:
    def marked(args: dict[str, Any]) -> Any:
        result = run(args)
        if isinstance(result, dict) and isinstance(result.get("open_questions"), list):
            result = result | {
                "open_questions": [
                    {"id": q, "status": "open" if open_questions.get(q, True) else "decided"}
                    for q in result["open_questions"]
                ]
            }
        return result

    return marked
