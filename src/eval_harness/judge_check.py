"""The judge-check set: hand labels the judge is measured against before it is trusted (ADR-0009).

Files in `<pack>/evals/judge_check/`, frozen with the cases:
- `broken.yaml`: hand-written broken answers, each replacing a real answer from a run.
- `items.json`: what the judge sees for each item (question, answer, cited text, planted text).
- `verdicts.json`: where each item came from and the judge's verdict. Never shown to the labeller.
- `labels.yaml`: the blind labelling file the owner fills in.
- `agreement.json`: the judge's agreement with the labels, written by `eval judge-agreement`.
"""

import json
import random
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from itertools import chain, zip_longest
from pathlib import Path
from typing import Any

import yaml

from eval_harness.budget import decide_start, estimate_run_cost, should_abort
from eval_harness.cases import (
    Case,
    CaseError,
)
from eval_harness.config import Config
from eval_harness.final_answer import FinalAnswer, parse_final_answer
from eval_harness.judge import (
    PAIR_RUBRIC,
    SCORER_PREFIX,
    JudgeUnavailable,
    Rubric,
    RubricError,
    ask_judge,
    cited_sources,
    load_rubrics,
    pair_material,
    planted_material,
    resolve_judge,
    single_material,
)
from eval_harness.ledger import Ledger
from eval_harness.openrouter import ChatResponse, OpenRouterClient, OpenRouterError
from eval_harness.pack import load_pack_cases
from eval_harness.refs import article_label

STRATA = ("grounding", "refuse", "inject", "bilingual", "cite")
TRUSTED_KAPPA = 0.6
LABELS = frozendict({"pass": True, "fail": False})
FREE_TEXT_RUBRIC = "grounding"
PAIR_RUBRIC_NAME = PAIR_RUBRIC.removeprefix(SCORER_PREFIX)
BROKEN_FILE = "broken.yaml"
ITEMS_FILE = "items.json"
VERDICTS_FILE = "verdicts.json"
LABELS_FILE = "labels.yaml"
AGREEMENT_FILE = "agreement.json"


class JudgeCheckError(Exception):
    pass


def check_dir(pack: Path) -> Path:
    return pack / "evals" / "judge_check"


@dataclass(frozen=True)
class Agreement:
    """How often two raters agree on pass/fail decisions, raw and chance-corrected."""

    n: int
    agreement: float | None
    kappa: float | None


def measure(pairs: Sequence[tuple[bool, bool]]) -> Agreement:
    """Raw agreement and Cohen's kappa over (owner, judge) pass/fail decisions.

    Kappa is None when chance agreement is already certain (both raters gave one answer only).
    """
    n = len(pairs)
    if not n:
        return Agreement(0, None, None)
    observed = sum(owner == judge for owner, judge in pairs) / n
    owner_pass = sum(owner for owner, _ in pairs) / n
    judge_pass = sum(judge for _, judge in pairs) / n
    chance = owner_pass * judge_pass + (1 - owner_pass) * (1 - judge_pass)
    kappa = None if chance == 1 else (observed - chance) / (1 - chance)
    return Agreement(n, observed, kappa)


@dataclass(frozen=True)
class Candidate:
    """One judged (or judgeable) answer from a run: a single answer or a bilingual pair."""

    run_id: str
    model: str | None
    case: Case
    rubric: str
    finals: dict[str, FinalAnswer]
    halves: dict[str, list[dict[str, Any]]]
    verdict: dict[str, Any] | None
    breakage: str | None = None

    @property
    def questions(self) -> dict[str, str]:
        return self.case.inputs()

    def sources(self) -> list[dict[str, Any]]:
        return cited_sources(self.finals, self.halves)

    def planted(self) -> list[dict[str, Any]]:
        return planted_material(self.case)


