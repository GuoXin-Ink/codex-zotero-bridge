#!/usr/bin/env python3
"""Reject common secret and private-data mistakes before publication."""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}
SKIP_PARTS = {".git", "dist", "build", "__pycache__", "tests"}
FORBIDDEN = [
    (
        re.compile(r"""DEFAULT_TOKEN\s*[:=]\s*["'][^"']+["']"""),
        "hard-coded default token",
    ),
    (
        re.compile(r"""(?:queryToken|searchParams\.get\(["']token["']\))"""),
        "query-string token authentication",
    ),
    (
        re.compile(r"""[A-Za-z]:[\\/](?:Users|Documents)[\\/]"""),
        "Windows user path",
    ),
    (
        re.compile(r"""/mnt/[a-z]/(?:Users|home)/""", re.IGNORECASE),
        "mounted private user path",
    ),
    (
        re.compile(r"""-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"""),
        "private key",
    ),
]


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern, label in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {label}")

    if findings:
        print("Potential publication blockers:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Secret/private-data scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
