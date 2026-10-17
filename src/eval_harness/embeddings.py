"""Chunk embeddings through OpenRouter (ADR-0002, ADR-0003), cached by model and chunk text hash."""

import json
import secrets
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from eval_harness.budget import decide_start, should_abort
from eval_harness.config import Config
from eval_harness.ingest import IngestError, read_chunks
from eval_harness.ledger import Ledger
from eval_harness.openrouter import OpenRouterClient, OpenRouterError

EMBEDDINGS_FILE = "embeddings.jsonl"
BATCH_SIZE = 32


class EmbedRefused(Exception):
    """Embedding did not start; nothing was spent."""


class EmbedAborted(Exception):
    """Embedding stopped once its spend crossed the remaining budget; batches already embedded
    stay cached."""


def cached_vectors(index_dir: Path, model: str) -> dict[str, list[float]]:
    """Cached vectors for one model, keyed by chunk text SHA-256."""
    path = index_dir / EMBEDDINGS_FILE
    if not path.exists():
        return {}
    try:
        records = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
        return {r["text_sha256"]: r["embedding"] for r in records if r["model"] == model}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise IngestError(f"{path} is unreadable: {exc}") from exc


def append_vectors(index_dir: Path, model: str, vectors: Iterable[tuple[str, list[float]]]) -> None:
    """Add (chunk text SHA-256, vector) pairs for one model to the cache."""
    index_dir.mkdir(parents=True, exist_ok=True)
    with (index_dir / EMBEDDINGS_FILE).open("a", encoding="utf-8") as f:
        for text_sha256, vector in vectors:
            record = {"model": model, "text_sha256": text_sha256, "embedding": vector}
            f.write(json.dumps(record) + "\n")


def embed_corpus(
    config: Config, client: OpenRouterClient, *, echo: Callable[[str], None] = print
) -> int:
    """Embed every chunk with no cached vector; returns how many were embedded.

    Raises EmbedRefused if the budget guard says no. The estimate takes one token per UTF-8
    byte, an upper bound, at the model's live prompt price. Raises EmbedAborted after the batch
    whose spend crosses the budget that remained at the start.
    """
    model = config.embedding_model
    cached = cached_vectors(config.index_dir, model)
    pending = {
        c.text_sha256: c.text for c in read_chunks(config.index_dir) if c.text_sha256 not in cached
    }
    if not pending:
        return 0

    models = client.embedding_models()
    if model not in models:
        raise EmbedRefused(f"embedding model {model!r} is not in the OpenRouter embeddings list")
    estimate = (
        models[model].peak_prompt_price_usd
        * sum(len(text.encode("utf-8")) for text in pending.values())
        * config.budget.safety_margin
    )
    ledger = Ledger(config.ledger_path)
    try:
        key_usage: float | None = client.key_usage()
    except OpenRouterError:
        key_usage = None
    decision = decide_start(
        estimate_usd=estimate,
        ledger_total_usd=ledger.total(),
        key_usage_usd=key_usage,
        ceiling_usd=config.budget.ceiling_usd,
    )
    if not decision.allowed or decision.remaining_usd is None:
        raise EmbedRefused(decision.reason)
    echo(f"budget ok: {decision.reason}")

    run_id = f"embed-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    items = list(pending.items())
    spend = 0.0
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        response = client.embed(model, [text for _, text in batch])
        ledger.append(run_id=run_id, purpose="embedding", model=model, usage=response.usage)
        append_vectors(
            config.index_dir, model, zip([h for h, _ in batch], response.vectors, strict=True)
        )
        spend += response.cost
        if should_abort(run_spend_usd=spend, remaining_usd=decision.remaining_usd):
            raise EmbedAborted(
                f"spend USD {spend:.6f} crossed the remaining budget USD "
                f"{decision.remaining_usd:.6f} after {start + len(batch)} of {len(items)} "
                "chunk(s); those stay cached"
            )
    return len(items)
