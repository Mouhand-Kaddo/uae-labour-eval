import hashlib
import json
from pathlib import Path

import pytest
from fake_openrouter import (
    FAKE_KEY,
    FakeOpenRouter,
    final_answer_response,
    text_response,
    tool_call_response,
)

from eval_harness.cli import main
from eval_harness.ingest import Chunk, write_chunks

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

CITE_CASES = """
- id: cite-en-001
  category: cite
  language: en
  input: "What is the longest probation period the Statute allows?"
  expected:
    status: answered
    citations: [{instrument: statute, article: "9"}]
  scoring: [status, citations]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Art 9 caps probation at six months.
"""

MANIFEST = """
[instruments.statute]
title = "The Statute"

[[sources]]
id = "statute-en"
instrument = "statute"
language = "en"
official_url = "https://official.example/en"
wayback_url = "https://web.archive.org/web/20260101000000id_/https://official.example/en"
retrieved = 2026-10-17
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
indexed = true
heading_pattern = 'Article \\((\\d+)\\)'
"""


def index_chunk(article, text):
    return Chunk(
        id=f"statute:en:{article}:1",
        instrument="statute",
        article=article,
        part=1,
        language="en",
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source="statute-en",
    )


INDEX = [
    index_chunk("9", "Article (9) Probation. Probation shall not exceed six months."),
    index_chunk("29", "Article (29) Annual leave of thirty days."),
]


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    (pack / "evals" / "cases" / "refuse.yaml").write_text(REFUSE_CASES)
    (pack / "evals" / "cases" / "cite.yaml").write_text(CITE_CASES)
    (pack / "corpus").mkdir()
    (pack / "corpus" / "manifest.toml").write_text(MANIFEST)
    write_chunks(INDEX, tmp_path / "data" / "index")
    (tmp_path / "config.toml").write_text(
        f"""
pack = "pack"
runs_dir = "runs"
sources_dir = "data/sources"
index_dir = "data/index"

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


def test_requests_carry_caps_routing_and_a_cacheable_prefix(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    eval_run(project, fake, "--limit", "1")

    [request] = fake.chat_requests
    assert request["model"] == HAIKU
    assert request["max_tokens"] == 1024
    assert request["reasoning"] == {"effort": "low"}
    assert request["provider"] == {"require_parameters": True}
    assert "temperature" not in request
    assert [t["function"]["name"] for t in request["tools"]] == [
        "search_sources",
        "get_section",
        "final_answer",
    ]
    system = request["messages"][0]
    assert system["role"] == "system"
    assert system["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_temperature_is_zero_where_the_model_supports_it(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    run(project, fake, "run", "--model", "qwen/qwen3.8-flash", "--limit", "1")

    [request] = fake.chat_requests
    assert request["temperature"] == 0


def test_no_cache_breakpoints_for_providers_that_cache_automatically(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    run(project, fake, "run", "--model", "openai/gpt-5.6-terra", "--limit", "1")

    [request] = fake.chat_requests
    assert "cache_control" not in request["messages"][0]["content"][0]


def test_a_case_that_never_calls_final_answer_stops_at_six_turns_with_status_limit(project, capsys):
    fake = FakeOpenRouter([text_response("Let me think.") for _ in range(6)])

    exit_code = eval_run(project, fake, "--limit", "1")

    assert exit_code == 0
    assert len(fake.chat_requests) == 6
    assert "FAIL refuse-en-001" in capsys.readouterr().out
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["cases"][0]["status"] == "limit"
    assert len(read_jsonl(project / "runs" / "ledger.jsonl")) == 6


def test_a_response_cut_off_by_the_token_cap_gets_status_limit(project):
    fake = FakeOpenRouter([text_response("The answer is", finish_reason="length")])

    eval_run(project, fake, "--limit", "1")

    assert len(fake.chat_requests) == 1
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["cases"][0]["status"] == "limit"


def test_tool_errors_go_back_to_the_model_and_the_loop_continues(project):
    fake = FakeOpenRouter(
        [
            tool_call_response("read_contract", {"path": "contract.pdf"}, call_id="c1"),
            tool_call_response("final_answer", {"answer": "x", "status": "maybe"}, call_id="c2"),
            final_answer_response("refused", "legal_advice"),
        ]
    )

    eval_run(project, fake, "--limit", "1")

    assert len(fake.chat_requests) == 3
    tool_messages = [m for m in fake.chat_requests[2]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["c1", "c2"]
    assert "unknown tool" in tool_messages[0]["content"]
    assert "status must be one of" in tool_messages[1]["content"]
    steps = read_jsonl(only_run_dir(project) / "traces" / "refuse-en-001.1.jsonl")
    assert [s["name"] for s in steps if s["type"] == "tool_call"] == [
        "read_contract",
        "final_answer",
    ]
    assert steps[-1]["passed"] is True


def test_refuses_to_start_when_the_estimate_exceeds_the_remaining_budget(project, capsys):
    fake = FakeOpenRouter([], key_usage=19.999)

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert fake.chat_requests == []
    assert "over budget" in capsys.readouterr().err
    assert not (project / "runs" / "ledger.jsonl").exists()


def test_refuses_to_start_when_key_usage_is_unreachable(project, capsys):
    fake = FakeOpenRouter([], key_status=503)

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert fake.chat_requests == []
    assert "key usage" in capsys.readouterr().err


def test_estimate_uses_ledger_history_for_the_model_and_category(project, capsys):
    history = {
        "time": "2026-10-17T00:00:00+00:00",
        "run_id": "earlier",
        "purpose": "agent",
        "model": HAIKU,
        "case_id": "refuse-en-001",
        "category": "refuse",
        "repeat": 1,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "cost": 8.0,
    }
    (project / "runs").mkdir()
    (project / "runs" / "ledger.jsonl").write_text(json.dumps(history) + "\n")
    fake = FakeOpenRouter([], key_usage=0.0)

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert fake.chat_requests == []
    assert "over budget" in capsys.readouterr().err


def test_run_aborts_when_its_spend_crosses_the_remaining_budget(project, capsys):
    fake = FakeOpenRouter(
        [
            final_answer_response("refused", "legal_advice", cost=0.006),
            final_answer_response("refused", "out_of_scope", cost=0.006),
        ],
        key_usage=19.995,
    )

    exit_code = eval_run(project, fake)

    assert exit_code == 3
    assert len(fake.chat_requests) == 1
    assert "aborted" in capsys.readouterr().err
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["status"] == "aborted"
    assert [c["status"] for c in summary["cases"]] == ["aborted"]
    assert len(read_jsonl(project / "runs" / "ledger.jsonl")) == 1


def test_budget_command_prints_ledger_total_key_usage_and_remaining(project, capsys):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice", cost=0.25)])
    eval_run(project, fake, "--limit", "1")
    capsys.readouterr()
    fake.key_usage = 1.5

    exit_code = run(project, fake, "budget")

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "ledger total USD 0.250000" in out
    assert "key usage USD 1.500000" in out
    assert "remaining USD 18.500000" in out


def cite_answer(*articles, call_id="c2"):
    return tool_call_response(
        "final_answer",
        {
            "answer": "Probation may not exceed six months (Art 9).",
            "citations": [{"instrument": "statute", "article": a} for a in articles],
            "status": "answered",
            "refusal_reason": None,
        },
        call_id=call_id,
    )


def cite_run(project, fake):
    return run(project, fake, "run", "--model", HAIKU, "--category", "cite")


def test_cite_case_searches_the_corpus_and_passes_with_a_retrieved_citation(project, capsys):
    fake = FakeOpenRouter(
        [tool_call_response("search_sources", {"query": "probation period"}), cite_answer("9")]
    )

    assert cite_run(project, fake) == 0

    assert "PASS cite-en-001" in capsys.readouterr().out
    tool_message = fake.chat_requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert "six months" in tool_message["content"]
    steps = read_jsonl(only_run_dir(project) / "traces" / "cite-en-001.1.jsonl")
    [retrieval] = [s for s in steps if s["type"] == "retrieval"]
    assert retrieval["tool"] == "search_sources"
    assert [c["id"] for c in retrieval["chunks"]] == ["statute:en:9:1"]
    verdict = steps[-1]
    assert verdict["passed"] is True
    assert verdict["details"]["citations"]["cited"] == ["statute 9"]


def test_cite_case_fails_a_made_up_citation(project, capsys):
    fake = FakeOpenRouter(
        [tool_call_response("search_sources", {"query": "probation"}), cite_answer("9", "120")]
    )

    cite_run(project, fake)

    assert "FAIL cite-en-001" in capsys.readouterr().out
    steps = read_jsonl(only_run_dir(project) / "traces" / "cite-en-001.1.jsonl")
    assert steps[-1]["details"]["citations"]["not_retrieved"] == ["statute 120"]


def test_get_section_reads_an_article_and_records_the_retrieval(project):
    fake = FakeOpenRouter(
        [
            tool_call_response(
                "get_section", {"instrument": "statute", "article": "9", "language": "en"}
            ),
            cite_answer("9"),
        ]
    )

    cite_run(project, fake)

    steps = read_jsonl(only_run_dir(project) / "traces" / "cite-en-001.1.jsonl")
    [retrieval] = [s for s in steps if s["type"] == "retrieval"]
    assert retrieval["tool"] == "get_section"
    assert steps[-1]["passed"] is True


def test_refuses_to_start_without_an_index(project, capsys):
    (project / "data" / "index" / "chunks.jsonl").unlink()
    fake = FakeOpenRouter([])

    assert cite_run(project, fake) == 2

    assert fake.chat_requests == []
    assert "ingest" in capsys.readouterr().err


def test_summary_records_the_corpus_manifest_hash(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    eval_run(project, fake, "--limit", "1")

    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    manifest_bytes = (project / "pack" / "corpus" / "manifest.toml").read_bytes()
    assert summary["corpus_manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
