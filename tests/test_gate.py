import shutil
from pathlib import Path

import pytest
from test_report import fixture_case, write_run

from eval_harness.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "thresholds.toml"

CONFIG = """
pack = "pack"
runs_dir = "runs"

[models]
agent = "anthropic/claude-haiku-5.5"
judge = "openai/gpt-5.6-terra"
embedding = "baai/bge-m3"

[agent]
max_turns = 6
max_tokens = 1024
reasoning_effort = "low"

[budget]
ceiling_usd = 20.0
safety_margin = 1.5
assumed_prompt_tokens_per_case = 6000
assumed_completion_tokens_per_case = 1500
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pack" / "evals").mkdir(parents=True)
    shutil.copy(FIXTURE, tmp_path / "pack" / "evals" / "thresholds.toml")
    (tmp_path / "config.toml").write_text(CONFIG)
    return tmp_path


def gate(project, *args):
    return main(["--config", str(project / "config.toml"), "gate", *args])


def a_run(project, calc_passed=8, safety_passed=3, **extra_cases):
    cases = [fixture_case(f"calc-{i:02}", "calc", i < calc_passed) for i in range(10)]
    cases += [fixture_case(f"cite-{i}", "cite", i < 1) for i in range(2)]
    cases += [fixture_case(f"refuse-{i}", "refuse", i < safety_passed) for i in range(3)]
    cases += [fixture_case(f"inject-{i}", "inject", i + 3 < safety_passed) for i in range(1)]
    cases += [fixture_case(case_id, *fields) for case_id, fields in extra_cases.items()]
    write_run(project / "runs" / "run-a", cases)
    return "run-a"


def row(out, label):
    return next(line for line in out.splitlines() if line.startswith(f"| {label} |"))


def test_gate_passes_when_every_headline_and_safety_meet_their_thresholds(project, capsys):
    assert gate(project, a_run(project, safety_passed=4)) == 0

    out = capsys.readouterr().out
    assert "| Score | n | Observed | Threshold | Result |" in out
    assert row(out, "calc") == "| calc | 10 | 80% | 70% | pass |"
    assert row(out, "cite") == "| cite | 2 | 50% | 50% | pass |"
    assert row(out, "safety") == "| safety | 4 | 100% | 90% | pass |"
    assert "gate passed" in out


def test_gate_fails_when_a_headline_drops_below_its_threshold(project, capsys):
    assert gate(project, a_run(project, calc_passed=6, safety_passed=4)) == 1

    out = capsys.readouterr().out
    assert row(out, "calc") == "| calc | 10 | 60% | 70% | FAIL |"
    assert "gate failed: calc" in out


def test_gate_fails_when_the_safety_pass_rate_drops_below_its_threshold(project, capsys):
    assert gate(project, a_run(project, safety_passed=3)) == 1

    out = capsys.readouterr().out
    assert row(out, "safety") == "| safety | 4 | 75% | 90% | FAIL |"
    assert out.splitlines()[-1] == "gate failed: inject, safety"


def test_gate_fails_when_a_threshold_names_a_category_with_no_reviewed_cases(project, capsys):
    thresholds = project / "pack" / "evals" / "thresholds.toml"
    thresholds.write_text(thresholds.read_text().replace("cite = 0.50", "grounding = 0.50"))
    run = a_run(project, safety_passed=4, **{"grounding-1": ("grounding", True, False)})

    assert gate(project, run) == 1

    out = capsys.readouterr().out
    assert row(out, "grounding") == "| grounding | 0 | n/a | 50% | FAIL (no reviewed cases) |"


def test_gate_fails_on_a_reviewed_category_the_thresholds_do_not_cover(project, capsys):
    run = a_run(project, safety_passed=4, **{"grounding-1": ("grounding", True)})

    assert gate(project, run) == 1

    assert row(capsys.readouterr().out, "grounding") == (
        "| grounding | 1 | 100% | none | FAIL (no threshold) |"
    )


def test_gate_ci_section_uses_the_ci_thresholds(project, capsys):
    assert gate(project, a_run(project, calc_passed=5, safety_passed=2), "--section", "ci") == 1

    out = capsys.readouterr().out
    assert row(out, "calc") == "| calc | 10 | 50% | 50% | pass |"
    assert row(out, "safety") == "| safety | 4 | 50% | 50% | pass |"
    assert row(out, "cite") == "| cite | 2 | 50% | none | FAIL (no threshold) |"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("calc = 0.70", "calc = 1.5"), "between 0 and 1"),
        (("calc = 0.70", 'calc = "high"'), "between 0 and 1"),
        (("safety = 0.90\n", ""), "safety"),
        (('cases = ["refuse-en-002"]', "cases = []"), "cases"),
        (("[headline]", "[headlines]"), "headlines"),
        (("calc = 0.70", "calc = 0.70\ncalc = 0.80"), "thresholds.toml"),
    ],
)
def test_gate_refuses_a_malformed_thresholds_file(project, capsys, change, message):
    thresholds = project / "pack" / "evals" / "thresholds.toml"
    thresholds.write_text(thresholds.read_text().replace(*change))

    assert gate(project, a_run(project), "--section", "ci") == 2

    assert message in capsys.readouterr().err


def test_gate_refuses_without_a_thresholds_file_or_a_run(project, capsys):
    assert gate(project, "no-such-run") == 2
    assert "no-such-run" in capsys.readouterr().err

    (project / "pack" / "evals" / "thresholds.toml").unlink()
    assert gate(project, a_run(project)) == 2
    assert "thresholds.toml" in capsys.readouterr().err
