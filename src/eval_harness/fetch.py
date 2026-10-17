"""Download every source in the manifest, official URL first, then the pinned Wayback snapshot."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import httpx

from eval_harness.manifest import Manifest, Source

USER_AGENT = "uae-labour-eval-fetch/0.1"


class FetchError(Exception):
    pass


def source_path(sources_dir: Path, source: Source) -> Path:
    return sources_dir / f"{source.id}.pdf"


def fetch_sources(
    manifest: Manifest,
    sources_dir: Path,
    *,
    transport: httpx.BaseTransport | None = None,
    echo: Callable[[str], None] = print,
) -> None:
    """Save each source whose download matches its expected SHA-256; raise FetchError otherwise."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        timeout=120.0,
        headers={"User-Agent": USER_AGENT},
    ) as http:
        for source in manifest.sources:
            path = source_path(sources_dir, source)
            if path.is_file() and _sha256(path.read_bytes()) == source.sha256:
                echo(f"ok {source.id}: already saved")
                continue
            attempts = []
            for label, url in (("official", source.official_url), ("wayback", source.wayback_url)):
                outcome = _download(http, url)
                if isinstance(outcome, bytes) and _sha256(outcome) == source.sha256:
                    tmp = path.with_suffix(".part")
                    tmp.write_bytes(outcome)
                    tmp.replace(path)
                    echo(f"ok {source.id}: saved from {label} {url}")
                    break
                if isinstance(outcome, bytes):
                    outcome = f"hash mismatch, got {_sha256(outcome)}"
                attempts.append(f"{label}: {outcome}")
            else:
                failures.append(f"{source.id}: " + "; ".join(attempts))
    if failures:
        raise FetchError("\n".join(failures))


def _download(http: httpx.Client, url: str) -> bytes | str:
    try:
        response = http.get(url)
    except httpx.HTTPError as exc:
        return f"request failed ({type(exc).__name__})"
    if response.status_code != 200:
        return f"HTTP {response.status_code}"
    return response.content


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
