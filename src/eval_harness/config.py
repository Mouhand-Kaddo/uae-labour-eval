"""config.toml: model IDs, pack and data paths, agent caps and budget, relative to the file."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROUTING_LISTS = frozenset({"order", "only", "ignore", "quantizations"})
ROUTING_FLAGS = frozenset({"allow_fallbacks", "require_parameters", "zdr"})
ROUTING_CHOICES = frozendict(
    sort=("price", "throughput", "latency"), data_collection=("allow", "deny")
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class AgentSettings:
    max_turns: int
    max_tokens: int
    reasoning_effort: str


@dataclass(frozen=True)
class JudgeSettings:
    max_tokens: int = 2048
    reasoning_effort: str = "low"


@dataclass(frozen=True)
class BudgetSettings:
    ceiling_usd: float
    safety_margin: float
    assumed_prompt_tokens_per_case: int
    assumed_completion_tokens_per_case: int


@dataclass(frozen=True)
class Config:
    pack: Path
    runs_dir: Path
    sources_dir: Path
    index_dir: Path
    agent_model: str
    judge_model: str
    embedding_model: str
    agent: AgentSettings
    budget: BudgetSettings
    open_questions: Path | None = None
    judge: JudgeSettings = JudgeSettings()
    provider_routing: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def ledger_path(self) -> Path:
        return self.runs_dir / "ledger.jsonl"

    def provider_for(self, model_id: str) -> dict[str, Any]:
        """The OpenRouter `provider` object for calls to this model: the model's configured
        routing, always with `require_parameters` so tools and structured outputs are honoured."""
        return {"require_parameters": True, **self.provider_routing.get(model_id, {})}


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    base = path.parent
    try:
        config = Config(
            pack=base / raw["pack"],
            runs_dir=base / raw["runs_dir"],
            sources_dir=base / raw.get("sources_dir", "data/sources"),
            index_dir=base / raw.get("index_dir", "data/index"),
            agent_model=raw["models"]["agent"],
            judge_model=raw["models"]["judge"],
            embedding_model=raw["models"]["embedding"],
            agent=AgentSettings(**raw["agent"]),
            budget=BudgetSettings(**raw["budget"]),
            open_questions=base / raw["open_questions"] if "open_questions" in raw else None,
            judge=JudgeSettings(**raw.get("judge", {})),
            provider_routing=_provider_routing(path, raw.get("provider_routing", {})),
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"{path}: missing or unexpected setting: {exc}") from exc
    if same_family(config.agent_model, config.judge_model):
        raise ConfigError(
            f"{path}: the judge {config.judge_model!r} is from the same model family as the "
            f"agent {config.agent_model!r}; pick a judge from another family"
        )
    return config


def _provider_routing(path: Path, raw: Any) -> dict[str, dict[str, Any]]:
    """`[provider_routing."<model id>"]` tables, checked against OpenRouter's `provider` fields."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: provider_routing must be a table of model IDs")
    for model_id, routing in raw.items():
        where = f"{path}: provider_routing.{model_id!r}"
        if "/" not in model_id:
            raise ConfigError(f"{where}: keys are OpenRouter model IDs like 'vendor/model'")
        if not isinstance(routing, dict):
            raise ConfigError(f"{where} must be a table")
        for name, value in routing.items():
            _check_routing_field(where, name, value)
    return raw


def _check_routing_field(where: str, name: str, value: Any) -> None:
    if name in ROUTING_LISTS:
        if not (
            isinstance(value, list)
            and value
            and all(isinstance(v, str) and v.strip() for v in value)
        ):
            raise ConfigError(f"{where}.{name} must be a non-empty list of provider slugs")
    elif name in ROUTING_FLAGS:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}.{name} must be true or false")
        if name == "require_parameters" and not value:
            raise ConfigError(f"{where}.require_parameters must stay true (ADR-0002)")
    elif name in ROUTING_CHOICES:
        if value not in ROUTING_CHOICES[name]:
            raise ConfigError(f"{where}.{name} must be one of {list(ROUTING_CHOICES[name])}")
    else:
        known = sorted(ROUTING_LISTS | ROUTING_FLAGS | ROUTING_CHOICES.keys())
        raise ConfigError(f"{where}: unknown routing field {name!r}; known: {known}")


def same_family(model_a: str, model_b: str) -> bool:
    """Models share a family when their OpenRouter IDs share the provider prefix."""
    return _family(model_a) == _family(model_b)


def _family(model_id: str) -> str:
    return model_id.partition("/")[0].strip().lstrip("~").casefold()
