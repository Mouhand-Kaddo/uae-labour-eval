import pytest

from eval_harness.manifest import ManifestError, load_manifest

SOURCE = """
[instruments.statute]
title = "The Statute"

[[sources]]
id = "statute-ar"
instrument = "statute"
language = "ar"
official_url = "https://official.example/ar"
wayback_url = "https://web.archive.org/web/20260101000000id_/https://official.example/ar"
retrieved = 2026-10-17
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
indexed = false
"""


def manifest_with(tmp_path, extra):
    (tmp_path / "manifest.toml").write_text(SOURCE + extra, encoding="utf-8")
    return tmp_path


def test_a_source_glyph_table_maps_font_and_glyph_id_to_text(tmp_path):
    pack = manifest_with(
        tmp_path,
        """
[sources.glyphs."ABCDEF+Naskh"]
655 = "ك"
1756 = ""
""",
    )

    [source] = load_manifest(pack).sources

    assert source.glyphs == {("ABCDEF+Naskh", 655): "ك", ("ABCDEF+Naskh", 1756): ""}


def test_a_source_without_a_glyph_table_has_an_empty_one(tmp_path):
    [source] = load_manifest(manifest_with(tmp_path, "")).sources

    assert source.glyphs == {}


@pytest.mark.parametrize(
    "extra",
    [
        '[sources.glyphs."ABCDEF+Naskh"]\nx12 = "ك"\n',
        '[sources.glyphs."ABCDEF+Naskh"]\n12 = 5\n',
        '[sources.glyphs]\n"ABCDEF+Naskh" = "ك"\n',
    ],
)
def test_a_malformed_glyph_table_is_rejected(tmp_path, extra):
    with pytest.raises(ManifestError, match="glyphs"):
        load_manifest(manifest_with(tmp_path, extra))
