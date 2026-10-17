from pathlib import Path

import pytest

from eval_harness.cases import load_cases, load_open_questions
from eval_harness.config import load_config
from eval_harness.manifest import load_manifest
from eval_harness.pack import load_pack_tools
from eval_harness.scorers import SCORERS

REPO = Path(__file__).resolve().parent.parent
CONFIG = load_config(REPO / "config.toml")
CASES = load_cases(
    CONFIG.pack / "evals" / "cases", SCORERS, load_open_questions(CONFIG.open_questions)
)
TOOLS = {tool.name: tool for tool in load_pack_tools(CONFIG.pack)}
GRATUITY_CASES = [
    pytest.param(case, id=case.id)
    for case in CASES
    if case.expected.get("tool_call", {}).get("name") == "calculate_gratuity"
]


def test_committed_config_points_at_a_pack_whose_cases_load():
    assert CONFIG.budget.ceiling_usd == 20.0
    assert (CONFIG.pack / "system_prompt.md").is_file()
    assert any(case.category == "refuse" for case in CASES)
    assert not any(case.reviewed for case in CASES)


def test_committed_manifest_indexes_only_the_english_labour_law_for_now():
    manifest = load_manifest(CONFIG.pack)

    assert [s.id for s in manifest.indexed_sources] == ["labour-law-en"]
    assert all(s.wayback_url.startswith("https://web.archive.org/web/") for s in manifest.sources)


def test_committed_pack_offers_the_gratuity_tool():
    assert "calculate_gratuity" in TOOLS


def test_gratuity_cases_are_about_fifteen_and_split_between_english_and_arabic():
    languages = [case.language for case in (p.values[0] for p in GRATUITY_CASES)]

    assert 14 <= len(languages) <= 16
    assert abs(languages.count("en") - languages.count("ar")) <= 1


@pytest.mark.parametrize("case", GRATUITY_CASES)
def test_gratuity_case_is_scored_on_the_tool_call_and_its_hand_worked_figure(case):
    assert {"status", "tool_call"} <= set(case.scoring)
    if "numeric" in case.scoring:
        assert case.expected["numbers"]
    assert case.rationale.strip()
    assert all(question.startswith("OQ-") for question in case.depends_on)


@pytest.mark.parametrize("case", GRATUITY_CASES)
def test_gratuity_case_hand_worked_figure_agrees_with_the_tool(case):
    result = TOOLS["calculate_gratuity"].run(case.expected["tool_call"]["arguments"])

    assert set(result["open_questions"]) <= set(case.depends_on)
    if result["gratuity"] is None:
        assert "numeric" not in case.scoring
    elif "numeric" in case.scoring:
        tolerance = case.expected.get("tolerance", 0)
        assert any(abs(result["gratuity"] - n) <= tolerance for n in case.expected["numbers"])
