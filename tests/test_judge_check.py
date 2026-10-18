import json

import pytest
import yaml
from corpus_fixture import write_corpus
from fake_openrouter import FAKE_KEY, FakeOpenRouter, final_answer_response
from test_bilingual import AR_ANSWER, BILINGUAL_RUBRIC, EN_ANSWER, PAIR, answer
from test_judge import GROUNDING_RUBRIC, REFUSAL_RUBRIC, grounded_answer, judge_says, search
from test_judge import write_config as write_judge_config
from test_run import run

from eval_harness.judge_check import item_material, measure

CITE_CASE = """
- id: cite-en-001
  category: cite
  language: en
  input: "Which article caps probation?"
  expected:
    status: answered
    citations: [{instrument: statute, article: "9"}]
  scoring: [status, citations]
  reviewed: false
  refs: []
  depends_on: []
  rationale: Art 9 caps probation.
"""

GROUNDING_AND_REFUSE = """
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


@pytest.fixture
def project(tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    (pack / "evals" / "cases").mkdir(parents=True)
    (pack / "evals" / "rubrics").mkdir()
    (pack / "system_prompt.md").write_text("You answer questions about the corpus.")
    cases = pack / "evals" / "cases"
    (cases / "cases.yaml").write_text(GROUNDING_AND_REFUSE)
    (cases / "cite.yaml").write_text(CITE_CASE)
    (cases / "bilingual.yaml").write_text(PAIR)
    rubrics = pack / "evals" / "rubrics"
    (rubrics / "grounding.md").write_text(GROUNDING_RUBRIC)
    (rubrics / "refusal.md").write_text(REFUSAL_RUBRIC)
    (rubrics / "bilingual.md").write_text(BILINGUAL_RUBRIC)
    write_corpus(tmp_path)
    write_judge_config(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    return tmp_path


def judged_run(project, *, judge_passes=True):
    """Run the grounding and refuse cases with the judge's verdicts; return the run directory."""
    before = set((project / "runs").glob("*")) if (project / "runs").exists() else set()
    fake = FakeOpenRouter(
        [
            search("probation"),
            grounded_answer("9"),
            judge_says(claims_supported=True, cites_relevant=judge_passes),
            final_answer_response("refused", "legal_advice"),
            judge_says(explains_why=judge_passes),
        ]
    )
    assert run(project, fake, "run", "--case", "grounding-en-001", "--case", "refuse-en-001") == 0
    [run_dir] = [p for p in (project / "runs").glob("*") if p.is_dir() and p not in before]
    return run_dir


def judge_check(project, *args, fake=None):
    fake = fake or FakeOpenRouter()
    return run(project, fake, "judge-check", *args)


def check_dir(project):
    return project / "pack" / "evals" / "judge_check"


def labels(project):
    return yaml.safe_load((check_dir(project) / "labels.yaml").read_text(encoding="utf-8"))


def verdicts(project):
    return json.loads((check_dir(project) / "verdicts.json").read_text(encoding="utf-8"))


def entry_with(entries, criterion):
    [entry] = [e for e in entries if criterion in e["criteria"]]
    return entry


def test_sample_writes_a_blind_labelling_file_and_keeps_the_verdicts_apart(project):
    run_dir = judged_run(project, judge_passes=False)

    assert judge_check(project, "sample", str(run_dir)) == 0

    text = (check_dir(project) / "labels.yaml").read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "cites_relevant reason" not in text and "passed" not in text
    entries = labels(project)
    assert len(entries) == 2
    grounding = entry_with(entries, "claims_supported")
    assert grounding["question"] == "How long can probation last under the Statute?"
    assert grounding["answer"]["text"] == "Probation may last up to six months."
    assert grounding["answer"]["citations"] == ["statute Art 9"]
    assert [s["text"] for s in grounding["sources"]] == [
        "Article (9) Probation. Probation shall not exceed six months."
    ]
    assert grounding["criteria"]["claims_supported"] == {
        "rule": "Every claim in the answer is supported by the cited chunk text.",
        "label": None,
    }
    stored = verdicts(project)[grounding["id"]]
    assert stored["verdict"]["criteria"]["cites_relevant"]["passed"] is False
    assert stored["origin"]["case_id"] == "grounding-en-001"


