import json

import pytest
from corpus_fixture import write_corpus
from fake_openrouter import FAKE_KEY, FakeOpenRouter, tool_call_response
from test_judge import JUDGE, judge_says, search, trace_steps, write_config
from test_run import HAIKU, only_run_dir, read_jsonl, run

BILINGUAL_RUBRIC = """# Bilingual consistency

## same_meaning
The English and the Arabic answers say the same thing.
"""

PAIR = """
- id: bilingual-probation-001
  category: bilingual
  language: both
  input:
    en: "How long can probation last under the Statute?"
    ar: "ما أقصى مدة لفترة التجربة في النظام؟"
  expected:
    en:
      status: answered
      numbers: [6]
      citations: [{instrument: statute, article: "9"}]
    ar:
      status: answered
      numbers: [6]
      citations: [{instrument: statute, article: "9"}]
  scoring: [status, numeric, citations, answer_language, consistency]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Art 9 caps probation at six months, in either language.
"""

EN_ANSWER = "Probation may last up to 6 months (Art 9)."
AR_ANSWER = "لا تزيد فترة التجربة على 6 أشهر (المادة 9)."


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "evals" / "rubrics").mkdir()
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    (pack / "evals" / "cases" / "bilingual.yaml").write_text(PAIR)
    (pack / "evals" / "rubrics" / "bilingual.md").write_text(BILINGUAL_RUBRIC)
    write_corpus(tmp_path)
    write_config(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return tmp_path


def answer(text, *articles):
    return tool_call_response(
        "final_answer",
        {
            "answer": text,
            "citations": [{"instrument": "statute", "article": a} for a in articles],
            "status": "answered",
            "refusal_reason": None,
        },
        call_id="c2",
    )


def pair_run(project, fake):
    return run(project, fake, "run", "--model", HAIKU, "--case", "bilingual-probation-001")


def test_a_pair_runs_both_halves_and_passes_as_one_case(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            search("التجربة"),
            answer(AR_ANSWER, "9"),
            judge_says(same_meaning=True),
        ]
    )

    assert pair_run(project, fake) == 0

    assert "PASS bilingual-probation-001" in capsys.readouterr().out
    agent_requests = [r for r in fake.chat_requests if r["model"] == HAIKU]
    assert agent_requests[0]["messages"][-1]["content"].startswith("How long can probation")
    assert agent_requests[2]["messages"][-1]["content"].startswith("ما أقصى مدة")

    steps = trace_steps(project, "bilingual-probation-001")
    halves = [s for s in steps if s["type"] == "half"]
    assert [(h["language"], h["input"][:3]) for h in halves] == [("en", "How"), ("ar", "ما ")]
    assert [s["status"] for s in steps if s["type"] == "final_answer"] == ["answered"] * 2
    verdict = steps[-1]
    assert verdict["type"] == "verdict" and verdict["passed"] is True
    assert verdict["details"]["citations"]["en"]["cited"] == ["statute 9"]
    assert verdict["details"]["answer_language"]["ar"]["detected"] == "ar"
    assert verdict["details"]["consistency"]["judge"]["criteria"]["same_meaning"]["passed"]

    judge_request = fake.chat_requests[-1]
    assert judge_request["model"] == JUDGE
    material = judge_request["messages"][1]["content"]
    assert EN_ANSWER in material and AR_ANSWER in material
    assert "ما أقصى مدة" in material and "Probation shall not exceed six months." in material

    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    [result] = summary["cases"]
    assert (result["case_id"], result["category"], result["status"]) == (
        "bilingual-probation-001",
        "bilingual",
        "answered",
    )
    records = read_jsonl(project / "runs" / "ledger.jsonl")
    assert "judge" in {r["purpose"] for r in records}
    assert result["cost_usd"] == pytest.approx(sum(r["cost"] for r in records))


def test_a_pair_whose_halves_cite_different_articles_passes_when_both_cite_the_required_one(
    project, capsys
):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            search("التجربة إجازة"),
            answer(AR_ANSWER, "9", "29"),
            judge_says(same_meaning=True),
        ]
    )

    assert pair_run(project, fake) == 0

    assert "PASS bilingual-probation-001" in capsys.readouterr().out
    details = trace_steps(project, "bilingual-probation-001")[-1]["details"]
    assert details["citations"]["passed"]
    assert "citations" not in details["consistency"]


