import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from corpus_fixture import INDEX, index_chunk, write_corpus
from fake_openrouter import (
    FAKE_KEY,
    FakeOpenRouter,
    final_answer_response,
    text_response,
    tool_call_response,
)

from eval_harness.cases import case_set_hash
from eval_harness.cli import main
from eval_harness.ingest import write_chunks

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


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    (pack / "evals" / "cases" / "refuse.yaml").write_text(REFUSE_CASES)
    (pack / "evals" / "cases" / "cite.yaml").write_text(CITE_CASES)
    write_corpus(tmp_path)
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


ARABIC_CITE_CASE = """
- id: cite-ar-001
  category: cite
  language: ar
  input: "ما أقصى مدة لفترة التجربة في القانون؟"
  expected:
    status: answered
    citations: [{instrument: statute, article: "9"}]
  scoring: [status, citations, answer_language]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Art 9 caps probation at six months.
"""
ARABIC_ARTICLE_9 = index_chunk(
    "9", "المادة (9) فترة التجربة. لا تزيد فترة التجربة على ستة أشهر.", language="ar"
)


def test_arabic_cite_case_finds_the_arabic_article_by_a_spelling_variant_and_answers_in_arabic(
    project, capsys
):
    write_corpus(project, [*INDEX, ARABIC_ARTICLE_9])
    (project / "pack" / "evals" / "cases" / "cite.yaml").write_text(ARABIC_CITE_CASE)
    fake = FakeOpenRouter(
        [
            tool_call_response("search_sources", {"query": "أقصى مدة فتره التجربه"}),
            tool_call_response(
                "final_answer",
                {
                    "answer": "لا تزيد فترة التجربة على ستة أشهر (المادة 9).",
                    "citations": [{"instrument": "statute", "article": "9"}],
                    "status": "answered",
                    "refusal_reason": None,
                },
                call_id="c2",
            ),
        ]
    )

    assert cite_run(project, fake) == 0

    assert "PASS cite-ar-001" in capsys.readouterr().out
    steps = read_jsonl(only_run_dir(project) / "traces" / "cite-ar-001.1.jsonl")
    [retrieval] = [s for s in steps if s["type"] == "retrieval"]
    assert [c["id"] for c in retrieval["chunks"]] == ["statute:ar:9:1"]
    assert steps[-1]["details"]["answer_language"]["detected"] == "ar"


def test_refuses_to_start_without_an_index(project, capsys):
    (project / "data" / "index" / "chunks.jsonl").unlink()
    fake = FakeOpenRouter([])

    assert cite_run(project, fake) == 2

    assert fake.chat_requests == []
    assert "ingest" in capsys.readouterr().err


def ledger(project):
    return read_jsonl(project / "runs" / "ledger.jsonl")


def embed(project, fake):
    return run(project, fake, "embed")


def write_index(project, *texts):
    write_chunks(
        [index_chunk(str(n), text) for n, text in enumerate(texts, 1)], project / "data" / "index"
    )


def test_embed_embeds_every_chunk_and_logs_each_call_to_the_ledger(project, capsys):
    write_index(project, "Probation shall not exceed six months.", "Leave of thirty days.")
    fake = FakeOpenRouter(embedding_cost=0.00002)

    assert embed(project, fake) == 0

    [request] = fake.embedding_requests
    assert request == {
        "model": "baai/bge-m3",
        "input": ["Probation shall not exceed six months.", "Leave of thirty days."],
    }
    [entry] = ledger(project)
    assert (entry["purpose"], entry["model"], entry["cost"]) == ("embedding", "baai/bge-m3", 2e-05)
    assert "embedded 2 chunk(s)" in capsys.readouterr().out