def new_run(project, fake, *args):
    before = set((project / "runs").glob("*")) if (project / "runs").exists() else set()
    assert run(project, fake, "run", *args) == 0
    [run_dir] = [p for p in (project / "runs").glob("*") if p.is_dir() and p not in before]
    return run_dir


def cite_run(project):
    fake = FakeOpenRouter([search("probation"), grounded_answer("9")])
    return new_run(project, fake, "--case", "cite-en-001")


def pair_run(project, judge_passes=True):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            search("التجربة"),
            answer(AR_ANSWER, "9"),
            judge_says(same_meaning=judge_passes),
        ]
    )
    return new_run(project, fake, "--case", "bilingual-probation-001")


def test_sample_draws_from_each_category_in_turn_mixing_judge_pass_and_fail(project):
    runs = [str(judged_run(project, judge_passes=p)) for p in (True, False)]

    assert judge_check(project, "sample", *runs, "--size", "3") == 0

    stored = verdicts(project)
    cases = sorted(v["origin"]["case_id"] for v in stored.values())
    assert cases == ["grounding-en-001", "grounding-en-001", "refuse-en-001"]
    grounding = [
        v["verdict"]["passed"]
        for v in stored.values()
        if v["origin"]["case_id"] == "grounding-en-001"
    ]
    assert sorted(grounding) == [False, True]


def test_unjudged_answers_are_sampled_after_judged_ones_with_a_pending_verdict(project):
    runs = [str(judged_run(project)), str(cite_run(project))]

    assert judge_check(project, "sample", *runs, "--size", "3") == 0

    stored = verdicts(project)
    [(cite_id, cite)] = [
        (k, v) for k, v in stored.items() if v["origin"]["case_id"] == "cite-en-001"
    ]
    assert cite["verdict"] is None
    items = json.loads((check_dir(project) / "items.json").read_text())
    assert items[cite_id]["rubric"] == "grounding"
    assert items[cite_id]["sources"][0]["id"] == "statute:en:9:1"


def test_a_bilingual_pair_is_one_item_with_both_halves_and_readable_arabic(project):
    run_dir = pair_run(project, judge_passes=False)

    assert judge_check(project, "sample", str(run_dir)) == 0

    text = (check_dir(project) / "labels.yaml").read_text(encoding="utf-8")
    assert AR_ANSWER in text and "\\u" not in text
    [entry] = labels(project)
    assert entry["question"]["ar"] == "ما أقصى مدة لفترة التجربة في النظام؟"
    assert entry["answer"]["en"]["text"] == EN_ANSWER
    assert entry["answer"]["ar"]["text"] == AR_ANSWER
    assert list(entry["criteria"]) == ["same_meaning"]
    [stored] = verdicts(project).values()
    assert stored["verdict"]["criteria"]["same_meaning"]["passed"] is False


def pairs(both_pass, owner_only, judge_only, both_fail):
    return (
        [(True, True)] * both_pass
        + [(True, False)] * owner_only
        + [(False, True)] * judge_only
        + [(False, False)] * both_fail
    )


def test_kappa_matches_the_textbook_example():
    result = measure(pairs(20, 5, 10, 15))

    assert result.n == 50
    assert result.agreement == pytest.approx(0.7)
    assert result.kappa == pytest.approx(0.4)


def test_kappa_is_undefined_when_both_raters_never_vary():
    result = measure(pairs(6, 0, 0, 0))

    assert result.agreement == 1.0
    assert result.kappa is None


def test_no_pairs_measure_nothing():
    result = measure([])

    assert (result.n, result.agreement, result.kappa) == (0, None, None)


def ledger_records(project):
    path = project / "runs" / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_judge_fills_the_missing_verdicts_through_the_ledger(project, capsys):
    run_dir = cite_run(project)
    assert judge_check(project, "sample", str(run_dir)) == 0
    fake = FakeOpenRouter([judge_says(cost=0.004, claims_supported=False, cites_relevant=True)])

    assert judge_check(project, "judge", fake=fake) == 0

    [request] = fake.chat_requests
    material = request["messages"][1]["content"]
    assert "Which article caps probation?" in material
    assert "Probation may last up to six months." in material
    assert "Probation shall not exceed six months." in material
    [stored] = verdicts(project).values()
    assert stored["verdict"]["passed"] is False
    assert stored["verdict"]["model"] == "openai/gpt-5.6-terra"
    assert stored["verdict"]["criteria"]["claims_supported"]["passed"] is False
    judge_spend = [r for r in ledger_records(project) if r["purpose"] == "judge"][-1]
    assert (judge_spend["cost"], judge_spend["model"]) == (0.004, "openai/gpt-5.6-terra")
    assert "judged 1 item(s)" in capsys.readouterr().out


