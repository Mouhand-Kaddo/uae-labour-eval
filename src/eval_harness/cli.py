"""`eval` command line. The OpenRouter key is read only from OPENROUTER_API_KEY."""

import argparse
import os
import sys
from pathlib import Path

import httpx

from eval_harness.budget import remaining_budget
from eval_harness.config import Config, ConfigError, load_config
from eval_harness.fetch import FetchError, fetch_sources
from eval_harness.ledger import Ledger
from eval_harness.manifest import ManifestError, load_manifest
from eval_harness.openrouter import OpenRouterClient, OpenRouterError
from eval_harness.runner import RunRefused, run_eval

EXIT_REFUSED = 2
EXIT_ABORTED = 3


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if args.command == "fetch":
        return _fetch(config, transport)

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("error: OPENROUTER_API_KEY is not set", file=sys.stderr)
        return EXIT_REFUSED
    client = OpenRouterClient(api_key, transport=transport)

    if args.command == "budget":
        return _budget(config, client)

    try:
        run = run_eval(
            config,
            client,
            model_id=args.model or config.agent_model,
            category=args.category,
            limit=args.limit,
            repeats=args.repeats,
        )
    except (RunRefused, OpenRouterError) as exc:
        print(f"run refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if run.status == "aborted":
        print("run aborted: its spend crossed the remaining budget", file=sys.stderr)
        return EXIT_ABORTED
    return 0


def _fetch(config: Config, transport: httpx.BaseTransport | None) -> int:
    try:
        fetch_sources(load_manifest(config.pack), config.sources_dir, transport=transport)
    except (ManifestError, FetchError) as exc:
        print(f"fetch failed:\n{exc}", file=sys.stderr)
        return EXIT_REFUSED
    return 0


def _budget(config: Config, client: OpenRouterClient) -> int:
    ledger_total = Ledger(config.ledger_path).total()
    print(f"ledger total USD {ledger_total:.6f}")
    try:
        key_usage = client.key_usage()
    except OpenRouterError as exc:
        print(f"error: key usage is unreachable: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"key usage USD {key_usage:.6f}")
    remaining = remaining_budget(config.budget.ceiling_usd, ledger_total, key_usage)
    print(f"remaining USD {remaining:.6f} of {config.budget.ceiling_usd:.2f}")
    return 0


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval", description="Eval harness for a legal agent.")
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run cases against a model")
    run.add_argument("--model", help="OpenRouter model ID (default: agent model from config)")
    run.add_argument("--category", help="only run cases in this category")
    run.add_argument("--limit", type=_positive_int, help="run at most N cases")
    run.add_argument("--repeats", type=_positive_int, default=1, help="run each case K times")

    commands.add_parser("fetch", help="download the manifest's sources and verify their SHA-256")
    commands.add_parser("budget", help="show ledger total, key usage and remaining budget")
    return parser
