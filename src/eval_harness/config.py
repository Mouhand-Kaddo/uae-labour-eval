"""config.toml: model IDs, pack path, agent caps and budget, with paths relative to the file."""

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
class BudgetSettings:
    ceiling_usd: float
    safety_margin: float
    assumed_prompt_tokens_per_case: int
    assumed_completion_tokens_per_case: int


@dataclass(frozen=True)
class Config:
    pack: Path
    runs_dir: Path
    agent_model: str
    judge_model: str
    embedding_model: str
    agent: AgentSettings
    budget: BudgetSettings

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
        return Config(
            pack=base / raw["pack"],
            runs_dir=base / raw["runs_dir"],
            agent_model=raw["models"]["agent"],
            judge_model=raw["models"]["judge"],
            embedding_model=raw["models"]["embedding"],
            agent=AgentSettings(**raw["agent"]),
            budget=BudgetSettings(**raw["budget"]),
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"{path}: missing or unexpected setting: {exc}") from exc
