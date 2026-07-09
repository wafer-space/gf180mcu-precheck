#!/usr/bin/env python3
"""Add missing gf180mcu-precheck.pdk_version labels to published GHCR images.

One-shot maintenance tool for the June 2026 PDK_TAG removal incident: images
built after the Makefile switched from PDK_TAG to PDK_COMMIT were published
without any resolvable PDK version, which breaks platform.wafer.space's
revision-metadata fetch (it shows raw sha256 digests instead of versions).

For every tag in the repository this script:
1. Resolves the tag to its manifest (index or single manifest).
2. Reads the amd64 image config labels.
3. Skips images that already have the label, or whose Makefile at the image's
   git revision still has PDK_TAG (the platform resolves those already).
4. For the rest, resolves PDK_COMMIT (from the Makefile at the image's
   revision) to open_pdks' VERSION at that commit.
5. In apply mode, publishes a mutated config/manifest/index with the
   gf180mcu-precheck.pdk_version and .pdk_commit labels added, and repoints
   every tag that referenced the old digest. Attestation entries
   (unknown/unknown platform) are dropped from mutated indexes since their
   subject digest no longer exists after mutation.

Environment:
    GHCR_TOKEN  - token with read/write access to the package (required)
    DRY_RUN     - "true" (default) to only print the plan, "false" to apply

Layers are untouched: only the config blob (labels) changes, so the mutated
images are functionally byte-identical at runtime.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "wafer-space/gf180mcu-precheck"
REGISTRY = "https://ghcr.io"
BASE = f"{REGISTRY}/v2/{REPO}"

LABEL_VERSION = "gf180mcu-precheck.pdk_version"
LABEL_COMMIT = "gf180mcu-precheck.pdk_commit"

ACCEPT_MANIFEST = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)

MAKEFILE_URL = f"https://raw.githubusercontent.com/{REPO}/{{rev}}/Makefile"
OPEN_PDKS_VERSION_URL = (
    "https://raw.githubusercontent.com/efabless/open_pdks/{commit}/VERSION"
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def get_registry_token(github_token: str, *, push: bool) -> str:
    """Exchange a GitHub token for a GHCR registry bearer token."""
    scope = f"repository:{REPO}:pull" + (",push" if push else "")
    url = f"{REGISTRY}/token?service=ghcr.io&scope={urllib.parse.quote(scope)}"
    basic = base64.b64encode(f"x:{github_token}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read())["token"]


def registry_request(
    token: str,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str | None = None,
    accept: str | None = None,
):
    headers = {"Authorization": f"Bearer {token}"}
    if accept:
        headers["Accept"] = accept
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=60)  # noqa: S310


def list_all_tags(token: str) -> list[str]:
    tags: list[str] = []
    url = f"{BASE}/tags/list?n=1000"
    while url:
        with registry_request(token, url) as resp:
            tags.extend(json.loads(resp.read()).get("tags", []))
            link = resp.headers.get("Link", "")
        match = re.search(r"<([^>]+)>", link) if 'rel="next"' in link else None
        url = urllib.parse.urljoin(BASE + "/", match.group(1)) if match else None
    return tags


def head_digest(token: str, ref: str) -> str:
    with registry_request(
        token, f"{BASE}/manifests/{ref}", method="HEAD", accept=ACCEPT_MANIFEST
    ) as resp:
        return resp.headers["Docker-Content-Digest"]


def get_json(token: str, url: str, accept: str | None = None) -> dict:
    with registry_request(token, url, accept=accept) as resp:
        return json.loads(resp.read())


def fetch_text(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            return resp.read().decode("utf-8")
    except urllib.error.URLError:
        return None


def serialize(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def blob_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def upload_blob(token: str, data: bytes) -> str:
    """Upload a blob and return its digest."""
    digest = blob_digest(data)
    with registry_request(
        token, f"{BASE}/blobs/uploads/", method="POST", data=b""
    ) as resp:
        location = resp.headers["Location"]
    location = urllib.parse.urljoin(REGISTRY, location)
    sep = "&" if "?" in location else "?"
    with registry_request(
        token,
        f"{location}{sep}digest={urllib.parse.quote(digest)}",
        method="PUT",
        data=data,
        content_type="application/octet-stream",
    ) as resp:
        if resp.status not in (201, 202):
            fail(f"Blob upload failed with HTTP {resp.status}")
    return digest


def put_manifest(token: str, ref: str, data: bytes, media_type: str) -> str:
    with registry_request(
        token,
        f"{BASE}/manifests/{ref}",
        method="PUT",
        data=data,
        content_type=media_type,
    ) as resp:
        if resp.status != 201:
            fail(f"Manifest PUT to {ref} failed with HTTP {resp.status}")
    return blob_digest(data)


def resolve_pdk_for_revision(revision: str) -> tuple[str, str] | str:
    """Return (pdk_commit, pdk_version) or a skip-reason string."""
    makefile = fetch_text(MAKEFILE_URL.format(rev=revision))
    if makefile is None:
        return "cannot fetch Makefile at image revision"
    if re.search(r"^PDK_TAG\s*\??=", makefile, re.MULTILINE):
        return "pre-June image: platform resolves PDK_TAG from Makefile already"
    commit_match = re.search(
        r"^PDK_COMMIT\s*\??=\s*([0-9a-f]{40})\s*$", makefile, re.MULTILINE
    )
    if not commit_match:
        return "Makefile has neither PDK_TAG nor PDK_COMMIT"
    commit = commit_match.group(1)
    version = fetch_text(OPEN_PDKS_VERSION_URL.format(commit=commit))
    if version is None:
        return f"cannot fetch open_pdks VERSION for {commit[:12]}"
    version = version.strip()
    if not re.fullmatch(r"\d+\.\d+(\.\d+)*", version):
        return f"open_pdks VERSION content not a version: {version!r}"
    return (commit, version)


def child_image_manifests(index: dict) -> list[dict]:
    """Entries with a real platform (skips unknown/unknown attestations)."""
    return [
        m
        for m in index.get("manifests", [])
        if m.get("platform", {}).get("os", "unknown") != "unknown"
    ]


def mutate_image(
    token: str, manifest: dict, labels_to_add: dict[str, str]
) -> tuple[bytes, str]:
    """Add labels to a single image manifest's config; upload new blobs.

    Returns (new_manifest_bytes, media_type).
    """
    config_desc = manifest["config"]
    config = get_json(token, f"{BASE}/blobs/{config_desc['digest']}")
    labels = config.setdefault("config", {}).setdefault("Labels", {}) or {}
    labels.update(labels_to_add)
    config["config"]["Labels"] = labels

    config_bytes = serialize(config)
    new_config_digest = upload_blob(token, config_bytes)

    manifest["config"] = {
        **config_desc,
        "digest": new_config_digest,
        "size": len(config_bytes),
    }
    media_type = manifest.get("mediaType", "application/vnd.oci.image.manifest.v1+json")
    manifest_bytes = serialize(manifest)
    put_manifest(token, blob_digest(manifest_bytes), manifest_bytes, media_type)
    return manifest_bytes, media_type


def process_digest(
    token: str,
    digest: str,
    tags: list[str],
    labels_to_add: dict[str, str],
    *,
    apply: bool,
) -> None:
    """Mutate one (index or manifest) digest and repoint its tags."""
    top = get_json(token, f"{BASE}/manifests/{digest}", accept=ACCEPT_MANIFEST)

    if "manifests" in top:  # index / manifest list
        children = child_image_manifests(top)
        dropped = len(top["manifests"]) - len(children)
        new_entries = []
        for entry in children:
            child = get_json(
                token, f"{BASE}/manifests/{entry['digest']}", accept=ACCEPT_MANIFEST
            )
            if not apply:
                continue
            child_bytes, _ = mutate_image(token, child, labels_to_add)
            new_entries.append(
                {**entry, "digest": blob_digest(child_bytes), "size": len(child_bytes)}
            )
        if not apply:
            print(f"    would mutate {len(children)} child manifest(s), "
                  f"drop {dropped} attestation entrie(s)")
            return
        top["manifests"] = new_entries
        if dropped:
            print(f"    dropped {dropped} attestation entrie(s) from index")
        top_bytes = serialize(top)
        media_type = top.get("mediaType", "application/vnd.oci.image.index.v1+json")
    else:  # single manifest
        if not apply:
            print("    would mutate 1 single-platform manifest")
            return
        top_bytes, media_type = mutate_image(token, top, labels_to_add)

    for tag in tags:
        put_manifest(token, tag, top_bytes, media_type)
        print(f"    pushed tag {tag} -> {blob_digest(top_bytes)[:26]}...")


def verify_tag(token: str, tag: str) -> str | None:
    """Return the pdk_version label readable via the tag, or None."""
    digest = head_digest(token, tag)
    top = get_json(token, f"{BASE}/manifests/{digest}", accept=ACCEPT_MANIFEST)
    manifest = top
    if "manifests" in top:
        children = child_image_manifests(top)
        if not children:
            return None
        manifest = get_json(
            token, f"{BASE}/manifests/{children[0]['digest']}", accept=ACCEPT_MANIFEST
        )
    config = get_json(token, f"{BASE}/blobs/{manifest['config']['digest']}")
    return (config.get("config", {}).get("Labels") or {}).get(LABEL_VERSION)


def main() -> None:
    github_token = os.environ.get("GHCR_TOKEN", "")
    if not github_token:
        fail("GHCR_TOKEN environment variable is required")
    apply = os.environ.get("DRY_RUN", "true").lower() == "false"
    print(f"Mode: {'APPLY' if apply else 'DRY RUN'}\n")

    token = get_registry_token(github_token, push=apply)

    tags = list_all_tags(token)
    print(f"Found {len(tags)} tags")

    digest_tags: dict[str, list[str]] = {}
    for tag in tags:
        digest_tags.setdefault(head_digest(token, tag), []).append(tag)
    print(f"Found {len(digest_tags)} unique digests\n")

    todo: list[tuple[str, list[str], dict[str, str]]] = []
    for digest, dtags in sorted(digest_tags.items(), key=lambda kv: kv[1][0]):
        top = get_json(token, f"{BASE}/manifests/{digest}", accept=ACCEPT_MANIFEST)
        manifest = top
        if "manifests" in top:
            children = child_image_manifests(top)
            if not children:
                print(f"SKIP {digest[:22]}... {dtags}: no platform manifests")
                continue
            manifest = get_json(
                token,
                f"{BASE}/manifests/{children[0]['digest']}",
                accept=ACCEPT_MANIFEST,
            )
        config = get_json(token, f"{BASE}/blobs/{manifest['config']['digest']}")
        labels = config.get("config", {}).get("Labels") or {}

        if labels.get(LABEL_VERSION):
            print(f"SKIP {digest[:22]}... {dtags}: already labeled "
                  f"({labels[LABEL_VERSION]})")
            continue
        revision = labels.get("org.opencontainers.image.revision", "")
        if not revision:
            print(f"SKIP {digest[:22]}... {dtags}: no revision label")
            continue
        resolved = resolve_pdk_for_revision(revision)
        if isinstance(resolved, str):
            print(f"SKIP {digest[:22]}... {dtags}: {resolved}")
            continue
        commit, version = resolved
        todo.append(
            (digest, dtags, {LABEL_VERSION: version, LABEL_COMMIT: commit})
        )
        print(f"FIX  {digest[:22]}... {dtags}: pdk_version={version} "
              f"pdk_commit={commit[:12]}")

    print(f"\n{len(todo)} digest(s) to fix")
    for digest, dtags, labels_to_add in todo:
        print(f"\nProcessing {digest[:22]}... tags={dtags}")
        process_digest(token, digest, dtags, labels_to_add, apply=apply)

    if apply and todo:
        print("\nVerifying mutated tags:")
        bad = 0
        for _, dtags, labels_to_add in todo:
            for tag in dtags:
                got = verify_tag(token, tag)
                ok = got == labels_to_add[LABEL_VERSION]
                bad += 0 if ok else 1
                print(f"  {'OK ' if ok else 'BAD'} {tag}: {LABEL_VERSION}={got}")
        if bad:
            fail(f"{bad} tag(s) failed post-mutation verification")
        print("\nAll mutated tags verified.")


if __name__ == "__main__":
    main()
