#!/usr/bin/env python3
"""Build a deterministic Zotero XPI and its update manifest."""

from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "zotero-extension"
DIST = ROOT / "dist"
RELEASE_BASE = (
    "https://github.com/GuoXin-Ink/codex-zotero-bridge/releases/download"
)
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def main() -> int:
    manifest_path = SOURCE / "manifest.json"
    bootstrap_path = SOURCE / "bootstrap.js"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest["version"]
    addon_id = manifest["applications"]["zotero"]["id"]
    minimum = manifest["applications"]["zotero"]["strict_min_version"]
    maximum = manifest["applications"]["zotero"]["strict_max_version"]

    DIST.mkdir(parents=True, exist_ok=True)
    output = DIST / f"codex-zotero-bridge-{version}.xpi"

    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source_path, archive_name in (
            (manifest_path, "manifest.json"),
            (bootstrap_path, "bootstrap.js"),
        ):
            info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source_path.read_bytes(), compresslevel=9)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    update_manifest = {
        "addons": {
            addon_id: {
                "updates": [
                    {
                        "version": version,
                        "update_link": (
                            f"{RELEASE_BASE}/v{version}/{output.name}"
                        ),
                        "update_hash": f"sha256:{digest}",
                        "applications": {
                            "zotero": {
                                "strict_min_version": minimum,
                                "strict_max_version": maximum,
                            }
                        },
                    }
                ]
            }
        }
    }
    (ROOT / "updates.json").write_text(
        json.dumps(update_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Built {output.relative_to(ROOT)}")
    print(f"SHA-256 {digest}")
    print("Updated updates.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
