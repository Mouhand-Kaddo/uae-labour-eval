"""The runner: resolve prices, select cases, ask the budget guard, run, score, record."""

import itertools
import json
import secrets
import subprocess
import time
from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_harness.agent import Tool, run_agent
from eval_harness.budget import (
    decide_start,
    estimate_run_cost,
    remaining_budget,
    should_abort,
)
from eval_harness.cases import CONSISTENCY, Case, CaseError, case_set_hash
from eval_harness.config import Config, same_family
from eval_harness.final_answer import FinalAnswer
from eval_harness.ingest import Chunk, IngestError
from eval_harness.judge import (
    PAIR_RUBRIC,
    JudgeUnavailable,
    Rubric,
    RubricError,
    judge_scorer,
    load_rubrics,
    pair_judge,
    resolve_judge,
)
from eval_harness.judge_check import recorded_agreement
from eval_harness.ledger import Ledger
from eval_harness.manifest import Manifest, ManifestError, load_manifest
from eval_harness.openrouter import (
    ChatResponse,
    EmbeddingResponse,
    ModelInfo,
    OpenRouterClient,
    OpenRouterError,
)
from eval_harness.pack import PackError, load_pack_cases, load_pack_tools, mark_open_questions
from eval_harness.refs import article_key
from eval_harness.scorers import (
    SCORERS,
    PairScorer,
    Scorer,
    consistency_scorer,
    score_case,
    score_pair,
)
from eval_harness.search import SearchIndex, search_tools
from eval_harness.trace import Trace

ASSUMED_TOKENS_PER_SEARCH_QUERY = 64


class RunRefused(Exception):
    """The run did not start; nothing was spent."""


class _BudgetCrossed(Exception):
    pass


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    repeat: int
    category: str
    reviewed: bool
    status: str
    passed: bool
    cost_usd: float
    latency_s: float
    sent_back: int
    """Final answers the agent loop sent back for citing articles no tool returned."""


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    cases: list[CaseResult]
    run_spend_usd: float
    cumulative_usd: float
    remaining_usd: float


def run_eval(
    config: Config,
    client: OpenRouterClient,
    *,
    model_id: str,
    category: str | None = None,
    case_ids: list[str] | None = None,
    limit: int | None = None,
    repeats: int = 1,
    echo: Callable[[str], None] = print,
) -> RunResult:
    """Run the selected cases against one model. Raises RunRefused if the guard says no."""
    plan = _plan(config, client, model_id, category, case_ids, limit)
    ledger = Ledger(config.ledger_path)
    ledger_total = ledger.total()
    estimate = _estimate(config, plan, ledger, category, repeats)
    key_usage, remaining_usd, reason = _ask_guard(config, client, estimate, ledger_total)
    echo(f"budget ok: {reason}")

    started_at = datetime.now(UTC)
    run_id = f"{started_at:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
    run_dir = config.runs_dir / run_id
    spend = _Spend(ledger, run_id, remaining_usd)
    run = _Run(client, config, plan, spend, run_dir)
    results: list[CaseResult] = []
    status = "completed"
    for repeat, case in itertools.product(range(1, repeats + 1), plan.cases):
        result, crossed = run.case(case, repeat)
        results.append(result)
        if crossed:
            status = "aborted"
            break
        echo(_case_line(result))

    cumulative = max(ledger.total(), key_usage + spend.run_usd)
    remaining = remaining_budget(
        config.budget.ceiling_usd, ledger.total(), key_usage + spend.run_usd
    )
    outcome = RunResult(run_id, status, results, spend.run_usd, cumulative, remaining)
    reviewed, unreviewed = _tally(results, reviewed=True), _tally(results, reviewed=False)
    _write_summary(
        run_dir,
        outcome,
        {
            "started_at": started_at.isoformat(),
            "case_set_hash": plan.cases_hash,
            "manifest_hash": plan.manifest.sha256,
            "git_commit": _git_commit(config),
            "config": asdict(config),
            "model": model_id,
            "models": {
                "agent": config.agent_model,
                "judge": config.judge_model,
                "embedding": config.embedding_model,
            },
            "pricing": asdict(plan.model)
            | {"supported_parameters": sorted(plan.model.supported_parameters)},
            "selection": {
                "category": category,
                "case": case_ids,
                "limit": limit,
                "repeats": repeats,
            },
            "estimate_usd": estimate,
            "ledger_total_at_start_usd": ledger_total,
            "key_usage_at_start_usd": key_usage,
            "reviewed": reviewed,
            "unreviewed": unreviewed,
            "judge_agreement": recorded_agreement(config.pack),
        },
    )
    passed = sum(r.passed for r in results)
    echo(f"run {run_id} {status}: {len(results)} case(s), {passed} passed")
    echo(f"headline (reviewed cases only): {reviewed['passed']}/{reviewed['total']} passed")
    echo(f"unreviewed: {unreviewed['passed']}/{unreviewed['total']} passed, not in the headline")
    echo(
        f"run spend USD {spend.run_usd:.6f}; cumulative USD {cumulative:.6f}; "
        f"remaining USD {remaining:.6f}"
    )
    return outcome


