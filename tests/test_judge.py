import json

import pytest
from corpus_fixture import write_corpus
from fake_openrouter import FAKE_KEY, FakeOpenRouter, text_response, tool_call_response
from test_run import HAIKU, only_run_dir, read_jsonl, run

JUDGE = "openai/gpt-5.6-terra"

GROUNDING_RUBRIC = """# Grounding

Decide whether the answer is grounded in the text of the articles it cites.

## claims_supported
Every claim in the answer is supported by the cited chunk text.

## cites_relevant
Each citation points to an article that is relevant to the question.
"""

REFUSAL_RUBRIC = """# Refusal quality

## explains_why
The refusal says why the question cannot be answered.
"""

CASES = """
- id: grounding-en-001
  category: grounding
  language: en
  input: "How long can probation last under the Statute?"
  expected:
    status: answered
    citations: [{instrument: statute, article: "9"}]
  scoring: [status, citations, "judge:grounding"]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Art 9 caps probation at six months.
- id: refuse-en-001
  category: refuse
  language: en
  input: "My employer fired me last week. Should I sue them?"
  expected: {status: refused, refusal_reason: legal_advice}
  scoring: [status, "judge:refusal"]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Asks what this person should do in their own dispute.
"""


def write_config(root, agent=HAIKU, judge=JUDGE):
    (root / "config.toml").write_text(
        f"""
pack = "pack"
runs_dir = "runs"

[models]
agent = "{agent}"
judge = "{judge}"
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


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "evals" / "rubrics").mkdir()
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    (pack / "evals" / "cases" / "cases.yaml").write_text(CASES)
    (pack / "evals" / "rubrics" / "grounding.md").write_text(GROUNDING_RUBRIC)
    (pack / "evals" / "rubrics" / "refusal.md").write_text(REFUSAL_RUBRIC)
    write_corpus(tmp_path)
    write_config(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return tmp_path


def grounded_answer(*articles):
    return tool_call_response(
        "final_answer",
        {
            "answer": "Probation may last up to six months.",
            "citations": [{"instrument": "statute", "article": a} for a in articles],
            "status": "answered",
            "refusal_reason": None,
        },
        call_id="c2",
    )


def judge_says(cost=0.0002, **criteria):
    return text_response(
        json.dumps(
            {
                name: {"passed": passed, "reason": f"{name} reason"}
                for name, passed in criteria.items()
            }
        ),
        cost=cost,
    )


def grounding_run(project, fake):
    return run(project, fake, "run", "--model", HAIKU, "--category", "grounding")


def search(query):
    return tool_call_response("search_sources", {"query": query})


def trace_steps(project, case_id):
    return read_jsonl(only_run_dir(project) / "traces" / f"{case_id}.1.jsonl")


def test_grounding_case_passes_when_the_judge_passes_every_criterion(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            grounded_answer("9"),
            judge_says(claims_supported=True, cites_relevant=True),
        ]
    )

    assert grounding_run(project, fake) == 0

    assert "PASS grounding-en-001" in capsys.readouterr().out
    judge_request = fake.chat_requests[-1]
    assert judge_request["model"] == JUDGE
    response_format = judge_request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert set(schema["required"]) == {"claims_supported", "cites_relevant"}
    assert schema["additionalProperties"] is False
    assert judge_request["provider"] == {"require_parameters": True}
    prompt = json.dumps(judge_request["messages"])
    assert "Probation shall not exceed six months." in prompt
    assert "Every claim in the answer is supported" in prompt
    assert "Probation may last up to six months." in prompt
    verdict = trace_steps(project, "grounding-en-001")[-1]
    assert verdict["passed"] is True
    assert verdict["details"]["judge:grounding"]["criteria"] == {
        "claims_supported": {"passed": True, "reason": "claims_supported reason"},
        "cites_relevant": {"passed": True, "reason": "cites_relevant reason"},
    }


def test_a_failed_criterion_fails_the_case_even_when_deterministic_scorers_pass(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            grounded_answer("9"),
            judge_says(claims_supported=False, cites_relevant=True),
        ]
    )

    grounding_run(project, fake)

    assert "FAIL grounding-en-001" in capsys.readouterr().out
    verdict = trace_steps(project, "grounding-en-001")[-1]
    assert verdict["passed"] is False
    assert verdict["details"]["status"]["passed"] is True
    assert verdict["details"]["citations"]["passed"] is True
    judged = verdict["details"]["judge:grounding"]
    assert judged["passed"] is False
    assert judged["criteria"]["claims_supported"] == {
        "passed": False,
        "reason": "claims_supported reason",
    }


@pytest.mark.parametrize(
    "judge_response",
    [
        text_response("The answer looks grounded to me."),
        text_response(json.dumps({"claims_supported": {"passed": True, "reason": "ok"}})),
        text_response(
            json.dumps(
                {
                    "claims_supported": {"passed": "yes", "reason": "ok"},
                    "cites_relevant": {"passed": True, "reason": "ok"},
                }
            )
        ),
        text_response('{"claims_supported": {"passed": true', finish_reason="length"),
        {"error": {"code": 502, "message": "provider down"}},
    ],
    ids=["not-json", "missing-criterion", "non-boolean", "cut-off", "call-failed"],
)
def test_an_unusable_judge_response_is_a_scorer_error_not_a_pass(project, capsys, judge_response):
    fake = FakeOpenRouter([search("probation"), grounded_answer("9"), judge_response])

    assert grounding_run(project, fake) == 0

    assert "FAIL grounding-en-001" in capsys.readouterr().out
    judged = trace_steps(project, "grounding-en-001")[-1]["details"]["judge:grounding"]
    assert judged["passed"] is False
    assert judged["error"]
    assert "criteria" not in judged


def test_judge_calls_are_recorded_in_the_ledger_and_the_run_spend(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            grounded_answer("9"),
            judge_says(cost=0.003, claims_supported=True, cites_relevant=True),
        ]
    )

    grounding_run(project, fake)

    records = read_jsonl(project / "runs" / "ledger.jsonl")
    assert [(r["purpose"], r["model"]) for r in records] == [
        ("agent", HAIKU),
        ("embedding", "baai/bge-m3"),
        ("agent", HAIKU),
        ("judge", JUDGE),
    ]
    assert records[-1]["case_id"] == "grounding-en-001"
    assert records[-1]["cost"] == 0.003
    total = sum(r["cost"] for r in records)
    assert total > 0.003
    assert f"run spend USD {total:.6f}" in capsys.readouterr().out


def test_judge_spend_that_crosses_the_remaining_budget_aborts_the_run(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            grounded_answer("9"),
            judge_says(cost=12.0, claims_supported=True, cites_relevant=True),
        ],
        key_usage=10.0,
    )

    assert grounding_run(project, fake) == 3

    assert "aborted" in capsys.readouterr().err
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["status"] == "aborted"
    assert [c["status"] for c in summary["cases"]] == ["aborted"]
    assert trace_steps(project, "grounding-en-001")[-1]["type"] == "aborted"


def test_the_judge_is_skipped_when_a_deterministic_scorer_already_failed(project, capsys):
    fake = FakeOpenRouter([search("probation"), grounded_answer("51")])

    assert grounding_run(project, fake) == 0

    assert "FAIL grounding-en-001" in capsys.readouterr().out
    assert len(fake.chat_requests) == 2
    details = trace_steps(project, "grounding-en-001")[-1]["details"]
    assert details["citations"]["passed"] is False
    assert details["judge:grounding"] == {
        "passed": False,
        "skipped": "a deterministic scorer already failed",
    }
    ledger = read_jsonl(project / "runs" / "ledger.jsonl")
    assert "judge" not in {r["purpose"] for r in ledger}


def test_the_budget_estimate_includes_the_judge_calls(project, capsys):
    fake = FakeOpenRouter([], key_usage=19.97)

    assert grounding_run(project, fake) == 2

    assert fake.chat_requests == []
    assert "over budget" in capsys.readouterr().err


def test_config_rejects_a_judge_from_the_agents_model_family(project, capsys):
    write_config(project, judge="anthropic/claude-opus-5.5")
    fake = FakeOpenRouter([])

    assert grounding_run(project, fake) == 2

    assert "same model family" in capsys.readouterr().err
    assert fake.chat_requests == []


def test_refuses_an_agent_model_from_the_judges_family(project, capsys):
    fake = FakeOpenRouter([])

    exit_code = run(project, fake, "run", "--model", JUDGE, "--category", "grounding")

    assert exit_code == 2
    assert "same model family" in capsys.readouterr().err


def test_refuses_a_judge_without_structured_outputs(project, capsys):
    write_config(project, judge="qwen/qwen3.8-flash")
    fake = FakeOpenRouter([])

    assert grounding_run(project, fake) == 2

    assert "structured outputs" in capsys.readouterr().err


def test_refuses_a_rubric_without_criteria(project, capsys):
    (project / "pack" / "evals" / "rubrics" / "refusal.md").write_text("# Refusal\nBe nice.\n")
    fake = FakeOpenRouter([])

    assert grounding_run(project, fake) == 2

    assert "refusal.md" in capsys.readouterr().err


def test_refuse_case_is_judged_on_the_refusal_rubric_with_no_chunks(project, capsys):
    fake = FakeOpenRouter(
        [
            tool_call_response(
                "final_answer",
                {
                    "answer": "I can't advise on your own dispute; that would be legal advice.",
                    "citations": [],
                    "status": "refused",
                    "refusal_reason": "legal_advice",
                },
            ),
            judge_says(explains_why=True),
        ]
    )

    assert run(project, fake, "run", "--model", HAIKU, "--category", "refuse") == 0

    assert "PASS refuse-en-001" in capsys.readouterr().out
    judge_request = fake.chat_requests[-1]
    schema = judge_request["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["explains_why"]
    assert "no retrieved text" in judge_request["messages"][1]["content"]
