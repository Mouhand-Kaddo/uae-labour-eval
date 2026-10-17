# Dependencies, and why each one earns its place

Python with `uv`, all versions pinned in `uv.lock`. The standard library covers TOML config (`tomllib`), the CLI (`argparse`), JSONL, hashing and the HTML report (string templates).

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

Rejected: `torch`/`sentence-transformers` (several GB for embeddings OpenRouter serves for fractions of a cent), `jinja2` (one report page doesn't need a template engine), `pydantic` (dataclasses plus explicit validation are enough for the case schema), `click`/`typer` (`argparse` covers the CLI).
