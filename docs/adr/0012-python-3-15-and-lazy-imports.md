# Python 3.15, with lazy imports for heavy modules

The project requires Python 3.15 (released 2026-10-09; every dependency installs on it and the suite passes). `mise.toml` pins it, `requires-python = ">=3.15"`, ruff targets `py315` and ty checks against 3.15.

3.15 features are used only where they were measured to help or are clearly simpler:

- **Explicit lazy imports (PEP 810).** Every command used to import numpy, bm25s (and SciPy through it), pdfminer, httpx and PyYAML before parsing its arguments. These are now `lazy import`s in the modules that use them, and the CLI imports its command modules lazily, so a command loads only what it runs. ruff and ty both parse the syntax, so the `__lazy_modules__` fallback isn't needed. Modules that subclass a third-party class at import time (`pdf_text`, `judge_check`) stay eager inside and are imported lazily by their callers.
- **`frozendict` (PEP 814)** for module-level lookup tables that are only read (scorer registry, case and manifest field types, routing choices, label values, probation notice rules). JSON-schema payloads stay plain dicts, since their nested values would still be mutable.
- **Unpacking in comprehensions (PEP 798)** where it replaces a nested `for` that only flattens.
- File I/O keeps its explicit `encoding="utf-8"` even though UTF-8 is now the default (PEP 686). The experimental JIT stays off.

Measured on CPython 3.15.0, Linux x86-64, median of 30 runs:

| Command | Before | After | Import time before → after |
|---|---|---|---|
| `eval --help` | 287 ms | 52 ms | 231 → 39 ms |
| `eval budget --help` | 285 ms | 51 ms | 235 → 39 ms |
| `eval budget` (stops at the missing key) | 303 ms | 40 ms | 240 → 28 ms |
| `eval compare --help` | 318 ms | 51 ms | 257 → 39 ms |

## Consequences

- Python 3.14 and older can no longer run the project, and `lazy` is a syntax error before 3.15.
- A broken heavy import now fails when a command first uses it, not at startup. The test suite exercises every command, so it still catches one.