@dataclass(frozen=True)
class _Plan:
    """Everything a run needs, checked before the budget guard is asked."""

    model: ModelInfo
    embedding: ModelInfo
    cases: list[Case]
    rubrics: dict[str, Rubric]
    pair_rubric: Rubric | None
    judge: ModelInfo | None
    judged_per_repeat: int
    manifest: Manifest
    index: SearchIndex
    system_prompt: str
    tools: list[Tool]
    cases_hash: str

    @property
    def agent_runs(self) -> int:
        """Agent runs per repeat: two for a bilingual pair, one for any other case."""
        return sum(len(case.inputs()) for case in self.cases)

    @property
    def instruments(self) -> dict[str, str]:
        return {
            s.instrument: self.manifest.instruments[s.instrument]
            for s in self.manifest.indexed_sources
        }


def _plan(
    config: Config,
    client: OpenRouterClient,
    model_id: str,
    category: str | None,
    case_ids: list[str] | None,
    limit: int | None,
) -> _Plan:
    models = client.models()
    if model_id not in models:
        raise RunRefused(f"model {model_id!r} is not in the OpenRouter models list")
    embedding_models = client.embedding_models()
    if config.embedding_model not in embedding_models:
        raise RunRefused(
            f"embedding model {config.embedding_model!r} is not in the OpenRouter embeddings list"
        )
    if same_family(model_id, config.judge_model):
        raise RunRefused(
            f"the agent {model_id!r} is from the same model family as the judge "
            f"{config.judge_model!r}"
        )
    try:
        rubrics = load_rubrics(config.pack)
        pack_cases = load_pack_cases(config, rubrics)
    except RubricError as exc:
        raise RunRefused(str(exc)) from exc
    except CaseError as exc:
        raise RunRefused(f"invalid cases: {exc}") from exc
    pair_rubric = rubrics.pop(PAIR_RUBRIC, None)
    cases = _select_cases(pack_cases.cases, category, case_ids, limit)
    pairs = sum(case.is_pair for case in cases)
    if pairs and pair_rubric is None:
        raise RunRefused(
            f"bilingual cases need the rubric {config.pack / 'evals' / 'rubrics' / 'bilingual.md'}"
        )
    judged_per_repeat = pairs + sum(
        len(case.inputs()) for case in cases for name in case.scoring if name in rubrics
    )
    try:
        judge = resolve_judge(config.judge_model, models) if judged_per_repeat else None
    except JudgeUnavailable as exc:
        raise RunRefused(str(exc)) from exc
    if judge is not None:
        judge = _as_routed(client, judge, config.provider_for(judge.id))
    manifest, index = _load_corpus(config)
    _check_planted_chunks(cases, index)
    try:
        tools = load_pack_tools(config.pack)
    except PackError as exc:
        raise RunRefused(str(exc)) from exc
    if pack_cases.open_questions is not None:
        tools = mark_open_questions(tools, pack_cases.open_questions)
    return _Plan(
        model=_as_routed(client, models[model_id], config.provider_for(model_id)),
        embedding=embedding_models[config.embedding_model],
        cases=cases,
        rubrics=rubrics,
        pair_rubric=pair_rubric,
        judge=judge,
        judged_per_repeat=judged_per_repeat,
        manifest=manifest,
        index=index,
        system_prompt=(config.pack / "system_prompt.md").read_text(encoding="utf-8"),
        tools=tools,
        cases_hash=case_set_hash(config.pack / "evals" / "cases"),
    )


