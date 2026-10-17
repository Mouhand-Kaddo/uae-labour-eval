"""`eval` command line. The OpenRouter key is read only from OPENROUTER_API_KEY."""

import argparse
import os
import sys
from pathlib import Path

import httpx

from eval_harness.budget import remaining_budget
from eval_harness.compare import compare_runs
from eval_harness.config import Config, ConfigError, load_config
from eval_harness.embeddings import EmbedRefused, embed_corpus
from eval_harness.fetch import FetchError, fetch_sources
from eval_harness.ingest import IngestError, ingest
from eval_harness.judge_check import (
    JudgeCheckError,
    judge_agreement,
    judge_pending,
    sample_check_set,
)
from eval_harness.ledger import Ledger
from eval_harness.manifest import ManifestError, load_manifest
from eval_harness.openrouter import OpenRouterClient, OpenRouterError
from eval_harness.report import ReportError, read_run, write_report
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
    if args.command == "ingest":
        return _ingest(config)

    if args.command == "report":
        return _report(config, args.run)
    if args.command == "compare":
        return _compare(config, args.run_a, args.run_b)
    if args.command == "judge-agreement":
        return _judge_agreement(config)
    if args.command == "judge-check" and args.action == "sample":
        return _judge_check_sample(config, args.runs, args.size, args.seed)
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("error: OPENROUTER_API_KEY is not set", file=sys.stderr)
        return EXIT_REFUSED
    client = OpenRouterClient(api_key, transport=transport)

    if args.command == "budget":
        return _budget(config, client)
    if args.command == "embed":
        return _embed(config, client)
    if args.command == "judge-check":
        return _judge_check_judge(config, client, args.limit)

    try:
        run = run_eval(
            config,
            client,
            model_id=args.model or config.agent_model,
            category=args.category,
            case_ids=args.case,
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


def _ingest(config: Config) -> int:
    try:
        chunks = ingest(load_manifest(config.pack), config.sources_dir, config.index_dir)
    except (ManifestError, IngestError) as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    for source in sorted({c.source for c in chunks}):
        articles = {c.article for c in chunks if c.source == source}
        count = sum(c.source == source for c in chunks)
        print(f"ok {source}: {len(articles)} articles, {count} chunks")
    print(f"wrote {len(chunks)} chunks to {config.index_dir}")
    return 0


def _embed(config: Config, client: OpenRouterClient) -> int:
    try:
        count = embed_corpus(config, client)
    except (EmbedRefused, IngestError, OpenRouterError) as exc:
        print(f"embed failed: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"embedded {count} chunk(s) with {config.embedding_model}")
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


def _run_dir(config: Config, run: str) -> Path:
    run_dir = Path(run) if Path(run).is_dir() else config.runs_dir / run
    if not run_dir.is_dir():
        raise ReportError(f"no run directory {run!r} (looked in {config.runs_dir})")
    return run_dir


def _report(config: Config, run: str) -> int:
    try:
        index = write_report(_run_dir(config, run))
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"report written to {index}")
    return 0


def _compare(config: Config, run_a: str, run_b: str) -> int:
    try:
        summaries = [read_run(_run_dir(config, run)) for run in (run_a, run_b)]
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(compare_runs(*summaries))
    return 0


def _judge_check_sample(config: Config, runs: list[str], size: int, seed: int) -> int:
    try:
        items = sample_check_set(
            config, [_run_dir(config, run) for run in runs], size=size, seed=seed
        )
    except (ReportError, JudgeCheckError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item.case.category, "broken" if item.breakage else "real")
        counts[key] = counts.get(key, 0) + 1
    for (category, kind), count in sorted(counts.items()):
        print(f"{category} {kind}: {count}")
    pending = sum(item.verdict is None for item in items)
    print(f"wrote {len(items)} items; {pending} still need a judge verdict (judge-check judge)")
    return 0


def _judge_check_judge(config: Config, client: OpenRouterClient, limit: int | None) -> int:
    try:
        judged, spend = judge_pending(config, client, limit=limit)
    except (JudgeCheckError, OpenRouterError) as exc:
        print(f"judge-check refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"judged {judged} item(s); spend USD {spend:.6f}")
    return 0


def _judge_agreement(config: Config) -> int:
    try:
        result = judge_agreement(config.pack)
    except JudgeCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(
        f"{result['n']} labelled decisions with a judge verdict across {result['items']} items; "
        f"{result['unlabelled']} unlabelled, {result['unjudged']} without a judge verdict"
    )
    print("| Rubric | Criterion | n | Agreement | Kappa | Trust |")
    print("|---|---|---|---|---|---|")
    for name, rubric in result["rubrics"].items():
        for criterion, measured in rubric["criteria"].items():
            print(f"| {name} | {criterion} | {_measured(measured)} | |")
        trust = "trusted" if rubric["trusted"] else "UNTRUSTED"
        print(f"| **{name}** | all | {_measured(rubric)} | {trust} |")
    print(f"| **overall** | | {_measured(result)} | |")
    untrusted = ", ".join(result["untrusted_categories"]) or "none"
    print(f"judged categories untrusted (kappa below {result['threshold']}): {untrusted}")
    return 0


def _measured(measured: dict) -> str:
    agreement, kappa = measured["agreement"], measured["kappa"]
    return (
        f"{measured['n']} | {'n/a' if agreement is None else f'{agreement:.0%}'} | "
        f"{'n/a' if kappa is None else f'{kappa:.2f}'}"
    )


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
    run.add_argument(
        "--case", action="append", help="only run the case with this ID (repeat for several)"
    )
    run.add_argument("--limit", type=_positive_int, help="run at most N cases")
    run.add_argument("--repeats", type=_positive_int, default=1, help="run each case K times")

    commands.add_parser("fetch", help="download the manifest's sources and verify their SHA-256")
    commands.add_parser("ingest", help="chunk the fetched sources into the search index")
    commands.add_parser("embed", help="embed chunks that have no cached vector (paid)")
    commands.add_parser("budget", help="show ledger total, key usage and remaining budget")

    report = commands.add_parser("report", help="write the HTML report for a run")
    report.add_argument("run", help="run ID under runs_dir, or a path to a run directory")

    compare = commands.add_parser("compare", help="show two runs side by side")
    compare.add_argument("run_a", help="run ID under runs_dir, or a path to a run directory")
    compare.add_argument("run_b", help="run ID under runs_dir, or a path to a run directory")

    judge_check = commands.add_parser("judge-check", help="build and judge the judge-check set")
    actions = judge_check.add_subparsers(dest="action", required=True)
    sample = actions.add_parser(
        "sample", help="sample judged answers from runs into the pack's blind labelling file"
    )
    sample.add_argument("runs", nargs="+", help="run IDs under runs_dir, or run directories")
    sample.add_argument("--size", type=_positive_int, default=40, help="real answers to draw")
    sample.add_argument("--seed", type=int, default=18, help="random seed for the draw")
    judge = actions.add_parser("judge", help="ask the judge about items with no verdict (paid)")
    judge.add_argument("--limit", type=_positive_int, help="judge at most N items")
    commands.add_parser(
        "judge-agreement", help="compare the owner's labels with the judge (raw and kappa)"
    )
    return parser