def sample_check_set(
    config: Config, run_dirs: Sequence[Path], *, size: int, seed: int
) -> list[Candidate]:
    """Sample about `size` judged answers from the runs, add the pack's broken answers, and write
    the check set into the pack. Returns the items in the order written."""
    rubrics = pack_rubrics(config.pack)
    cases = _pack_cases(config, rubrics)
    candidates = [*read_candidates(run_dir, cases) for run_dir in run_dirs]
    directory = check_dir(config.pack)
    rng = random.Random(seed)
    chosen = sample(candidates, size, rng)
    chosen += broken_candidates(directory / BROKEN_FILE, candidates, rubrics)
    return build_check_set(directory, chosen, rubrics, rng)


def pack_rubrics(pack: Path) -> dict[str, Rubric]:
    """The pack's rubrics keyed by rubric name (the scorer name without `judge:`)."""
    try:
        return {rubric.name: rubric for rubric in load_rubrics(pack).values()}
    except RubricError as exc:
        raise JudgeCheckError(str(exc)) from exc


def _pack_cases(config: Config, rubrics: Mapping[str, Rubric]) -> dict[str, Case]:
    by_scorer = {SCORER_PREFIX + name: rubric for name, rubric in rubrics.items()}
    try:
        cases = load_pack_cases(config, by_scorer).cases
    except CaseError as exc:
        raise JudgeCheckError(f"invalid cases: {exc}") from exc
    return {case.id: case for case in cases}


def read_candidates(run_dir: Path, cases: Mapping[str, Case]) -> list[Candidate]:
    """Every answer in a run whose case falls in one of the STRATA and that ended in a final
    answer, with the judge's stored verdict when the run judged it."""
    try:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JudgeCheckError(f"cannot read {run_dir / 'summary.json'}: {exc}") from exc
    run_id = str(summary.get("run_id", run_dir.name))
    candidates = []
    for path in sorted((run_dir / "traces").glob("*.jsonl")):
        try:
            steps = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        except (OSError, json.JSONDecodeError) as exc:
            raise JudgeCheckError(f"cannot read {path}: {exc}") from exc
        candidate = _candidate(run_id, summary.get("model"), steps, cases, path)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate(
    run_id: str,
    model: str | None,
    steps: list[dict[str, Any]],
    cases: Mapping[str, Case],
    path: Path,
) -> Candidate | None:
    start = steps[0] if steps else {}
    if start.get("type") != "case" or start.get("category") not in STRATA:
        return None
    case = cases.get(start["case_id"])
    if case is None:
        raise JudgeCheckError(f"{path}: case {start['case_id']!r} is not in the pack's cases")
    halves = _halves(steps, case)
    final_steps = {language: _final_step(half) for language, half in halves.items()}
    if final_steps.keys() != case.inputs().keys() or None in final_steps.values():
        return None
    try:
        finals = {language: parse_final_answer(step) for language, step in final_steps.items()}
    except ValueError as exc:
        raise JudgeCheckError(f"{path}: malformed final answer: {exc}") from exc
    details = (steps[-1].get("details") if steps[-1].get("type") == "verdict" else None) or {}
    if case.is_pair:
        rubric = PAIR_RUBRIC_NAME
        stored = (details.get("consistency") or {}).get("judge")
    else:
        rubric = next(
            (n.removeprefix(SCORER_PREFIX) for n in case.scoring if n.startswith(SCORER_PREFIX)),
            FREE_TEXT_RUBRIC,
        )
        stored = details.get(SCORER_PREFIX + rubric)
    verdict = stored if isinstance(stored, dict) and "criteria" in stored else None
    return Candidate(run_id, start.get("model", model), case, rubric, finals, halves, verdict)


def _halves(steps: list[dict[str, Any]], case: Case) -> dict[str, list[dict[str, Any]]]:
    if not case.is_pair:
        return {case.language: steps}
    halves: dict[str, list[dict[str, Any]]] = {}
    current: list[dict[str, Any]] | None = None
    for step in steps:
        if step.get("type") == "half":
            current = halves.setdefault(step["language"], [])
        elif current is not None:
            current.append(step)
    return halves


def _final_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    final = next((s for s in steps if s.get("type") == "final_answer"), None)
    if final is None:
        return None
    return {k: final[k] for k in ("answer", "citations", "status", "refusal_reason")}


