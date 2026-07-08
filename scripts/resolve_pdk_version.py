#!/usr/bin/env python3
"""Resolve the PDK version for the PDK_COMMIT pinned in the Makefile.

The Makefile pins the PDK as an open_pdks commit hash (used by `ciel enable`).
Downstream consumers (platform.wafer.space) need a human-meaningful PDK
version, published as the `gf180mcu-precheck.pdk_version` OCI image label.
This script maps the pinned commit to the `VERSION` file content of open_pdks
at that commit.

Prints GitHub Actions output lines (`pdk_commit=...` / `pdk_version=...`) on
stdout so the workflow can append them to $GITHUB_OUTPUT.

Any value that cannot be resolved is a fatal error: the script exits non-zero
so the image build fails instead of publishing an image with missing labels.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OPEN_PDKS_VERSION_URL = (
    "https://raw.githubusercontent.com/efabless/open_pdks/{commit}/VERSION"
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_pdk_commit(makefile_text: str) -> str:
    """Extract the PDK_COMMIT hash from Makefile text (fatal if absent)."""
    match = re.search(
        r"^PDK_COMMIT\s*\??=\s*([0-9a-f]{40})\s*$", makefile_text, re.MULTILINE
    )
    if not match:
        fail(
            "Could not find 'PDK_COMMIT ?= <40-char sha1>' in the Makefile; "
            "cannot resolve a PDK version for the image labels."
        )
    return match.group(1)


def fetch_pdk_version(commit: str) -> str:
    """Fetch open_pdks VERSION at the given commit (fatal on any failure)."""
    url = OPEN_PDKS_VERSION_URL.format(commit=commit)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            version = response.read().decode("utf-8").strip()
    except urllib.error.URLError as exc:
        fail(f"Failed to fetch {url}: {exc}")
    except TimeoutError as exc:
        fail(f"Timed out fetching {url}: {exc}")

    if not re.fullmatch(r"\d+\.\d+(\.\d+)*", version):
        fail(
            f"open_pdks VERSION at commit {commit[:12]} does not look like a "
            f"version number: {version!r}"
        )
    return version


def main() -> None:
    makefile_path = Path(__file__).resolve().parent.parent / "Makefile"
    if len(sys.argv) > 1:
        makefile_path = Path(sys.argv[1])
    if not makefile_path.is_file():
        fail(f"Makefile not found at {makefile_path}")

    commit = parse_pdk_commit(makefile_path.read_text())
    version = fetch_pdk_version(commit)

    print(f"pdk_commit={commit}")
    print(f"pdk_version={version}")


if __name__ == "__main__":
    main()