def _estimate(
    config: Config, plan: _Plan, ledger: Ledger, category: str | None, repeats: int
) -> float:
    """The run's cost estimate: agent runs, from ledger history if any, plus judge calls, plus
    query embeddings, assuming at most one search per agent turn. Every price is the model's
    peak for a call of the assumed prompt size (and history is scaled up to it), since a
    surcharge window can double the price; size surcharges above that prompt size are left out."""
    prompt_tokens = config.budget.assumed_prompt_tokens_per_case
    history = ledger.per_case_average(model=plan.model.id, category=category)
    agent_prompt_price, agent_completion_price = plan.model.peak_prices(prompt_tokens)
    estimate = estimate_run_cost(
        case_count=plan.agent_runs * repeats,
        history_per_case_usd=None
        if history is None
        else history * plan.model.peak_factor(prompt_tokens),
        prompt_price_usd=agent_prompt_price,
        completion_price_usd=agent_completion_price,
        assumed_prompt_tokens=prompt_tokens,
        assumed_completion_tokens=config.budget.assumed_completion_tokens_per_case,
        margin=config.budget.safety_margin,
    )
    if plan.judge is not None:
        judge_prompt_price, judge_completion_price = plan.judge.peak_prices(prompt_tokens)
        estimate += estimate_run_cost(
            case_count=plan.judged_per_repeat * repeats,
            history_per_case_usd=None,
            prompt_price_usd=judge_prompt_price,
            completion_price_usd=judge_completion_price,
            assumed_prompt_tokens=prompt_tokens,
            assumed_completion_tokens=config.budget.assumed_completion_tokens_per_case,
            margin=config.budget.safety_margin,
        )
    estimate += estimate_run_cost(
        case_count=plan.agent_runs * repeats * config.agent.max_turns,
        history_per_case_usd=None,
        prompt_price_usd=plan.embedding.peak_prices(ASSUMED_TOKENS_PER_SEARCH_QUERY)[0],
        completion_price_usd=0.0,
        assumed_prompt_tokens=ASSUMED_TOKENS_PER_SEARCH_QUERY,
        assumed_completion_tokens=0,
        margin=config.budget.safety_margin,
    )
    return estimate


def _ask_guard(
    config: Config, client: OpenRouterClient, estimate: float, ledger_total: float
) -> tuple[float, float, str]:
    """The key's usage, the remaining budget and the guard's reason for going ahead; raises
    RunRefused when the guard says no."""
    try:
        key_usage: float | None = client.key_usage()
    except OpenRouterError:
        key_usage = None
    decision = decide_start(
        estimate_usd=estimate,
        ledger_total_usd=ledger_total,
        key_usage_usd=key_usage,
        ceiling_usd=config.budget.ceiling_usd,
    )
    if not decision.allowed or key_usage is None or decision.remaining_usd is None:
        raise RunRefused(decision.reason)
    return key_usage, decision.remaining_usd, decision.reason


@dataclass
class _Spend:
    """Appends each paid call to the ledger against the current case and keeps the run's and
    the case's spend; raises _BudgetCrossed once the run's spend crosses the budget that
    remained when it started."""

    ledger: Ledger
    run_id: str
    remaining_usd: float
    run_usd: float = 0.0
    case_usd: float = 0.0
    case: Case | None = None
    repeat: int | None = None

    def start_case(self, case: Case, repeat: int) -> None:
        self.case, self.repeat, self.case_usd = case, repeat, 0.0

    def record(self, response: ChatResponse | EmbeddingResponse, purpose: str, model: str) -> None:
        assert self.case is not None
        self.ledger.append(
            run_id=self.run_id,
            purpose=purpose,
            model=model,
            usage=response.usage,
            case_id=self.case.id,
            category=self.case.category,
            repeat=self.repeat,
            provider=response.provider if isinstance(response, ChatResponse) else None,
        )
        self.run_usd += response.cost
        self.case_usd += response.cost
        if should_abort(run_spend_usd=self.run_usd, remaining_usd=self.remaining_usd):
            raise _BudgetCrossed


