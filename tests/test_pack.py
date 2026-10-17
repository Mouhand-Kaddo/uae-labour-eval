from pathlib import Path

from eval_harness.cases import load_cases
from eval_harness.config import load_config
from eval_harness.manifest import load_manifest
from eval_harness.scorers import SCORERS

REPO = Path(__file__).resolve().parent.parent


def test_committed_config_points_at_a_pack_whose_cases_load():
    config = load_config(REPO / "config.toml")
    assert config.budget.ceiling_usd == 20.0
    assert (config.pack / "system_prompt.md").is_file()

    cases = load_cases(config.pack / "evals" / "cases", SCORERS)

    assert any(case.category == "refuse" for case in cases)
    assert not any(case.reviewed for case in cases)


def test_committed_manifest_indexes_only_the_english_labour_law_for_now():
    manifest = load_manifest(load_config(REPO / "config.toml").pack)

    assert [s.id for s in manifest.indexed_sources] == ["labour-law-en"]
    assert all(s.wayback_url.startswith("https://web.archive.org/web/") for s in manifest.sources)
