# Copyright (c) 2025 wafer.space
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.9"
# dependencies = ["docker"]
# ///

"""Verify a built gf180mcu-precheck Docker image by running a complete DRC check.

This script is a faithful, self-contained stand-in for the way the
platform.wafer.space checker machines launch a manufacturability check
(see ``wafer_space/projects/tasks_checks.py:do_starting``). It deliberately
reproduces the *exact* mechanism the production checkers use rather than a
convenient shortcut, so that a passing run here proves the published image can
actually complete a DRC check the same way the platform invokes it:

* the same ``precheck.py`` command line
  (``--input /input/design.gds --output /output/design.gds --top ... --slot ... --id ...``),
* the same container configuration
  (``working_dir=/workspace``, ``network_disabled=True``, ``mem_limit``,
  ``COLUMNS``/``TERM`` environment),
* the same no-bind-mount file transfer: the input layout is uploaded via
  ``put_archive`` to ``/input/design.gds`` and an empty ``/output`` directory is
  created, then the output GDS is read back from ``/output/design.gds``.

The image is referenced by its immutable content-addressed ID (e.g. the
``imageid`` emitted by docker/build-push-action), never by a mutable tag, so the
verification always runs the exact image that was built even when several
images are being built/published concurrently on a shared Docker daemon.

Exit status is ``0`` only if the container exits ``0`` *and* a non-empty
``/output/design.gds`` was produced.
"""

import argparse
import io
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import docker
import docker.errors


# These two helpers are intentionally identical to
# platform.wafer.space/wafer_space/projects/docker_utils.py so the bytes
# uploaded to the container match production exactly.
def create_tar_archive(file_path: Path, arcname: str) -> io.BytesIO:
    """Create an in-memory tar archive containing ``file_path`` as ``arcname``."""
    # A temp file keeps peak memory low for large GDS files, matching the
    # platform helper, then we hand back an in-memory stream for put_archive.
    with tempfile.NamedTemporaryFile(suffix=".tar") as temp_file:
        with tarfile.open(fileobj=temp_file, mode="w") as tar:
            tar.add(str(file_path), arcname=arcname)
        temp_file.seek(0)
        return io.BytesIO(temp_file.read())


def create_directory_tar(dirname: str) -> io.BytesIO:
    """Create an in-memory tar archive containing a single empty directory."""
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        dir_info = tarfile.TarInfo(name=dirname)
        dir_info.type = tarfile.DIRTYPE
        dir_info.mode = 0o755
        tar.addfile(dir_info)
    tar_stream.seek(0)
    return tar_stream


def run_check(
    image: str,
    input_layout: Path,
    top: str,
    slot: str,
    die_id: str,
    mem_limit: str,
    output_path: Optional[Path] = None,
) -> int:
    """Run the precheck in a container exactly as the platform does.

    Returns the container exit code (and asserts the output GDS exists). If
    ``output_path`` is given, the produced ``/output/design.gds`` is copied
    there so callers (e.g. CI) can upload it as an artifact.
    """
    client = docker.from_env()

    # The exact command the checker machines build in do_starting. The image
    # ENTRYPOINT is ``dev-shell`` and WORKDIR is /workspace, so this runs inside
    # the offline nix environment with precheck.py on the path.
    command = [
        "python3",
        "precheck.py",
        "--input",
        "/input/design.gds",
        "--output",
        "/output/design.gds",
        "--top",
        top,
        "--slot",
        slot,
        "--id",
        die_id,
    ]
    print(f"[verify] image:   {image}")
    print(f"[verify] command: {' '.join(command)}")
    print(f"[verify] input:   {input_layout} -> /input/design.gds", flush=True)

    container = client.containers.create(
        image,
        command=command,
        working_dir="/workspace",
        network_disabled=True,
        mem_limit=mem_limit,
        environment={
            "COLUMNS": "200",
            "TERM": "xterm-256color",
        },
    )

    try:
        # Upload the layout to /input/design.gds and create an empty /output,
        # both via put_archive("/", ...) — no bind mounts, just like production.
        container.put_archive("/", create_tar_archive(input_layout, "input/design.gds"))
        container.put_archive("/", create_directory_tar("output"))

        print("[verify] starting container…", flush=True)
        container.start()

        # Stream the precheck log live so CI shows progress and failures.
        for chunk in container.logs(stream=True, follow=True):
            sys.stdout.buffer.write(chunk)
            sys.stdout.flush()

        exit_code = container.wait()["StatusCode"]
        print(f"\n[verify] container exited with status {exit_code}")

        output_ok = fetch_output_gds(container, output_path) > 0
        if exit_code == 0 and output_ok:
            print("[verify] PASS: precheck completed and /output/design.gds was written")
            return 0

        if exit_code == 0 and not output_ok:
            print("[verify] FAIL: precheck exited 0 but no /output/design.gds was produced")
            return 1

        print("[verify] FAIL: precheck reported a failure (non-zero exit)")
        return exit_code
    finally:
        container.remove(force=True)


def fetch_output_gds(container, dest: Optional[Path]) -> int:
    """Return the size of /output/design.gds, copying it to ``dest`` if given.

    Returns 0 (and copies nothing) if the file does not exist in the container.
    """
    try:
        bits, stat = container.get_archive("/output/design.gds")
    except docker.errors.NotFound:
        print("[verify] /output/design.gds not found in container")
        return 0

    size = stat.get("size", 0)
    print(f"[verify] /output/design.gds size: {size} bytes")

    if dest is not None and size > 0:
        # get_archive yields a tar stream; pull the single design.gds member out.
        buf = io.BytesIO()
        for chunk in bits:
            buf.write(chunk)
        buf.seek(0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            extracted = tar.extractfile(tar.getmember("design.gds"))
            with open(dest, "wb") as out:
                shutil.copyfileobj(extracted, out)
        print(f"[verify] copied output GDS to {dest} ({dest.stat().st_size} bytes)")

    return size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        required=True,
        help="Image to verify, ideally the immutable image ID (sha256:...) so a "
        "concurrent build cannot move the tag out from under the test.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path on the host to the layout to check (uploaded as /input/design.gds).",
    )
    parser.add_argument("--top", required=True, help="Top-level cell name.")
    parser.add_argument(
        "--slot",
        required=True,
        choices=["1x1", "0p5x1", "1x0p5", "0p5x0p5"],
        help="Slot size of the design.",
    )
    parser.add_argument(
        "--id",
        default="DEADBEEF",
        help="8-character die ID passed to the precheck (default: DEADBEEF).",
    )
    parser.add_argument(
        "--mem-limit",
        default="24g",
        help="Container memory limit, matching the platform (default: 24g).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="If set, copy the produced /output/design.gds to this host path "
        "(e.g. for uploading as a CI artifact).",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input layout does not exist: {args.input}")

    return run_check(
        image=args.image,
        input_layout=args.input,
        top=args.top,
        slot=args.slot,
        die_id=args.id,
        mem_limit=args.mem_limit,
        output_path=args.output,
    )


if __name__ == "__main__":
    sys.exit(main())
