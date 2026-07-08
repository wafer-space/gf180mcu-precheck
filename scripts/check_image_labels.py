#!/usr/bin/env python3
"""Verify all required OCI image labels are present and non-empty.

Reads the docker/metadata-action JSON output from the METADATA_JSON
environment variable and asserts every label the image build promises to
publish actually resolved to a non-empty value.

This guards against silent failures where a GitHub Actions expression like
`${{ steps.pdk.outputs.pdk_version }}` expands to an empty string (typo'd
step id, renamed output, skipped step) and an image gets published with a
missing or empty label. Any missing/empty label is fatal: exit non-zero so
the build fails before the image is pushed.
"""

from __future__ import annotations

import json
import os
import sys

REQUIRED_LABELS = [
    "gf180mcu-precheck.pdk_commit",
    "gf180mcu-precheck.pdk_version",
    "org.opencontainers.image.created",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.version",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    raw = os.environ.get("METADATA_JSON", "")
    if not raw.strip():
        fail("METADATA_JSON environment variable is not set or empty")

    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"METADATA_JSON is not valid JSON: {exc}")

    labels = metadata.get("labels")
    if not isinstance(labels, dict):
        fail("METADATA_JSON has no 'labels' object")

    problems = [
        name for name in REQUIRED_LABELS if not str(labels.get(name, "")).strip()
    ]
    if problems:
        for name in problems:
            print(f"ERROR: required image label missing or empty: {name}",
                  file=sys.stderr)
        raise SystemExit(1)

    print("All required image labels resolved:")
    for name in REQUIRED_LABELS:
        print(f"  {name}={labels[name]}")


if __name__ == "__main__":
    main()