@dataclass
class _Run:
    """Runs and scores one case at a time; the judge scorers are built once, for the run."""

    client: OpenRouterClient
    config: Config
    plan: _Plan
    spend: _Spend
    run_dir: Path
    scorers: dict[str, Scorer] = field(init=False)
    pair_scorers: dict[str, PairScorer] = field(init=False)

    def __post_init__(self) -> None:
        self.scorers, self.pair_scorers = dict(SCORERS), {}
        judge = self.plan.judge
        if judge is None:
            return

        def record_judge(response: ChatResponse) -> None:
            self.spend.record(response, "judge", judge.id)

        settings = self.config.judge
        provider = self.config.provider_for(judge.id)
        self.scorers |= {
            name: judge_scorer(
                self.client,
                model=judge,
                rubric=rubric,
                settings=settings,
                provider=provider,
                on_response=record_judge,
            )
            for name, rubric in self.plan.rubrics.items()
        }
        if self.plan.pair_rubric is not None:
            self.pair_scorers[CONSISTENCY] = consistency_scorer(
                pair_judge(
                    self.client,
                    model=judge,
                    rubric=self.plan.pair_rubric,
                    settings=settings,
                    provider=provider,
                    on_response=record_judge,
                )
            )

    def case(self, case: Case, repeat: int) -> tuple[CaseResult, bool]:
        """Run and score one case; returns its result and whether the budget was crossed."""
        self.spend.start_case(case, repeat)
        trace = Trace(self.run_dir / "traces" / f"{case.id}.{repeat}.jsonl")
        trace.add(
            "case",
            case_id=case.id,
            category=case.category,
            language=case.language,
            input=case.input,
            model=self.plan.model.id,
            repeat=repeat,
        )
        started = time.monotonic()
        try:
            finals, halves = self._answer(case, trace)
        except _BudgetCrossed:
            return self._aborted(case, repeat, trace, time.monotonic() - started), True
        latency = round(time.monotonic() - started, 3)
        try:
            status, passed = _score(
                case, finals, halves, trace, self.scorers, self.pair_scorers, self.plan.rubrics
            )
        except _BudgetCrossed:
            return self._aborted(case, repeat, trace, latency), True
        result = CaseResult(
            case.id,
            repeat,
            case.category,
            case.reviewed,
            status,
            passed,
            self.spend.case_usd,
            latency,
            _sent_back(trace),
        )
        return result, False

    def _answer(
        self, case: Case, trace: Trace
    ) -> tuple[dict[str, FinalAnswer] | None, dict[str, list[dict[str, Any]]]]:
        """Put each of the case's questions to the agent; no answers if a call failed."""
        planted = case.planted_chunks or []

        def record_agent(response: ChatResponse) -> None:
            self.spend.record(response, "agent", self.plan.model.id)

        def embed_query(query: str) -> list[float]:
            response = self.client.embed(self.config.embedding_model, [query])
            self.spend.record(response, "embedding", self.config.embedding_model)
            return response.vectors[0]

        def record_retrieval(tool: str, chunks: list[Chunk]) -> None:
            trace.add(
                "retrieval",
                tool=tool,
                chunks=[
                    {
                        "id": c.id,
                        "instrument": c.instrument,
                        "article": c.article,
                        "text": c.text,
                        **({"planted": True} if c in planted else {}),
                    }
                    for c in chunks
                ],
            )

        finals: dict[str, FinalAnswer] = {}
        halves: dict[str, list[dict[str, Any]]] = {}
        try:
            for language, user_input in case.inputs().items():
                if case.is_pair:
                    trace.add("half", language=language, input=user_input)
                first_step = len(trace.steps)
                finals[language] = run_agent(
                    self.client,
                    model=self.plan.model,
                    system_prompt=self.plan.system_prompt,
                    user_input=user_input,
                    tools=[
                        *search_tools(
                            self.plan.index,
                            self.plan.instruments,
                            record_retrieval,
                            embed_query,
                            planted,
                        ),
                        *self.plan.tools,
                    ],
                    settings=self.config.agent,
                    provider=self.config.provider_for(self.plan.model.id),
                    trace=trace,
                    on_response=record_agent,
                )
                halves[language] = trace.steps[first_step:]
        except OpenRouterError as exc:
            trace.add("error", message=str(exc))
            return None, halves
        return finals, halves

    def _aborted(self, case: Case, repeat: int, trace: Trace, latency: float) -> CaseResult:
        trace.add("aborted", reason="run spend crossed the remaining budget")
        return CaseResult(
            case.id,
            repeat,
            case.category,
            case.reviewed,
            "aborted",
            False,
            self.spend.case_usd,
            round(latency, 3),
            _sent_back(trace),
        )


def _sent_back(trace: Trace) -> int:
    return sum(1 for step in trace.steps if step["type"] == "tool_call" and "unread" in step)