def test_judge_takes_broken_items_first_and_stops_at_the_limit(project):
    pair = pair_run(project)
    cite = cite_run(project)
    write_broken(project, BROKEN_PAIR.format(run=pair.name))
    assert judge_check(project, "sample", str(pair), str(cite)) == 0
    fake = FakeOpenRouter([judge_says(same_meaning=False)])

    assert judge_check(project, "judge", "--limit", "1", fake=fake) == 0

    stored = verdicts(project).values()
    judged = [v["origin"] for v in stored if v["verdict"] is not None and "breakage" in v["origin"]]
    assert len(judged) == 1
    assert [v["origin"]["case_id"] for v in stored if v["verdict"] is None] == ["cite-en-001"]


def test_an_item_shows_the_judge_exactly_what_it_saw_during_the_run(project):
    fake = FakeOpenRouter(
        [
            search("probation"),
            answer(EN_ANSWER, "9"),
            search("التجربة"),
            answer(AR_ANSWER, "9"),
            judge_says(same_meaning=True),
        ]
    )
    run_dir = new_run(project, fake, "--case", "bilingual-probation-001")
    assert judge_check(project, "sample", str(run_dir)) == 0

    [item] = json.loads((check_dir(project) / "items.json").read_text()).values()
    assert item_material(item) == fake.chat_requests[-1]["messages"][1]["content"]


def test_judge_refuses_to_start_when_the_budget_guard_says_no(project, capsys):
    assert judge_check(project, "sample", str(cite_run(project))) == 0
    fake = FakeOpenRouter([], key_usage=19.999)

    assert judge_check(project, "judge", fake=fake) == 2

    assert "over budget" in capsys.readouterr().err
    assert fake.chat_requests == []
    [stored] = verdicts(project).values()
    assert stored["verdict"] is None


def agreement(project):
    return run(project, FakeOpenRouter(), "judge-agreement")