def test_embed_reuses_cached_vectors_by_chunk_text_hash(project):
    write_index(project, "Probation shall not exceed six months.", "Leave of thirty days.")
    embed(project, FakeOpenRouter())
    write_index(project, "Probation shall not exceed six months.", "Leave of 30 days.")
    fake = FakeOpenRouter()

    assert embed(project, fake) == 0

    assert [r["input"] for r in fake.embedding_requests] == [["Leave of 30 days."]]
    assert embed(project, fake) == 0
    assert len(fake.embedding_requests) == 1


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (FakeOpenRouter(key_usage=20.0), "over budget"),
        (FakeOpenRouter(key_status=503), "key usage is unreachable"),
    ],
)
def test_embed_refuses_to_run_when_the_budget_guard_says_no(project, capsys, fake, message):
    write_index(project, "Probation shall not exceed six months.")

    assert embed(project, fake) == 2

    assert fake.embedding_requests == []
    assert message in capsys.readouterr().err


def test_embed_refuses_an_embedding_model_openrouter_does_not_list(project, capsys):
    config = project / "config.toml"
    config.write_text(config.read_text().replace("baai/bge-m3", "acme/embedder"))
    fake = FakeOpenRouter()

    assert embed(project, fake) == 2

    assert fake.embedding_requests == []
    assert "acme/embedder" in capsys.readouterr().err


def test_search_embeds_each_query_through_the_ledger(project):
    fake = FakeOpenRouter(
        [tool_call_response("search_sources", {"query": "probation period"}), cite_answer("9")],
        embedding_cost=0.00003,
    )

    assert cite_run(project, fake) == 0

    assert [r["input"] for r in fake.embedding_requests] == [["probation period"]]
    [entry] = [e for e in ledger(project) if e["purpose"] == "embedding"]
    assert (entry["case_id"], entry["model"], entry["cost"]) == (
        "cite-en-001",
        "baai/bge-m3",
        3e-05,
    )
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["run_spend_usd"] == pytest.approx(0.0002 + 0.00003)


def test_refuses_to_start_when_chunks_have_no_embeddings(project, capsys):
    write_index(project, "A chunk ingested after the last embed.")
    fake = FakeOpenRouter([])

    assert cite_run(project, fake) == 2

    assert fake.chat_requests == []
    assert "embed" in capsys.readouterr().err


CALC_CASE = """
- id: calc-en-001
  category: calc
  language: en
  input: "First day 2023-01-01, last day 2023-12-31, basic wage AED 36,500. My gratuity?"
  expected:
    status: answered
    numbers: [25200]
    tolerance: 1
    tool_call:
      name: calculate_gratuity
      arguments: {start_date: "2023-01-01", end_date: "2023-12-31", monthly_basic_wage: 36500}
  scoring: [status, numeric, tool_call]
  reviewed: false
  refs: ["Labour Law Art 51(2)"]
  depends_on: [OQ-001]
  rationale: 21 days × 36,500 × 12 / 365 = 21 × 1,200 = 25,200.
"""

GRATUITY_ARGS = {
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "monthly_basic_wage": 36500,
    "work_pattern": "full_time",
    "nationality": "foreign",
}


def answer_response(text):
    return tool_call_response(
        "final_answer",
        {
            "answer": text,
            "citations": [{"instrument": "Labour Law", "article": "51"}],
            "status": "answered",
            "refusal_reason": None,
        },
        call_id="c2",
    )


def test_pack_tools_are_offered_called_and_scored(project):
    pack = project / "pack"
    (pack / "__init__.py").write_text(
        "from uae_labour.gratuity import GRATUITY_TOOL\n\nTOOLS = [GRATUITY_TOOL]\n"
    )
    (pack / "evals" / "cases" / "calc.yaml").write_text(CALC_CASE)
    fake = FakeOpenRouter(
        [
            tool_call_response("calculate_gratuity", GRATUITY_ARGS, call_id="c1"),
            answer_response("Your gratuity is AED 25,200. This is not legal advice."),
        ]
    )

    exit_code = run(project, fake, "run", "--model", HAIKU, "--category", "calc")

    assert exit_code == 0
    first, second = fake.chat_requests
    assert [t["function"]["name"] for t in first["tools"]] == [
        "search_sources",
        "get_section",
        "calculate_gratuity",
        "final_answer",
    ]
    [tool_message] = [m for m in second["messages"] if m["role"] == "tool"]
    assert json.loads(tool_message["content"])["result"]["gratuity"] == 25200.0
    steps = read_jsonl(only_run_dir(project) / "traces" / "calc-en-001.1.jsonl")
    [call] = [s for s in steps if s["type"] == "tool_call"]
    assert call["arguments"] == GRATUITY_ARGS
    assert call["result"]["refs"][0] == {"instrument": "Labour Law", "article": "51", "clause": "2"}
    verdict = steps[-1]
    assert verdict["passed"] is True
    assert set(verdict["details"]) == {"status", "numeric", "tool_call"}


