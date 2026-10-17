"""A pack's calculation tools: the `TOOLS` list in the pack folder's `__init__.py` (ADR-0006)."""

import importlib.util
import sys
from pathlib import Path

from eval_harness.agent import Tool


class PackError(Exception):
    pass


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
