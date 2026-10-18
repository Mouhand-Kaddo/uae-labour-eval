import pytest

from eval_harness.budget import decide_start, estimate_run_cost, should_abort


def test_remaining_budget_uses_the_higher_of_ledger_and_key_usage():
    decision = decide_start(
        estimate_usd=1.0, ledger_total_usd=3.0, key_usage_usd=5.0, ceiling_usd=20.0
    )
    assert decision.allowed
    assert decision.remaining_usd == 15.0

    decision = decide_start(
        estimate_usd=1.0, ledger_total_usd=7.0, key_usage_usd=5.0, ceiling_usd=20.0
    )
    assert decision.remaining_usd == 13.0


def test_refuses_a_run_whose_estimate_exceeds_the_remaining_budget():
    decision = decide_start(
        estimate_usd=2.5, ledger_total_usd=18.0, key_usage_usd=0.0, ceiling_usd=20.0
    )
    assert not decision.allowed
    assert decision.remaining_usd == 2.0
    assert "2.5" in decision.reason and "2.0" in decision.reason


def test_refuses_to_start_when_key_usage_is_unreachable():
    decision = decide_start(
        estimate_usd=0.01, ledger_total_usd=0.0, key_usage_usd=None, ceiling_usd=20.0
    )
    assert not decision.allowed
    assert decision.remaining_usd is None
    assert "key usage" in decision.reason


def test_estimate_uses_per_case_history_times_cases_times_margin():
    estimate = estimate_run_cost(
        case_count=10,
        history_per_case_usd=0.004,
        prompt_price_usd=0.0000001,
        completion_price_usd=0.0000005,
        assumed_prompt_tokens=6000,
        assumed_completion_tokens=1500,
        margin=1.5,
    )
    assert estimate == pytest.approx(0.06)


def test_estimate_without_history_uses_live_prices_times_assumed_tokens():
    estimate = estimate_run_cost(
        case_count=4,
        history_per_case_usd=None,
        prompt_price_usd=0.0000001,
        completion_price_usd=0.0000005,
        assumed_prompt_tokens=6000,
        assumed_completion_tokens=1500,
        margin=1.5,
    )
    assert estimate == pytest.approx(0.0081)


def test_run_aborts_only_once_its_spend_crosses_the_remaining_budget():
    assert not should_abort(run_spend_usd=0.5, remaining_usd=0.5)
    assert should_abort(run_spend_usd=0.5001, remaining_usd=0.5)