def sample(candidates: Sequence[Candidate], size: int, rng: random.Random) -> list[Candidate]:
    """Up to `size` candidates, drawn in turn from each stratum. Within a stratum, answers with a
    stored verdict come first, alternating judge pass and fail; unjudged answers come last."""
    queues = []
    for stratum in STRATA:
        group = [c for c in candidates if c.case.category == stratum]
        rng.shuffle(group)
        passed = [c for c in group if c.verdict is not None and c.verdict["passed"]]
        failed = [c for c in group if c.verdict is not None and not c.verdict["passed"]]
        alternating = [c for c in chain(*zip_longest(passed, failed)) if c is not None]
        queues.append(alternating + [c for c in group if c.verdict is None])
    chosen: list[Candidate] = []
    while len(chosen) < size and any(queues):
        for queue in queues:
            if queue and len(chosen) < size:
                chosen.append(queue.pop(0))
    return chosen


def broken_candidates(
    path: Path, candidates: Sequence[Candidate], rubrics: Mapping[str, Rubric]
) -> list[Candidate]:
    """The hand-written broken answers in `path`, each put in place of a real run answer."""
    if not path.exists():
        return []
    try:
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except yaml.YAMLError as exc:
        raise JudgeCheckError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(entries, list):
        raise JudgeCheckError(f"{path}: expected a list of broken answers")
    by_origin = {(c.run_id, c.case.id): c for c in candidates}
    broken = []
    for number, entry in enumerate(entries, 1):
        where = f"{path.name} entry {number}"
        if not isinstance(entry, dict) or set(entry) != {"breakage", "run", "case", "answers"}:
            raise JudgeCheckError(f"{where}: needs exactly breakage, run, case and answers")
        base = by_origin.get((entry["run"], entry["case"]))
        if base is None:
            raise JudgeCheckError(
                f"{where}: no answer from run {entry['run']!r} to case {entry['case']!r}"
            )
        answers = entry["answers"]
        if not isinstance(answers, dict) or not answers or not set(answers) <= set(base.finals):
            raise JudgeCheckError(f"{where}: answers must be keyed by {sorted(base.finals)}")
        try:
            finals = {lang: parse_final_answer(answers.get(lang)) for lang in answers}
        except ValueError as exc:
            raise JudgeCheckError(f"{where}: {exc}") from exc
        if base.rubric not in rubrics:
            raise JudgeCheckError(f"{where}: the pack has no rubric {base.rubric!r}")
        broken.append(
            replace(
                base,
                finals=base.finals | finals,
                verdict=None,
                breakage=str(entry["breakage"]),
            )
        )
    return broken


def build_check_set(
    directory: Path,
    candidates: Sequence[Candidate],
    rubrics: Mapping[str, Rubric],
    rng: random.Random,
) -> list[Candidate]:
    """Write items, verdicts and the blind labelling file for `candidates`, in shuffled order.

    Refuses to overwrite a labelling file that already holds labels.
    """
    labels_path = directory / LABELS_FILE
    if labels_path.exists() and any(_filled_labels(read_labels(labels_path))):
        raise JudgeCheckError(
            f"{labels_path} already holds labels; move it away before sampling a new set"
        )
    missing = sorted({c.rubric for c in candidates} - set(rubrics))
    if missing:
        raise JudgeCheckError(f"the pack has no rubric for {missing}")
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    ids = [f"jc-{n:03d}" for n in range(1, len(shuffled) + 1)]
    items = {
        item_id: {
            "rubric": c.rubric,
            "category": c.case.category,
            "questions": c.questions,
            "answers": {language: asdict(final) for language, final in c.finals.items()},
            "sources": c.sources(),
            "planted": c.planted(),
        }
        for item_id, c in zip(ids, shuffled, strict=True)
    }
    verdicts = {
        item_id: {
            "origin": {
                "run_id": c.run_id,
                "case_id": c.case.id,
                "model": c.model,
                **({"breakage": c.breakage} if c.breakage else {}),
            },
            "verdict": c.verdict,
        }
        for item_id, c in zip(ids, shuffled, strict=True)
    }
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / ITEMS_FILE, items)
    write_json(directory / VERDICTS_FILE, verdicts)
    labels_path.write_text(labels_text(items, rubrics), encoding="utf-8")
    return shuffled