def _as_routed(client: OpenRouterClient, model: ModelInfo, provider: dict[str, Any]) -> ModelInfo:
    """A model held to specific endpoints (`only`, or `order` without fallbacks) is priced at the
    dearest of them and offered only the parameters they all support; the models list prices
    a model at its cheapest endpoint. A pin that matches no endpoint refuses the run."""
    slugs = provider.get("only") or (
        provider.get("order") if provider.get("allow_fallbacks") is False else None
    )
    if not slugs:
        return model
    endpoints = client.endpoints(model.id)
    pinned: list[ModelInfo] = []
    for slug in slugs:
        exact = [info for tag, info in endpoints.items() if tag == slug]
        pinned += exact or [info for tag, info in endpoints.items() if tag.startswith(f"{slug}/")]
    if not pinned:
        raise RunRefused(
            f"no endpoint of {model.id!r} matches the pinned providers {slugs}; "
            f"its endpoints are {sorted(endpoints)}"
        )
    return ModelInfo(
        id=model.id,
        prompt_price_usd=max(e.prompt_price_usd for e in pinned),
        completion_price_usd=max(e.completion_price_usd for e in pinned),
        supported_parameters=model.supported_parameters.intersection(
            *(e.supported_parameters for e in pinned)
        ),
        overrides=tuple(o for e in pinned for o in e.overrides),
    )


def _load_corpus(config: Config) -> tuple[Manifest, SearchIndex]:
    try:
        return load_manifest(config.pack), SearchIndex.load(
            config.index_dir, config.embedding_model
        )
    except (ManifestError, IngestError) as exc:
        raise RunRefused(str(exc)) from exc


def _check_planted_chunks(cases: list[Case], index: SearchIndex) -> None:
    """A planted chunk must claim an article the corpus lacks, so citing it is detectable."""
    corpus_articles = {article_key(c.instrument, c.article) for c in index.chunks}
    for case in cases:
        for chunk in case.planted_chunks or []:
            if article_key(chunk.instrument, chunk.article) in corpus_articles:
                raise RunRefused(
                    f"case {case.id!r}: planted chunk {chunk.id} claims an article that is in "
                    "the corpus; give it an article number the corpus does not have"
                )


def _select_cases(
    cases: list[Case], category: str | None, case_ids: list[str] | None, limit: int | None
) -> list[Case]:
    if case_ids is not None:
        unknown = sorted(set(case_ids) - {c.id for c in cases})
        if unknown:
            raise RunRefused(f"no cases match the selection: unknown case IDs {unknown}")
    selected = [
        c
        for c in cases
        if category in (None, c.category) and (case_ids is None or c.id in case_ids)
    ]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise RunRefused("no cases match the selection")
    return selected


def _git_commit(config: Config) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.pack,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:
        return None
    return completed.stdout.strip()


def _tally(results: list[CaseResult], *, reviewed: bool) -> dict[str, Any]:
    group = [r for r in results if r.reviewed == reviewed]
    by_category: dict[str, dict[str, int]] = {}
    for result in group:
        counts = by_category.setdefault(result.category, {"total": 0, "passed": 0})
        counts["total"] += 1
        counts["passed"] += result.passed
    return {"total": len(group), "passed": sum(r.passed for r in group), "by_category": by_category}


def _score(
    case: Case,
    finals: dict[str, FinalAnswer] | None,
    halves: dict[str, list[dict[str, Any]]],
    trace: Trace,
    scorers: dict[str, Scorer],
    pair_scorers: dict[str, PairScorer],
    deferred: Collection[str],
) -> tuple[str, bool]:
    """The case's status and whether it passed, with its verdict added to the trace."""
    if finals is None:
        trace.add("verdict", passed=False, details={"error": "the case did not finish"})
        return "error", False
    if case.is_pair:
        verdict = score_pair(case, finals, halves, scorers, pair_scorers, deferred)
    else:
        verdict = score_case(case, finals[case.language], trace.steps, scorers, deferred)
    trace.add("verdict", passed=verdict.passed, details=verdict.details)
    statuses = {final.status for final in finals.values()}
    status = (
        statuses.pop()
        if len(statuses) == 1
        else " ".join(f"{language}={final.status}" for language, final in finals.items())
    )
    return status, verdict.passed


def _case_line(result: CaseResult) -> str:
    mark = "PASS" if result.passed else "FAIL"
    reviewed = "" if result.reviewed else " [unreviewed]"
    return (
        f"{mark} {result.case_id} (repeat {result.repeat}) status={result.status} "
        f"cost USD {result.cost_usd:.6f} latency {result.latency_s:.2f}s{reviewed}"
    )


def _write_summary(run_dir, run: RunResult, context: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run.run_id,
        "status": run.status,
        **context,
        "run_spend_usd": run.run_spend_usd,
        "cumulative_usd": run.cumulative_usd,
        "remaining_usd": run.remaining_usd,
        "cases": [asdict(c) for c in run.cases],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
