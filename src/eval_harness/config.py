"""config.toml: model IDs, pack and data paths, agent caps and budget, relative to the file."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


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

    @property
    def ledger_path(self) -> Path:
        return self.runs_dir / "ledger.jsonl"


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
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"{path}: missing or unexpected setting: {exc}") from exc
    if same_family(config.agent_model, config.judge_model):
        raise ConfigError(
            f"{path}: the judge {config.judge_model!r} is from the same model family as the "
            f"agent {config.agent_model!r}; pick a judge from another family"
        )
    return config


def same_family(model_a: str, model_b: str) -> bool:
    """Models share a family when their OpenRouter IDs share the provider prefix."""
    return _family(model_a) == _family(model_b)


def _family(model_id: str) -> str:
    return model_id.partition("/")[0].strip().lstrip("~").casefold()