def judge_pending(
    config: Config,
    client: OpenRouterClient,
    *,
    limit: int | None = None,
    echo: Callable[[str], None] = print,
) -> tuple[int, float]:
    """Ask the judge about every item without a usable verdict, broken items first, and store
    each verdict as it arrives. Returns (items judged, spend).

    The budget guard must allow the whole batch before the first call; the batch stops early if
    its spend crosses the budget that remained at the start.
    """
    directory = check_dir(config.pack)
    items, verdicts, rubrics = _read_check_set(config.pack)
    pending = [
        item_id for item_id in items if "criteria" not in (verdicts[item_id]["verdict"] or {})
    ]
    pending.sort(key=lambda item_id: "breakage" not in verdicts[item_id]["origin"])
    pending = pending[:limit]
    if not pending:
        return 0, 0.0
    try:
        judge = resolve_judge(config.judge_model, client.models())
        key_usage: float | None = client.key_usage()
    except JudgeUnavailable as exc:
        raise JudgeCheckError(str(exc)) from exc
    except OpenRouterError:
        key_usage = None
    estimate = estimate_run_cost(
        case_count=len(pending),
        history_per_case_usd=None,
        prompt_price_usd=judge.peak_prompt_price_usd,
        completion_price_usd=judge.peak_completion_price_usd,
        assumed_prompt_tokens=config.budget.assumed_prompt_tokens_per_case,
        assumed_completion_tokens=config.budget.assumed_completion_tokens_per_case,
        margin=config.budget.safety_margin,
    )
    ledger = Ledger(config.ledger_path)
    decision = decide_start(
        estimate_usd=estimate,
        ledger_total_usd=ledger.total(),
        key_usage_usd=key_usage,
        ceiling_usd=config.budget.ceiling_usd,
    )
    if not decision.allowed or decision.remaining_usd is None:
        raise JudgeCheckError(decision.reason)
    echo(f"budget ok: {decision.reason}")

    run_id = f"judge-check-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    spend = 0.0
    judged = 0
    for item_id in pending:
        item = items[item_id]

        def record(response: ChatResponse, item_id: str = item_id, item=item) -> None:
            nonlocal spend
            ledger.append(
                run_id=run_id,
                purpose="judge",
                model=judge.id,
                usage=response.usage,
                case_id=item_id,
                category=item["category"],
                provider=response.provider,
            )
            spend += response.cost

        verdict = ask_judge(
            client,
            judge,
            rubrics[item["rubric"]],
            config.judge,
            config.provider_for(judge.id),
            record,
            item_material(item),
        )
        verdicts[item_id]["verdict"] = {"passed": verdict.passed, **verdict.details}
        write_json(directory / VERDICTS_FILE, verdicts)
        judged += 1
        echo(f"{item_id} {item['rubric']}: {'error' if 'error' in verdict.details else 'judged'}")
        if should_abort(run_spend_usd=spend, remaining_usd=decision.remaining_usd):
            echo("stopped: the spend crossed the remaining budget")
            break
    return judged, spend