def git(project, *args):
    return subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_the_summary_ties_the_run_to_its_cases_config_models_and_commit(project):
    git(project, "init", "-q")
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "fixture")
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    eval_run(project, fake, "--limit", "1")

    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["case_set_hash"] == case_set_hash(project / "pack" / "evals" / "cases")
    manifest = (project / "pack" / "manifest.toml").read_bytes()
    assert summary["manifest_hash"] == hashlib.sha256(manifest).hexdigest()
    assert summary["git_commit"] == git(project, "rev-parse", "HEAD")
    assert summary["models"] == {
        "agent": HAIKU,
        "judge": "openai/gpt-5.6-terra",
        "embedding": "baai/bge-m3",
    }
    assert summary["config"]["agent"] == {
        "max_turns": 6,
        "max_tokens": 1024,
        "reasoning_effort": "low",
    }
    assert summary["config"]["budget"]["ceiling_usd"] == 20.0


def test_the_summary_has_no_git_commit_outside_a_repository(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    eval_run(project, fake, "--limit", "1")

    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["git_commit"] is None


def test_headline_numbers_count_reviewed_cases_only(project, capsys):
    cases = REFUSE_CASES.replace("reviewed: false", "reviewed: true", 1)
    (project / "pack" / "evals" / "cases" / "refuse.yaml").write_text(cases)
    fake = FakeOpenRouter(
        [
            final_answer_response("refused", "legal_advice"),
            final_answer_response("answered", None),
        ]
    )

    eval_run(project, fake)

    out = capsys.readouterr().out
    assert "headline (reviewed cases only): 1/1 passed" in out
    assert "unreviewed: 0/1 passed, not in the headline" in out
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["reviewed"] == {
        "total": 1,
        "passed": 1,
        "by_category": {"refuse": {"total": 1, "passed": 1}},
    }
    assert summary["unreviewed"] == {
        "total": 1,
        "passed": 0,
        "by_category": {"refuse": {"total": 1, "passed": 0}},
    }


def set_open_questions(project, path):
    config = project / "config.toml"
    config.write_text(f'open_questions = "{path}"\n' + config.read_text())


def test_refuses_a_reviewed_case_that_depends_on_an_open_question(project, capsys):
    (project / "open-questions.md").write_text(
        "## OQ-005: Leave boundaries\n\n**Decision:** _open_\n"
    )
    set_open_questions(project, "open-questions.md")
    cases = REFUSE_CASES.replace(
        "reviewed: false\n  refs: []\n  depends_on: []",
        "reviewed: true\n  refs: []\n  depends_on: [OQ-005]",
        1,
    )
    (project / "pack" / "evals" / "cases" / "refuse.yaml").write_text(cases)
    fake = FakeOpenRouter([])

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert fake.chat_requests == []
    assert "reviewed but depends on open questions ['OQ-005']" in capsys.readouterr().err


def test_refuses_to_start_when_the_configured_questions_doc_is_missing(project, capsys):
    set_open_questions(project, "missing.md")
    fake = FakeOpenRouter([])

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert "cannot read open questions" in capsys.readouterr().err


def test_refuses_to_start_when_the_pack_offers_no_tool_list(project, capsys):
    (project / "pack" / "__init__.py").write_text("TOOLS = None\n")
    fake = FakeOpenRouter([])

    exit_code = eval_run(project, fake)

    assert exit_code == 2
    assert "TOOLS" in capsys.readouterr().err
