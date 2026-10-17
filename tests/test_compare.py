import pytest
from test_report import CONFIG, fixture_case, write_run

from eval_harness.cli import main

QWEN = "qwen/qwen3.8-flash"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config.toml").write_text(CONFIG)
    return tmp_path


def compare(project, *runs):
    return main(["--config", str(project / "config.toml"), "compare", *runs])


def row(out, label):
    [line] = [line for line in out.splitlines() if line.startswith(f"| {label} |")]
    return [cell.strip() for cell in line.strip("|").split("|")]


def test_compare_shows_each_categorys_pass_rate_side_by_side_with_the_difference(project, capsys):
    write_run(
        project / "runs" / "run-a",
        [
            fixture_case("calc-1", "calc", True),
            fixture_case("calc-2", "calc", True),
            fixture_case("cite-1", "cite", False),
            fixture_case("refuse-1", "refuse", True),
        ],
    )
    write_run(
        project / "runs" / "run-b",
        [
            fixture_case("calc-1", "calc", True),
            fixture_case("calc-2", "calc", False),
            fixture_case("cite-1", "cite", True),
            fixture_case("refuse-1", "refuse", True),
        ],
        model=QWEN,
    )

    assert compare(project, "run-a", "run-b") == 0

    out = capsys.readouterr().out
    assert "run-a" in out and "run-b" in out and QWEN in out
    assert row(out, "calc") == ["calc", "100% (2/2)", "50% (1/2)", "-50 pts"]
    assert row(out, "cite") == ["cite", "0% (0/1)", "100% (1/1)", "+100 pts"]
    assert row(out, "safety") == ["safety", "100% (1/1)", "100% (1/1)", "+0 pts"]


def test_compare_keeps_unreviewed_categories_in_their_own_labelled_rows(project, capsys):
    write_run(
        project / "runs" / "run-a",
        [
            fixture_case("cite-1", "cite", True, reviewed=False),
            fixture_case("inject-1", "inject", False, reviewed=False),
        ],
    )
    write_run(
        project / "runs" / "run-b",
        [
            fixture_case("cite-1", "cite", False, reviewed=False),
            fixture_case("inject-1", "inject", True, reviewed=False),
        ],
    )

    compare(project, "run-a", "run-b")

    out = capsys.readouterr().out
    assert row(out, "cite (unreviewed)") == [
        "cite (unreviewed)",
        "100% (1/1)",
        "0% (0/1)",
        "-100 pts",
    ]
    assert row(out, "safety (unreviewed)") == [
        "safety (unreviewed)",
        "0% (0/1)",
        "100% (1/1)",
        "+100 pts",
    ]
    assert "| cite |" not in out


def test_compare_shows_a_category_only_one_run_has(project, capsys):
    write_run(project / "runs" / "run-a", [fixture_case("calc-1", "calc", True)])
    write_run(
        project / "runs" / "run-b",
        [fixture_case("calc-1", "calc", True), fixture_case("cite-1", "cite", True)],
    )

    compare(project, "run-a", "run-b")

    out = capsys.readouterr().out
    assert row(out, "cite") == ["cite", "–", "100% (1/1)", "–"]
    assert "the runs cover different cases" in out


def test_compare_shows_latency_and_cost_percentiles_and_run_spend(project, capsys):
    write_run(
        project / "runs" / "run-a",
        [fixture_case("c-1", "calc", True, cost=0.001, latency=2.0)],
        run_spend_usd=0.004,
    )
    write_run(
        project / "runs" / "run-b",
        [fixture_case("c-1", "calc", True, cost=0.003, latency=1.5)],
        run_spend_usd=0.009,
    )

    compare(project, "run-a", "run-b")

    out = capsys.readouterr().out
    assert row(out, "latency p50") == ["latency p50", "2.00 s", "1.50 s", "-0.50 s"]
    assert row(out, "cost p95") == [
        "cost p95",
        "USD 0.001000",
        "USD 0.003000",
        "+USD 0.002000",
    ]
    assert row(out, "run spend") == ["run spend", "USD 0.004000", "USD 0.009000", "+USD 0.005000"]


def test_compare_refuses_a_missing_run(project, capsys):
    write_run(project / "runs" / "run-a", [fixture_case("c-1", "calc", True)])

    assert compare(project, "run-a", "nope") == 2

    assert "nope" in capsys.readouterr().err