def judge_agreement(pack: Path) -> dict[str, Any]:
    """Compare the owner's labels with the judge's verdicts and write `agreement.json`.

    Every (item, criterion) with both a label and a judge verdict is one decision. Agreement is
    reported overall, per rubric and per criterion; a rubric is trusted only if its kappa is at
    least TRUSTED_KAPPA. Raises JudgeCheckError when nothing is labelled yet.
    """
    directory = check_dir(pack)
    items, verdicts, rubrics = _read_check_set(pack)
    owner = owner_labels(read_labels(directory / LABELS_FILE), items, rubrics)
    decisions: dict[str, dict[str, list[tuple[bool, bool]]]] = {
        name: {criterion: [] for criterion in rubrics[name].criteria}
        for name in sorted({item["rubric"] for item in items.values()})
    }
    unlabelled = unjudged = 0
    for item_id, item in items.items():
        judged = (verdicts[item_id]["verdict"] or {}).get("criteria") or {}
        for criterion in rubrics[item["rubric"]].criteria:
            label = owner.get((item_id, criterion))
            if label is None:
                unlabelled += 1
            elif criterion not in judged:
                unjudged += 1
            else:
                decisions[item["rubric"]][criterion].append((label, judged[criterion]["passed"]))
    every_decision = [
        pair
        for by_criterion in decisions.values()
        for pairs in by_criterion.values()
        for pair in pairs
    ]
    if not every_decision:
        raise JudgeCheckError(
            f"no labelled decisions with a judge verdict yet: fill in {directory / LABELS_FILE}"
        )
    by_rubric: dict[str, dict[str, Any]] = {}
    for name, by_criterion in decisions.items():
        overall = measure([*pairs for pairs in by_criterion.values()])
        by_rubric[name] = asdict(overall) | {
            "trusted": overall.kappa is not None and overall.kappa >= TRUSTED_KAPPA,
            "categories": sorted(
                {item["category"] for item in items.values() if item["rubric"] == name}
            ),
            "criteria": {c: asdict(measure(pairs)) for c, pairs in by_criterion.items()},
        }
    result = asdict(measure(every_decision)) | {
        "threshold": TRUSTED_KAPPA,
        "items": len(items),
        "unlabelled": unlabelled,
        "unjudged": unjudged,
        "rubrics": by_rubric,
        "untrusted_categories": sorted(
            {*r["categories"] for r in by_rubric.values() if not r["trusted"]}
        ),
    }
    write_json(directory / AGREEMENT_FILE, result)
    return result


def _read_check_set(pack: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Rubric]]:
    """Items, verdicts and rubrics, checked to cover each other."""
    directory = check_dir(pack)
    items = read_json(directory / ITEMS_FILE)
    verdicts = read_json(directory / VERDICTS_FILE)
    rubrics = pack_rubrics(pack)
    if set(items) != set(verdicts):
        raise JudgeCheckError(f"{ITEMS_FILE} and {VERDICTS_FILE} list different items")
    for item_id, item in items.items():
        if not isinstance(item, dict) or item.get("rubric") not in rubrics:
            raise JudgeCheckError(
                f"{ITEMS_FILE} {item_id}: needs one of the rubrics {sorted(rubrics)}"
            )
        if not isinstance(verdicts[item_id], dict) or not {"origin", "verdict"} <= set(
            verdicts[item_id]
        ):
            raise JudgeCheckError(f"{VERDICTS_FILE} {item_id}: needs origin and verdict")
    return items, verdicts, rubrics


def owner_labels(
    entries: list[dict[str, Any]], items: Mapping[str, Any], rubrics: Mapping[str, Rubric]
) -> dict[tuple[str, str], bool]:
    """The owner's pass/fail per (item, criterion); empty labels are left out."""
    labels: dict[tuple[str, str], bool] = {}
    for entry in entries:
        item_id = entry.get("id")
        if not isinstance(item_id, str) or item_id not in items:
            raise JudgeCheckError(f"{LABELS_FILE}: unknown item {item_id!r}")
        criteria = entry.get("criteria")
        expected = set(rubrics[items[item_id]["rubric"]].criteria)
        if not isinstance(criteria, dict) or set(criteria) != expected:
            raise JudgeCheckError(f"{LABELS_FILE} {item_id}: criteria must be {sorted(expected)}")
        for name, criterion in criteria.items():
            label = criterion.get("label") if isinstance(criterion, dict) else None
            if label is None:
                continue
            if not isinstance(label, str) or label.strip().casefold() not in LABELS:
                raise JudgeCheckError(
                    f"{LABELS_FILE} {item_id} {name}: label must be pass or fail, got {label!r}"
                )
            labels[(item_id, name)] = LABELS[label.strip().casefold()]
    return labels


def item_material(item: Mapping[str, Any]) -> str:
    """What the judge sees for an item, built exactly as during a run."""
    finals = {language: parse_final_answer(answer) for language, answer in item["answers"].items()}
    if item["rubric"] == PAIR_RUBRIC_NAME:
        return pair_material(item["questions"], finals, item["sources"])
    [(language, final)] = finals.items()
    return single_material(item["questions"][language], final, item["sources"], item["planted"])