def label(project, decide):
    """Fill each criterion's label with decide(case_id, criterion, judge_passed)."""
    path = check_dir(project) / "labels.yaml"
    stored = verdicts(project)
    text = path.read_text(encoding="utf-8")
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    entries = yaml.safe_load(text)
    for entry in entries:
        origin, verdict = stored[entry["id"]]["origin"], stored[entry["id"]]["verdict"]
        for name, criterion in entry["criteria"].items():
            judge_passed = verdict["criteria"][name]["passed"] if verdict else None
            criterion["label"] = decide(origin["case_id"], name, judge_passed)
    path.write_text(header + yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")


def two_judged_runs(project):
    runs = [str(judged_run(project, judge_passes=p)) for p in (True, False)]
    assert judge_check(project, "sample", *runs) == 0


def agree_on_grounding_disagree_on_refusal(case_id, criterion, judge_passed):
    owner_passes = judge_passed if case_id.startswith("grounding") else not judge_passed
    return "pass" if owner_passes else "fail"


def test_agreement_reports_raw_agreement_and_kappa_and_flags_untrusted_rubrics(project, capsys):
    two_judged_runs(project)
    label(project, agree_on_grounding_disagree_on_refusal)
    capsys.readouterr()

    assert agreement(project) == 0

    result = json.loads((check_dir(project) / "agreement.json").read_text())
    assert result["n"] == 6
    assert result["agreement"] == pytest.approx(4 / 6)
    assert result["kappa"] == pytest.approx(0.25)
    grounding, refusal = result["rubrics"]["grounding"], result["rubrics"]["refusal"]
    assert (grounding["n"], grounding["kappa"], grounding["trusted"]) == (4, 1.0, True)
    assert grounding["criteria"]["cites_relevant"] == {"n": 2, "agreement": 1.0, "kappa": 1.0}
    assert grounding["criteria"]["claims_supported"]["kappa"] is None
    assert (refusal["n"], refusal["kappa"], refusal["trusted"]) == (2, -1.0, False)
    assert result["untrusted_categories"] == ["refuse"]
    out = capsys.readouterr().out
    assert "UNTRUSTED" in out and "refuse" in out
    assert "0.25" in out


def test_later_runs_record_the_agreement_in_their_summary(project):
    two_judged_runs(project)
    label(project, agree_on_grounding_disagree_on_refusal)
    assert agreement(project) == 0

    run_dir = judged_run(project)

    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["judge_agreement"]["kappa"] == pytest.approx(0.25)
    assert summary["judge_agreement"]["untrusted_categories"] == ["refuse"]


def test_unlabelled_criteria_and_unjudged_items_are_left_out_and_counted(project, capsys):
    two_judged_runs(project)
    label(
        project,
        lambda case_id, criterion, judge_passed: None if criterion == "explains_why" else "pass",
    )
    capsys.readouterr()

    assert agreement(project) == 0

    result = json.loads((check_dir(project) / "agreement.json").read_text())
    assert (result["n"], result["unlabelled"], result["unjudged"]) == (4, 2, 0)
    assert result["rubrics"]["refusal"]["n"] == 0
    assert result["rubrics"]["refusal"]["trusted"] is False
    assert "2 unlabelled" in capsys.readouterr().out


def test_agreement_without_any_label_explains_what_to_do(project, capsys):
    two_judged_runs(project)

    assert agreement(project) == 2

    assert "no labelled decisions" in capsys.readouterr().err
    assert not (check_dir(project) / "agreement.json").exists()


def test_agreement_refuses_a_label_that_is_not_pass_or_fail(project, capsys):
    two_judged_runs(project)
    label(project, lambda case_id, criterion, judge_passed: "maybe")

    assert agreement(project) == 2

    err = capsys.readouterr().err
    assert "jc-00" in err and "pass or fail" in err


BROKEN_PAIR = """
- breakage: inconsistent_pair
  run: {run}
  case: bilingual-probation-001
  answers:
    ar:
      status: answered
      refusal_reason: null
      answer: "لا تزيد فترة التجربة على 3 أشهر (المادة 9)."
      citations: [{{instrument: statute, article: "9"}}]
"""
BROKEN_AR = "لا تزيد فترة التجربة على 3 أشهر (المادة 9)."


def write_broken(project, text):
    check_dir(project).mkdir(parents=True, exist_ok=True)
    (check_dir(project) / "broken.yaml").write_text(text, encoding="utf-8")


def test_broken_answers_replace_a_real_answer_and_wait_for_a_verdict(project):
    run_dir = pair_run(project)
    write_broken(project, BROKEN_PAIR.format(run=run_dir.name))

    assert judge_check(project, "sample", str(run_dir)) == 0

    stored = verdicts(project)
    [(broken_id, broken)] = [(k, v) for k, v in stored.items() if "breakage" in v["origin"]]
    assert broken["origin"]["breakage"] == "inconsistent_pair"
    assert broken["verdict"] is None
    entries = {e["id"]: e for e in labels(project)}
    assert len(entries) == 2
    assert entries[broken_id]["answer"]["ar"]["text"] == BROKEN_AR
    assert entries[broken_id]["answer"]["en"]["text"] == EN_ANSWER
    text = (check_dir(project) / "labels.yaml").read_text(encoding="utf-8")
    assert "breakage" not in text and "inconsistent_pair" not in text


@pytest.mark.parametrize(
    "broken, message",
    [
        (BROKEN_PAIR.replace("bilingual-probation-001", "no-such-case"), "no answer from run"),
        (BROKEN_PAIR.replace("status: answered", "status: maybe"), "status must be one of"),
        (BROKEN_PAIR.replace("    ar:", "    fr:"), "answers must be keyed by"),
        ("- breakage: x\n", "needs exactly breakage, run, case and answers"),
    ],
)
def test_a_malformed_broken_answer_is_refused(project, capsys, broken, message):
    run_dir = pair_run(project)
    write_broken(project, broken.format(run=run_dir.name))

    assert judge_check(project, "sample", str(run_dir)) == 2

    assert message in capsys.readouterr().err
    assert not (check_dir(project) / "labels.yaml").exists()


def test_sample_refuses_to_overwrite_labels_the_owner_has_started(project, capsys):
    run_dir = judged_run(project)
    assert judge_check(project, "sample", str(run_dir)) == 0
    path = check_dir(project) / "labels.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("label:\n", "label: pass\n", 1))

    assert judge_check(project, "sample", str(run_dir)) == 2

    assert "already holds labels" in capsys.readouterr().err
    assert "label: pass" in path.read_text(encoding="utf-8")
