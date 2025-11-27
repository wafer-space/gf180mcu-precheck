#!/usr/bin/env python3
"""
Run a precheck using only Python standard library.

Usage:
    python3 run_precheck.py <gds_file> <top_cell> [die_id] [server_url]

Examples:
    python3 run_precheck.py chip_top.gds chip_top
    python3 run_precheck.py chip_top.gds chip_top ABCD1234
    python3 run_precheck.py chip_top.gds chip_top ABCD1234 http://precheck.example.com:8000
"""

import json
import time
import urllib.request
from pathlib import Path


def run_precheck(
    server: str,
    gds_file: str,
    top_cell: str,
    die_id: str = "FFFFFFFF",
    api_key: str | None = None,
) -> bool:
    """
    Upload a GDS file, run precheck, and download the result.

    Args:
        server: Base URL of the precheck server (e.g., "http://localhost:8000")
        gds_file: Path to the GDS file to check
        top_cell: Name of the top-level cell
        die_id: 8-character hex ID for the die (default: "FFFFFFFF")
        api_key: Optional API key for authentication

    Returns:
        True if precheck passed, False otherwise
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 1. Upload the GDS file
    print(f"Uploading {gds_file}...")
    boundary = "----PythonFormBoundary"
    filename = Path(gds_file).name
    with open(gds_file, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    upload_headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        **headers,
    }
    req = urllib.request.Request(
        f"{server}/api/v1/uploads",
        data=body,
        headers=upload_headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        upload = json.loads(resp.read())
    upload_id = upload["Id"]
    print(f"Upload ID: {upload_id}")

    # 2. Create precheck run
    print("Creating precheck run...")
    run_data = json.dumps({
        "upload_id": upload_id,
        "top_cell": top_cell,
        "die_id": die_id,
    }).encode()
    run_headers = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(
        f"{server}/api/v1/prechecks",
        data=run_data,
        headers=run_headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        run = json.loads(resp.read())
    run_id = run["Id"]
    print(f"Run ID: {run_id}")

    # 3. Poll for completion
    print("Waiting for completion...")
    while True:
        req = urllib.request.Request(
            f"{server}/api/v1/prechecks/{run_id}",
            headers=headers,
        )
        with urllib.request.urlopen(req) as resp:
            run = json.loads(resp.read())
        status = run["State"]["Status"]
        print(f"  Status: {status}")
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(5)

    # 4. Check result
    exit_code = run["State"]["ExitCode"]
    if exit_code == 0:
        print("Precheck PASSED!")
        # Download output
        output_file = f"{top_cell}_output.gds"
        req = urllib.request.Request(
            f"{server}/api/v1/prechecks/{run_id}/output",
            headers=headers,
        )
        with urllib.request.urlopen(req) as resp:
            with open(output_file, "wb") as f:
                f.write(resp.read())
        print(f"Output saved to {output_file}")
        return True
    else:
        print(f"Precheck FAILED (exit code {exit_code})")
        error = run["State"]["Error"]
        if error:
            print(f"Error: {error}")
        return False


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <gds_file> <top_cell> [die_id] [server_url]")
        print()
        print("Arguments:")
        print("  gds_file    Path to GDS file")
        print("  top_cell    Name of top-level cell")
        print("  die_id      8-char hex ID (default: FFFFFFFF)")
        print("  server_url  Server URL (default: http://localhost:8000)")
        print()
        print("Environment:")
        print("  PRECHECK_API_KEY  API key for authentication (optional)")
        sys.exit(1)

    gds_file = sys.argv[1]
    top_cell = sys.argv[2]
    die_id = sys.argv[3] if len(sys.argv) > 3 else "FFFFFFFF"
    server = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:8000"
    api_key = os.environ.get("PRECHECK_API_KEY")

    success = run_precheck(server, gds_file, top_cell, die_id, api_key)
    sys.exit(0 if success else 1)
