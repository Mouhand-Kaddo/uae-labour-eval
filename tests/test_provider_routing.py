import json
from pathlib import Path

import pytest
from fake_openrouter import (
    MODELS,
    FakeOpenRouter,
    final_answer_response,
    served_by,
    tool_call_response,
)
from test_run import HAIKU, only_run_dir, project, read_jsonl, run

from eval_harness.config import load_config

DEEPSEEK = "deepseek/deepseek-v4.1-flash-1017"
JUDGE = "openai/gpt-5.6-terra"

__all__ = ["project"]


def add_routing(project, model, routing):
    config = project / "config.toml"
    config.write_text(f'{config.read_text()}\n[provider_routing."{model}"]\n{routing}\n')


def trace_path(project):
    return only_run_dir(project) / "traces" / "refuse-en-001.1.jsonl"


def deepseek_run(project, fake, *extra):
    return run(project, fake, "run", "--model", DEEPSEEK, "--case", "refuse-en-001", *extra)


@pytest.mark.parametrize(
    ("routing", "message"),
    [
        ('order = "deepseek"', "order must be a non-empty list of provider slugs"),
        ("order = []", "order must be a non-empty list of provider slugs"),
        ('allow_fallbacks = "no"', "allow_fallbacks must be true or false"),
        ("require_parameters = false", "require_parameters must stay true"),
        ('sort = "cheapest"', "sort must be one of"),
        ("allowFallbacks = false", "unknown routing field 'allowFallbacks'"),
    ],
)
def test_a_malformed_routing_table_is_refused_before_any_call(project, capsys, routing, message):
    add_routing(project, DEEPSEEK, routing)
    fake = FakeOpenRouter([])

    assert deepseek_run(project, fake) == 2

    assert message in capsys.readouterr().err
    assert fake.chat_requests == []


def test_routing_keys_must_be_model_ids(project, capsys):
    add_routing(project, "deepseek", 'order = ["deepseek"]')

    assert deepseek_run(project, FakeOpenRouter([])) == 2

    assert "keys are OpenRouter model IDs" in capsys.readouterr().err


def test_a_model_without_routing_gets_only_require_parameters(project):
    add_routing(project, DEEPSEEK, 'order = ["deepseek"]\nallow_fallbacks = false')
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    assert run(project, fake, "run", "--model", HAIKU, "--case", "refuse-en-001") == 0

    assert fake.chat_requests[0]["provider"] == {"require_parameters": True}


def test_the_serving_provider_of_each_call_is_recorded_in_the_trace_and_ledger(project):
    fake = FakeOpenRouter(
        [
            served_by(tool_call_response("search_sources", {"query": "notice"}), "DeepSeek"),
            final_answer_response("refused", "legal_advice") | {"provider": "Fallback Inc"},
        ]
    )

    assert deepseek_run(project, fake) == 0

    assert all(h["x-openrouter-metadata"] == "enabled" for h in fake.chat_headers)
    responses = [s for s in read_jsonl(trace_path(project)) if s["type"] == "response"]
    assert [s["provider"] for s in responses] == ["DeepSeek", "Fallback Inc"]
    ledger = read_jsonl(project / "runs" / "ledger.jsonl")
    agent_calls = [r for r in ledger if r["purpose"] == "agent"]
    assert [r["provider"] for r in agent_calls] == ["DeepSeek", "Fallback Inc"]
    assert {r["provider"] for r in ledger if r["purpose"] == "embedding"} == {None}


def test_a_response_without_provider_metadata_records_none(project):
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    assert deepseek_run(project, fake) == 0

    [record] = read_jsonl(project / "runs" / "ledger.jsonl")
    assert record["provider"] is None


def test_the_agent_request_carries_the_routing_configured_for_its_model(project):
    add_routing(project, DEEPSEEK, 'order = ["deepseek"]\nallow_fallbacks = false')
    fake = FakeOpenRouter([final_answer_response("refused", "legal_advice")])

    assert deepseek_run(project, fake) == 0

    [request] = fake.chat_requests
    assert request["provider"] == {
        "require_parameters": True,
        "order": ["deepseek"],
        "allow_fallbacks": False,
    }


def test_the_estimate_prices_the_agent_at_its_highest_override(project, capsys):
    fake = FakeOpenRouter([], key_usage=19.996)

    assert deepseek_run(project, fake) == 2

    assert "over budget: estimate USD 0.0054" in capsys.readouterr().err
    assert fake.chat_requests == []


def test_the_estimate_scales_ledger_history_up_to_the_highest_override(project, capsys):
    history = {
        "run_id": "earlier",
        "purpose": "agent",
        "model": DEEPSEEK,
        "case_id": "refuse-en-002",
        "category": "refuse",
        "repeat": 1,
        "cost": 0.002,
    }
    (project / "runs").mkdir()
    (project / "runs" / "ledger.jsonl").write_text(json.dumps(history) + "\n")
    fake = FakeOpenRouter([], key_usage=19.995)

    exit_code = run(
        project, fake, "run", "--model", DEEPSEEK, "--category", "refuse", "--limit", "1"
    )

    assert exit_code == 2
    assert "over budget: estimate USD 0.0060" in capsys.readouterr().err


def test_the_estimate_prices_the_judge_at_its_highest_override(project, capsys):
    surge = {"min_prompt_tokens": 272000, "prompt": "0.000004", "completion": "0.000018"}
    models = [
        m | {"pricing": m["pricing"] | {"overrides": [surge]}} if m["id"] == JUDGE else m
        for m in MODELS
    ]
    cases = project / "pack" / "evals" / "cases" / "refuse.yaml"
    cases.write_text(cases.read_text().replace("[status]", '[status, "judge:refusal"]', 1))
    rubrics = project / "pack" / "evals" / "rubrics"
    rubrics.mkdir()
    (rubrics / "refusal.md").write_text("# Refusal\n\n## explains_why\nSays why.\n")
    fake = FakeOpenRouter([], key_usage=19.94, models=models)

    assert run(project, fake, "run", "--model", HAIKU, "--case", "refuse-en-001") == 2

    assert "over budget: estimate USD 0.0785" in capsys.readouterr().err


def test_the_repo_config_pins_the_owners_agent_model_to_deepseeks_own_endpoint():
    config = load_config(Path(__file__).parents[1] / "config.toml")

    assert config.agent_model == DEEPSEEK
    assert config.judge_model == JUDGE
    assert config.provider_for(DEEPSEEK) == {
        "require_parameters": True,
        "order": ["deepseek"],
        "allow_fallbacks": False,
    }


def with_reasoning(response, text):
    message = response["choices"][0]["message"]
    message |= {
        "content": "",
        "reasoning": text,
        "reasoning_details": [{"type": "reasoning.text", "text": text, "index": 0}],
    }
    return response


def test_deepseek_requests_cache_automatically_and_keep_reasoning_across_turns(project):
    fake = FakeOpenRouter(
        [
            with_reasoning(tool_call_response("search_sources", {"query": "notice"}), "Look up."),
            with_reasoning(final_answer_response("refused", "legal_advice"), "Refuse."),
        ]
    )

    assert deepseek_run(project, fake) == 0

    first, second = fake.chat_requests
    assert first["temperature"] == 0
    assert first["reasoning"] == {"effort": "low"}
    assert "cache_control" not in first["messages"][0]["content"][0]
    [assistant] = [m for m in second["messages"] if m["role"] == "assistant"]
    assert assistant["reasoning_details"] == [
        {"type": "reasoning.text", "text": "Look up.", "index": 0}
    ]