def recorded_agreement(pack: Path) -> dict[str, Any] | None:
    """The pack's last measured judge agreement, or None if it was never measured."""
    path = check_dir(pack) / AGREEMENT_FILE
    return read_json(path) if path.exists() else None


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JudgeCheckError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise JudgeCheckError(f"{path} is not a JSON object")
    return value


INSTRUCTIONS = """\
# Judge-check labels (ADR-0009). Label every item without looking at verdicts.json.
#
# Each item is one agent answer (or, for bilingual items, an English and an Arabic answer to
# the same question). You see what the judge saw: the question, the answer, the text of the
# articles the answer cites as the agent retrieved it, and any planted (fake) chunks.
#
# For every criterion under an item, read its rule and replace the empty `label:` with
#   pass   the answer meets the rule
#   fail   it does not
# Judge only against the rule and the text shown, not your own knowledge of the law: a claim
# that is true but not in the cited text is unsupported. Leave a label empty if you cannot
# decide; empty labels are left out of the agreement figures. `note:` is free text for you.
#
# When done, run `uv run eval judge-agreement`. Commit this file: the labels are frozen with
# the cases.
#
# What each rubric is about:
"""


def labels_text(items: Mapping[str, dict[str, Any]], rubrics: Mapping[str, Rubric]) -> str:
    """The blind labelling file: instructions, then one entry per item, with no verdicts."""
    used = sorted({item["rubric"] for item in items.values()})
    preambles = "".join(
        f"#\n# {name}:\n"
        + "".join(
            f"#   {line}".rstrip() + "\n"
            for line in rubrics[name].preamble.splitlines()
            if not line.startswith("#")
        )
        for name in used
    )
    entries = [
        _label_entry(item_id, item, rubrics[item["rubric"]]) for item_id, item in items.items()
    ]
    body = yaml.dump(entries, Dumper=_LabelsDumper, allow_unicode=True, sort_keys=False, width=100)
    return INSTRUCTIONS + preambles + "\n" + body


def _label_entry(item_id: str, item: dict[str, Any], rubric: Rubric) -> dict[str, Any]:
    questions = item["questions"]
    answers = {language: _label_answer(answer) for language, answer in item["answers"].items()}
    single = len(questions) == 1
    entry: dict[str, Any] = {
        "id": item_id,
        "rubric": item["rubric"],
        "question": next(iter(questions.values())) if single else questions,
        "answer": next(iter(answers.values())) if single else answers,
        "sources": [_label_chunk(c) for c in item["sources"]],
    }
    if item["planted"]:
        entry["planted"] = [_label_chunk(c) for c in item["planted"]]
    entry["criteria"] = {name: {"rule": text, "label": None} for name, text in rubric.rules.items()}
    entry["note"] = None
    return entry


def _label_answer(answer: dict[str, Any]) -> dict[str, Any]:
    reason = {"refusal_reason": answer["refusal_reason"]} if answer["refusal_reason"] else {}
    return {
        "status": answer["status"],
        **reason,
        "text": answer["answer"],
        "citations": [article_label(c["instrument"], c["article"]) for c in answer["citations"]],
    }


def _label_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chunk["id"],
        "article": article_label(chunk["instrument"], chunk["article"]),
        "text": chunk["text"],
    }


class _LabelsDumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value or len(value) > 80 else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


def _represent_none(dumper: yaml.SafeDumper, _: None) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


_LabelsDumper.add_representer(str, _represent_str)
_LabelsDumper.add_representer(type(None), _represent_none)


def read_labels(path: Path) -> list[dict[str, Any]]:
    try:
        entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise JudgeCheckError(f"cannot read {path}: {exc}") from exc
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise JudgeCheckError(f"{path}: expected a list of items")
    return entries


def _filled_labels(entries: list[dict[str, Any]]) -> list[Any]:
    return [
        criterion.get("label")
        for entry in entries
        for criterion in (entry.get("criteria") or {}).values()
        if isinstance(criterion, dict) and criterion.get("label") is not None
    ]
