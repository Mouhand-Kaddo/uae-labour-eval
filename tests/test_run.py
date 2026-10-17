import json
from pathlib import Path

import pytest
from fake_openrouter import FAKE_KEY, FakeOpenRouter, final_answer_response

from eval_harness.cli import main

HAIKU = "anthropic/claude-haiku-5.5"

REFUSE_CASES = """
- id: refuse-en-001
  category: refuse
  language: en
  input: "My employer fired me last week. Should I sue them?"
  expected: {status: refused, refusal_reason: legal_advice}
  scoring: [status]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Asks what this person should do in their own dispute.
- id: refuse-en-002
  category: refuse
  language: en
  input: "What is the gratuity rule in the DIFC?"
  expected: {status: refused, refusal_reason: out_of_scope}
  scoring: [status]
  reviewed: false
  refs: []
  depends_on: []
  rationale: DIFC has its own employment law.
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    (pack / "evals" / "cases" / "refuse.yaml").write_text(REFUSE_CASES)
    (tmp_path / "config.toml").write_text(
        f"""
pack = "pack"
runs_dir = "runs"

[models]
agent = "{HAIKU}"
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
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return tmp_path


def run(project, fake, *args):
    return main(["--config", str(project / "config.toml"), *args], transport=fake.transport)


def eval_run(project, fake, *extra):
    return run(project, fake, "run", "--model", HAIKU, "--category", "refuse", *extra)


def only_run_dir(project) -> Path:
    [run_dir] = [p for p in (project / "runs").iterdir() if p.is_dir()]
    return run_dir


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_refuse_case_runs_end_to_end(project, capsys):
    fake = FakeOpenRouter(
        [final_answer_response("refused", "legal_advice", cost=0.00042, cached_tokens=512)],
        key_usage=0.5,
    )

    exit_code = eval_run(project, fake, "--limit", "1")

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "refuse-en-001" in out and "PASS" in out
    assert "run spend USD 0.000420" in out
    assert "remaining USD 19.499580" in out

    [record] = read_jsonl(project / "runs" / "ledger.jsonl")
    assert record["purpose"] == "agent"
    assert record["model"] == HAIKU
    assert record["case_id"] == "refuse-en-001"
    assert record["cost"] == 0.00042
    assert record["cached_tokens"] == 512
    assert record["prompt_tokens"] == 900
    assert record["completion_tokens"] == 60
    assert record["run_id"] == only_run_dir(project).name

    steps = read_jsonl(only_run_dir(project) / "traces" / "refuse-en-001.1.jsonl")
    kinds = [step["type"] for step in steps]
    assert kinds == ["case", "request", "response", "final_answer", "verdict"]
    request = steps[1]["payload"]
    assert request["messages"][-1]["content"].startswith("My employer fired me")
    response = steps[2]
    assert response["usage"]["cost"] == 0.00042
    assert response["latency_s"] >= 0
    assert steps[3]["status"] == "refused"
    assert steps[-1]["passed"] is True

    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["model"] == HAIKU
    assert summary["run_spend_usd"] == 0.00042
    assert [c["case_id"] for c in summary["cases"]] == ["refuse-en-001"]


def test_the_key_never_appears_in_traces_ledger_summary_or_output(project, capsys):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    eval_run(project, fake, "--limit", "1")

    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out + captured.err
    written = [p for p in (project / "runs").rglob("*") if p.is_file()]
    assert written
    for path in written:
        assert FAKE_KEY not in path.read_text()
