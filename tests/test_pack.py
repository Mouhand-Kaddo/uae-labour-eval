from pathlib import Path

import pytest

from eval_harness.cases import CONSISTENCY, PAIR_LANGUAGES, load_cases, load_open_questions
from eval_harness.config import load_config
from eval_harness.judge import load_rubrics
from eval_harness.manifest import load_manifest
from eval_harness.pack import load_pack_tools
from eval_harness.scorers import SCORERS

REPO = Path(__file__).resolve().parent.parent
CONFIG = load_config(REPO / "config.toml")
RUBRICS = load_rubrics(CONFIG.pack)
CASES = load_cases(
    CONFIG.pack / "evals" / "cases",
    [*SCORERS, *RUBRICS, CONSISTENCY],
    load_open_questions(CONFIG.open_questions),
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
    assert {"judge:grounding", "judge:refusal"} <= RUBRICS.keys()
    assert any("judge:grounding" in case.scoring for case in CASES)
    assert not any(case.reviewed for case in CASES)


def test_committed_manifest_indexes_the_law_and_its_regulations_in_both_languages():
    manifest = load_manifest(CONFIG.pack)

    assert [s.id for s in manifest.indexed_sources] == [
        "labour-law-en",
        "labour-law-ar",
        "executive-regulations-en",
        "executive-regulations-ar",
    ]
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


INJECT_CASES = [pytest.param(case, id=case.id) for case in CASES if case.category == "inject"]


def test_inject_cases_are_eight_in_the_message_and_seven_planted_split_by_language():
    cases = [p.values[0] for p in INJECT_CASES]
    languages = [case.language for case in cases]

    assert sum(case.planted_chunks is None for case in cases) == 8
    assert sum(case.planted_chunks is not None for case in cases) == 7
    assert abs(languages.count("en") - languages.count("ar")) <= 1


@pytest.mark.parametrize("case", INJECT_CASES)
def test_inject_case_is_scored_deterministically_and_by_the_judge(case):
    assert {"status", "inject", "judge:inject"} <= set(case.scoring)
    assert case.expected["canary"].strip()
    assert set(case.expected.get("forbidden_tools", [])) <= set(TOOLS)


PAIRS = [pytest.param(case, id=case.id) for case in CASES if case.language == "both"]


def pair_topic(case):
    expected = case.expected["en"]
    if "tool_call" in expected:
        return "calc"
    return "cite" if "citations" in expected else expected["status"]


def test_bilingual_pairs_are_ten_spread_over_calc_cite_and_refusals():
    cases = [p.values[0] for p in PAIRS]
    topics = [pair_topic(case) for case in cases]

    assert len(cases) == 10
    assert all(case.category == "bilingual" and not case.reviewed for case in cases)
    assert topics.count("calc") >= 3 and topics.count("cite") >= 3
    assert topics.count("refused") >= 2
    assert "judge:bilingual" in RUBRICS


@pytest.mark.parametrize("case", PAIRS)
def test_bilingual_pair_halves_share_their_expectations_and_are_checked_for_language(case):
    assert case.expected["en"] == case.expected["ar"]
    assert {"status", "answer_language", CONSISTENCY} <= set(case.scoring)
    assert case.rationale.strip()


@pytest.mark.parametrize("case", [p for p in PAIRS if pair_topic(p.values[0]) == "calc"])
def test_bilingual_calc_pair_figures_agree_with_the_tool(case):
    for language in PAIR_LANGUAGES:
        expected = case.half(language).expected
        name = expected["tool_call"]["name"]
        result = TOOLS[name].run(expected["tool_call"]["arguments"])
        fields = FIGURES.get(name, ("gratuity",))
        figures = [result[field] for field in fields if result[field] is not None]

        assert {"numeric", "tool_call"} <= set(case.scoring)
        assert set(result["open_questions"]) <= set(case.depends_on)
        for number in expected["numbers"]:
            assert any(abs(f - number) <= expected["tolerance"] for f in figures), number
