from pathlib import Path

from eval_harness.cases import load_cases, load_open_questions
from eval_harness.config import load_config
from eval_harness.scorers import SCORERS

REPO = Path(__file__).resolve().parent.parent


def test_committed_config_points_at_a_pack_whose_cases_load():
    config = load_config(REPO / "config.toml")
    assert config.budget.ceiling_usd == 20.0
    assert (config.pack / "system_prompt.md").is_file()

    questions = load_open_questions(config.open_questions)
    cases = load_cases(config.pack / "evals" / "cases", SCORERS, questions)

    assert any(case.category == "refuse" for case in cases)
    assert not any(case.reviewed for case in cases)
