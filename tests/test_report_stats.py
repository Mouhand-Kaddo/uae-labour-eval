import pytest

from eval_harness.report_stats import percentile, report_numbers, wilson_interval


@pytest.mark.parametrize(
    ("passed", "n", "low", "high"),
    [(8, 10, 0.4902, 0.9433), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (1, 1, 0.2065, 1.0)],
)
def test_wilson_interval_matches_published_values(passed, n, low, high):
    assert wilson_interval(passed, n) == pytest.approx((low, high), abs=5e-5)


def test_wilson_interval_is_none_without_data():
    assert wilson_interval(0, 0) is None


def result(case_id, category, passed, *, reviewed=True, repeat=1, cost=0.001, latency=1.0):
    return {
        "case_id": case_id,
        "repeat": repeat,
        "category": category,
        "reviewed": reviewed,
        "status": "answered",
        "passed": passed,
        "cost_usd": cost,
        "latency_s": latency,
    }


def test_percentiles_use_the_nearest_rank():
    assert percentile([float(v) for v in range(20, 0, -1)], 50) == 10.0
    assert percentile([float(v) for v in range(1, 21)], 95) == 19.0
    assert percentile([3.0], 95) == 3.0
    assert percentile([], 50) is None


def test_headline_scores_cover_reviewed_cases_per_category_with_their_average():
    results = [result(f"calc-{i}", "calc", i < 8) for i in range(10)]
    results += [result("cite-1", "cite", True), result("cite-2", "cite", False)]
    results += [result("calc-x", "calc", False, reviewed=False)]

    numbers = report_numbers(results)

    calc, cite = numbers.headline
    assert (calc.label, calc.passed, calc.n, calc.rate) == ("calc", 8, 10, 0.8)
    assert calc.interval == pytest.approx((0.4902, 0.9433), abs=5e-5)
    assert (cite.label, cite.passed, cite.n, cite.rate) == ("cite", 1, 2, 0.5)
    assert numbers.headline_average == pytest.approx(0.65)


def test_repeats_score_each_case_by_its_pass_fraction_and_n_counts_distinct_cases():
    results = [
        result("calc-1", "calc", True, repeat=1),
        result("calc-1", "calc", True, repeat=2),
        result("calc-2", "calc", True, repeat=1),
        result("calc-2", "calc", False, repeat=2),
        result("calc-3", "calc", False, repeat=1),
        result("calc-3", "calc", False, repeat=2),
        result("cite-1", "cite", True, repeat=1),
        result("cite-1", "cite", True, repeat=2),
    ]

    numbers = report_numbers(results)

    calc, cite = numbers.headline
    assert (calc.n, calc.rate) == (3, 0.5)
    assert calc.interval == pytest.approx((0.1253, 0.8747), abs=5e-5)
    assert (cite.n, cite.rate) == (1, 1.0)
    assert numbers.headline_average == pytest.approx(0.75)


def test_safety_scores_each_case_by_its_pass_fraction_across_repeats():
    results = [
        result("refuse-1", "refuse", True, repeat=1),
        result("refuse-1", "refuse", False, repeat=2),
        result("inject-1", "inject", True, repeat=1),
        result("inject-1", "inject", True, repeat=2),
    ]

    safety = report_numbers(results).safety

    assert (safety.n, safety.rate) == (2, 0.75)


def test_safety_pools_reviewed_refuse_and_inject_cases():
    results = [
        result("refuse-1", "refuse", True),
        result("refuse-2", "refuse", False),
        result("inject-1", "inject", True),
        result("inject-2", "inject", True, reviewed=False),
        result("calc-1", "calc", False),
    ]

    safety = report_numbers(results).safety

    assert (safety.passed, safety.n) == (2, 3)


def test_unreviewed_cases_are_scored_apart_from_the_headline():
    results = [result("calc-1", "calc", True), result("calc-2", "calc", False, reviewed=False)]

    numbers = report_numbers(results)

    assert [(s.label, s.passed, s.n) for s in numbers.headline] == [("calc", 1, 1)]
    assert [(s.label, s.passed, s.n) for s in numbers.unreviewed] == [("calc", 0, 1)]


def test_latency_and_cost_percentiles_cover_every_result():
    results = [
        result(f"c-{i}", "calc", True, cost=i / 1000, latency=float(i), reviewed=i % 2 == 0)
        for i in range(1, 21)
    ]

    numbers = report_numbers(results)

    assert (numbers.latency_p50, numbers.latency_p95) == (10.0, 19.0)
    assert (numbers.cost_p50, numbers.cost_p95) == (0.010, 0.019)


def test_worst_failures_put_safety_first_then_calc_then_the_rest_reviewed_before_unreviewed():
    results = [
        result("cite-1", "cite", False),
        result("calc-2", "calc", False, reviewed=False),
        result("calc-1", "calc", False),
        result("calc-ok", "calc", True),
        result("inject-1", "inject", False, reviewed=False),
        result("refuse-1", "refuse", False),
        result("grounding-1", "grounding", False),
    ]

    failures = report_numbers(results).failures

    assert [r["case_id"] for r in failures] == [
        "refuse-1",
        "inject-1",
        "calc-1",
        "calc-2",
        "cite-1",
        "grounding-1",
    ]


def test_flaky_cases_are_those_that_both_pass_and_fail_across_repeats():
    results = [
        result("calc-1", "calc", True, repeat=1),
        result("calc-1", "calc", False, repeat=2),
        result("calc-1", "calc", True, repeat=3),
        result("calc-2", "calc", False, repeat=1),
        result("calc-2", "calc", False, repeat=2),
        result("cite-1", "cite", True, repeat=1),
    ]

    flaky = report_numbers(results).flaky

    assert [(f.case_id, f.passed, f.runs) for f in flaky] == [("calc-1", 2, 3)]
