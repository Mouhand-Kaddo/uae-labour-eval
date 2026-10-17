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


def test_committed_manifest_indexes_the_labour_law_in_both_languages_for_now():
    manifest = load_manifest(CONFIG.pack)

    assert [s.id for s in manifest.indexed_sources] == ["labour-law-en", "labour-law-ar"]
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


FIGURES = {
    "calculate_annual_leave": ("entitlement_days", "balance_days", "cash_out"),
    "check_notice_period": ("pay_in_lieu", "minimum_notice_days", "maximum_notice_days"),
    "check_probation": ("required_notice_days", "maximum_months", "compensation"),
}
LEAVE_NOTICE_PROBATION_CASES = [
    pytest.param(case, id=case.id)
    for case in CASES
    if case.expected.get("tool_call", {}).get("name") in FIGURES
]


def test_committed_pack_offers_the_leave_notice_and_probation_tools():
    assert set(FIGURES) <= set(TOOLS)


def test_leave_notice_and_probation_cases_are_ten_five_five_and_half_arabic():
    cases = [p.values[0] for p in LEAVE_NOTICE_PROBATION_CASES]
    tools = [case.expected["tool_call"]["name"] for case in cases]
    languages = [case.language for case in cases]

    assert tools.count("calculate_annual_leave") == 10
    assert tools.count("check_notice_period") == 5
    assert tools.count("check_probation") == 5
    assert languages.count("en") == languages.count("ar")


@pytest.mark.parametrize("case", LEAVE_NOTICE_PROBATION_CASES)
def test_case_hand_worked_figures_agree_with_the_tool(case):
    name = case.expected["tool_call"]["name"]
    result = TOOLS[name].run(case.expected["tool_call"]["arguments"])
    figures = [result[field] for field in FIGURES[name] if result[field] is not None]
    tolerance = case.expected.get("tolerance", 0)

    assert {"status", "tool_call"} <= set(case.scoring)
    assert case.rationale.strip()
    assert set(result["open_questions"]) <= set(case.depends_on)
    for number in case.expected.get("numbers", []):
        assert any(abs(figure - number) <= tolerance for figure in figures), number
