#!/usr/bin/env python3
"""Extract version information from Nix flake and environment.

This script extracts pinned versions from flake.lock and runtime tool versions
from the Nix development environment. Output is JSON suitable for Docker build args.
"""

import json
import subprocess
import sys
from pathlib import Path


def get_flake_lock_info(flake_lock_path: Path) -> dict:
    """Extract version info from flake.lock."""
    with open(flake_lock_path) as f:
        lock = json.load(f)

    nodes = lock.get("nodes", {})
    info = {}

    # Extract key inputs with their refs and revisions
    inputs_to_extract = {
        "nix-eda": "nix_eda",
        "librelane": "librelane",
        "nixpkgs": "nixpkgs",
        "ciel": "ciel",
    }

    for node_name, key_prefix in inputs_to_extract.items():
        node = nodes.get(node_name, {})
        locked = node.get("locked", {})
        original = node.get("original", {})

        # Get the ref (branch/tag) if available
        ref = original.get("ref", "")
        # Get the revision (commit hash)
        rev = locked.get("rev", "")
        # Get owner/repo for URL construction
        owner = locked.get("owner", "")
        repo = locked.get("repo", "")

        if ref:
            info[f"{key_prefix}_ref"] = ref
        if rev:
            info[f"{key_prefix}_rev"] = rev
        if owner and repo:
            info[f"{key_prefix}_url"] = f"github:{owner}/{repo}"
            if ref:
                info[f"{key_prefix}_url"] += f"/{ref}"

    return info


def get_tool_versions() -> dict:
    """Get runtime tool versions from nix environment."""
    # Commands to extract versions
    version_commands = {
        "klayout_version": "klayout -v | head -1",
        "magic_version": "magic --version | head -1",
        "python_version": "python3 --version",
    }

    info = {}

    for key, cmd in version_commands.items():
        try:
            result = subprocess.run(
                [
                    "nix",
                    "develop",
                    "--accept-flake-config",
                    "--command",
                    "bash",
                    "-c",
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # Clean up version strings
                version = version.replace("KLayout ", "")
                version = version.replace("Python ", "")
                info[key] = version
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"Warning: Failed to get {key}: {e}", file=sys.stderr)

    return info


def main():
    """Extract all version info and output as JSON."""
    # Find flake.lock relative to this script or current directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    flake_lock_path = repo_root / "flake.lock"
    if not flake_lock_path.exists():
        flake_lock_path = Path("flake.lock")

    if not flake_lock_path.exists():
        print("Error: flake.lock not found", file=sys.stderr)
        sys.exit(1)

    # Collect all version info
    versions = {}

    # Get flake.lock info
    versions.update(get_flake_lock_info(flake_lock_path))

    # Check if we should skip tool version extraction (for CI without nix env)
    if "--flake-only" not in sys.argv:
        versions.update(get_tool_versions())

    # Output format based on flags
    if "--docker-args" in sys.argv:
        # Output as Docker build-arg format
        for key, value in sorted(versions.items()):
            print(f"--build-arg {key.upper()}={value}")
    elif "--github-output" in sys.argv:
        # Output for GitHub Actions $GITHUB_OUTPUT
        for key, value in sorted(versions.items()):
            print(f"{key}={value}")
    else:
        # Default: JSON output
        print(json.dumps(versions, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