def test_the_second_half_cannot_cite_an_article_only_the_first_half_read(project, capsys):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            answer(AR_ANSWER, "9"),
            search("التجربة"),
            answer(AR_ANSWER, "9"),
            judge_says(same_meaning=True),
        ]
    )

    assert pair_run(project, fake) == 0

    assert "PASS bilingual-probation-001" in capsys.readouterr().out
    steps = trace_steps(project, "bilingual-probation-001")
    [rejected] = [s for s in steps if s["type"] == "tool_call" and s["name"] == "final_answer"]
    assert rejected["unread"] == ["statute Art 9"]
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["cases"][0]["sent_back"] == 1


def test_the_pair_judge_is_skipped_when_a_deterministic_scorer_already_failed(project, capsys):
    fake = FakeOpenRouter(
        [search("probation"), answer(EN_ANSWER, "9"), search("probation"), answer(EN_ANSWER, "9")]
    )

    assert pair_run(project, fake) == 0

    assert "FAIL bilingual-probation-001" in capsys.readouterr().out
    assert all(r["model"] == HAIKU for r in fake.chat_requests)
    details = trace_steps(project, "bilingual-probation-001")[-1]["details"]
    assert details["answer_language"]["passed"] is False
    assert details["consistency"] == {
        "passed": False,
        "skipped": "a deterministic scorer already failed",
    }


def test_a_half_that_fails_to_finish_leaves_the_pair_unfinished(project, capsys):
    fake = FakeOpenRouter(
        [answer(EN_ANSWER, "9"), {"error": {"code": 502, "message": "provider down"}}]
    )

    assert pair_run(project, fake) == 0

    assert "FAIL bilingual-probation-001" in capsys.readouterr().out
    steps = trace_steps(project, "bilingual-probation-001")
    assert [s["type"] for s in steps][-2:] == ["error", "verdict"]
    assert len(fake.chat_requests) == 2
    summary = json.loads((only_run_dir(project) / "summary.json").read_text())
    assert summary["cases"][0]["status"] == "error"


def test_the_budget_estimate_counts_both_halves_and_the_pair_judge(project, capsys):
    fake = FakeOpenRouter([], key_usage=20.0 - 0.048)

    assert pair_run(project, fake) == 2

    assert "estimate USD 0.0491" in capsys.readouterr().err
    assert fake.chat_requests == []


def test_a_pair_is_refused_without_the_bilingual_rubric(project, capsys):
    (project / "pack" / "evals" / "rubrics" / "bilingual.md").unlink()
    fake = FakeOpenRouter([])

    assert pair_run(project, fake) == 2

    assert "bilingual.md" in capsys.readouterr().err
    assert fake.chat_requests == []


def test_the_bilingual_rubric_is_not_a_per_answer_scorer(project, capsys):
    cases = project / "pack" / "evals" / "cases" / "bilingual.yaml"
    cases.write_text(PAIR.replace("consistency]", 'consistency, "judge:bilingual"]'))

    assert pair_run(project, FakeOpenRouter([])) == 2

    assert "unknown scorers ['judge:bilingual']" in capsys.readouterr().err


def test_the_report_counts_a_pair_once_and_shows_both_halves(project):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            search("التجربة"),
            answer(AR_ANSWER, "9"),
            judge_says(same_meaning=True),
        ]
    )
    pair_run(project, fake)
    run_dir = only_run_dir(project)

    assert run(project, fake, "report", run_dir.name) == 0

    index = (run_dir / "report" / "index.html").read_text()
    unreviewed = index.split('id="unreviewed"')[1].split("</section>")[0]
    row = unreviewed.split(">bilingual<")[1].split("</tr>")[0]
    assert ">100%<" in row and '<td class="num">1</td>' in row
    page = (run_dir / "report" / "traces" / "bilingual-probation-001.1.html").read_text()
    assert page.count(". half</h2>") == 2
    assert "ما أقصى مدة" in page and "Probation may last up to 6 months" in page
