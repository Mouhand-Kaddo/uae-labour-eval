import hashlib

import httpx
import pytest

from eval_harness.cli import main

OFFICIAL = b"%PDF-1.7 official copy"
OTHER = b"%PDF-1.7 a different edition"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(expected_sha256: str) -> str:
    return f"""
[instruments.statute]
title = "The Statute"

[[sources]]
id = "statute-en"
instrument = "statute"
language = "en"
official_url = "https://official.example/statute/en/download"
wayback_url = "https://web.archive.org/web/20260407120528id_/https://official.example/statute/en/download"
retrieved = 2026-10-17
sha256 = "{expected_sha256}"
indexed = false
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pack").mkdir()
    (tmp_path / "config.toml").write_text(
        """
pack = "pack"
runs_dir = "runs"
sources_dir = "data/sources"
index_dir = "data/index"

[models]
agent = "anthropic/claude-haiku-5.5"
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
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return tmp_path


class FakeWeb:
    def __init__(self, routes):
        self.routes = routes
        self.requested = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        status, body = self.routes.get(url, (404, b""))
        return httpx.Response(status, content=body)


OFFICIAL_URL = "https://official.example/statute/en/download"
WAYBACK_URL = (
    "https://web.archive.org/web/20260407120528id_/https://official.example/statute/en/download"
)


def fetch(project, web):
    return main(["--config", str(project / "config.toml"), "fetch"], transport=web.transport)


def saved(project):
    return project / "data" / "sources" / "statute-en.pdf"


def write_manifest(project, expected_sha256):
    (project / "pack" / "manifest.toml").write_text(manifest(expected_sha256))


def test_fetch_saves_the_official_file_when_its_hash_matches(project):
    write_manifest(project, sha256(OFFICIAL))
    web = FakeWeb({OFFICIAL_URL: (200, OFFICIAL)})

    assert fetch(project, web) == 0

    assert saved(project).read_bytes() == OFFICIAL
    assert web.requested == [OFFICIAL_URL]


def test_fetch_falls_back_to_the_wayback_snapshot_when_the_portal_blocks_it(project, capsys):
    write_manifest(project, sha256(OFFICIAL))
    web = FakeWeb({OFFICIAL_URL: (403, b"Forbidden"), WAYBACK_URL: (200, OFFICIAL)})

    assert fetch(project, web) == 0

    assert saved(project).read_bytes() == OFFICIAL
    assert web.requested == [OFFICIAL_URL, WAYBACK_URL]
    assert "wayback" in capsys.readouterr().out


def test_fetch_falls_back_when_the_portal_serves_a_different_file(project):
    write_manifest(project, sha256(OFFICIAL))
    web = FakeWeb({OFFICIAL_URL: (200, OTHER), WAYBACK_URL: (200, OFFICIAL)})

    assert fetch(project, web) == 0

    assert saved(project).read_bytes() == OFFICIAL


def test_fetch_refuses_a_file_whose_hash_does_not_match(project, capsys):
    write_manifest(project, sha256(OFFICIAL))
    web = FakeWeb({OFFICIAL_URL: (200, OTHER), WAYBACK_URL: (200, OTHER)})

    assert fetch(project, web) == 2

    assert not saved(project).exists()
    err = capsys.readouterr().err
    assert "statute-en" in err and "hash mismatch" in err and sha256(OTHER) in err


def test_fetch_skips_a_source_already_saved_with_the_right_hash(project):
    write_manifest(project, sha256(OFFICIAL))
    saved(project).parent.mkdir(parents=True)
    saved(project).write_bytes(OFFICIAL)
    web = FakeWeb({})

    assert fetch(project, web) == 0

    assert web.requested == []


def test_fetch_replaces_a_saved_file_whose_hash_no_longer_matches(project):
    write_manifest(project, sha256(OFFICIAL))
    saved(project).parent.mkdir(parents=True)
    saved(project).write_bytes(OTHER)
    web = FakeWeb({OFFICIAL_URL: (200, OFFICIAL)})

    assert fetch(project, web) == 0

    assert saved(project).read_bytes() == OFFICIAL


def test_fetch_rejects_a_manifest_entry_missing_a_field(project, capsys):
    (project / "pack" / "manifest.toml").write_text(
        manifest(sha256(OFFICIAL)).replace('language = "en"\n', "")
    )

    assert fetch(project, FakeWeb({})) == 2

    assert "language" in capsys.readouterr().err


def test_ingest_refuses_a_source_that_has_not_been_fetched(project, capsys):
    (project / "pack" / "manifest.toml").write_text(
        manifest(sha256(OFFICIAL)).replace(
            "indexed = false", "indexed = true\nheading_pattern = 'Article \\((\\d+)\\)'"
        )
    )

    assert main(["--config", str(project / "config.toml"), "ingest"]) == 2

    assert "run fetch" in capsys.readouterr().err
    assert not (project / "data" / "index").exists()
