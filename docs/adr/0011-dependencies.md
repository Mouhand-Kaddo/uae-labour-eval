# Dependencies, and why each one earns its place

Python with `uv`, all package versions pinned in `uv.lock`. `mise.toml` pins the tools themselves (Python 3.15 and uv) and is the single source of the Python version: it points uv at mise's Python (`UV_PYTHON`, downloads off), and CI installs both with `jdx/mise-action`, so local runs and CI use the same interpreter. The standard library covers TOML config (`tomllib`), the CLI (`argparse`), JSONL, hashing and the HTML report (string templates).

| Dependency | Group | Why it earns its place |
|---|---|---|
| `httpx` | runtime | OpenRouter calls with timeouts and the raw `usage` object (ADR-0001) |
| `numpy` | runtime | Embedding vectors and brute-force cosine search |
| `bm25s` | runtime | Maintained BM25; core needs only NumPy. `rank-bm25` is unmaintained since 2022 |
| `pyyaml` | runtime | Cases are YAML, as the brief requires |
| `pdfminer.six` | runtime | Glyph-level PDF text extraction, needed for the Arabic repair (ADR-0004) |
| `fonttools` | dev | Building the glyph table once; not needed at runtime |
| `pytest` | dev | Tests |
| `ruff` | dev | Lint and format |
| `ty` | dev | Type checking (`[tool.ty]`, Python 3.15); `make lint` and CI run it with ruff. Fast enough to run on every change, from the same vendor as uv and ruff |

Rejected: `torch`/`sentence-transformers` (several GB for embeddings OpenRouter serves for fractions of a cent), `jinja2` (one report page doesn't need a template engine), `pydantic` (dataclasses plus explicit validation are enough for the case schema), `click`/`typer` (`argparse` covers the CLI).
