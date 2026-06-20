# Copyright (c) 2025 wafer.space
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///

"""Push an already-built, already-verified local image to its registry tags.

The publish workflow builds the image, loads it into the local Docker daemon,
and DRC-verifies it by its immutable image ID. This script then publishes
*that exact image*: it re-tags the verified image ID onto each registry tag
(so a concurrent build cannot have moved a tag onto a different image in the
local daemon) and pushes each tag. The registry therefore receives the
byte-for-byte image that passed verification — no rebuild, no second exporter,
no chance of publishing different bytes than were tested.

Inputs are read from the environment (the GitHub-recommended way to pass
``${{ }}`` values, avoiding shell-injection and multi-line quoting issues):

* ``IMAGE_ID``   – the verified image ID (e.g. ``sha256:...``)
* ``IMAGE_TAGS`` – newline-separated registry tags to publish
"""

import os
import subprocess
import sys


def main() -> int:
    image_id = os.environ.get("IMAGE_ID", "").strip()
    tags = [t.strip() for t in os.environ.get("IMAGE_TAGS", "").splitlines() if t.strip()]

    if not image_id:
        print("[push] IMAGE_ID is empty — nothing to publish", file=sys.stderr)
        return 1
    if not tags:
        print("[push] IMAGE_TAGS is empty — no tags to publish", file=sys.stderr)
        return 1

    print(f"[push] publishing verified image {image_id} to {len(tags)} tag(s)")
    for tag in tags:
        # Re-tag the verified image ID immediately before pushing so we publish
        # exactly what was verified, even if the tag was touched concurrently.
        print(f"[push] docker tag {image_id} {tag}", flush=True)
        subprocess.run(["docker", "tag", image_id, tag], check=True)
        print(f"[push] docker push {tag}", flush=True)
        subprocess.run(["docker", "push", tag], check=True)

    print(f"[push] published verified image {image_id} to all {len(tags)} tag(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
