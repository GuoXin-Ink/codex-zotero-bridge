#!/usr/bin/env python3
"""Run repository validation without installing third-party dependencies."""

from __future__ import annotations

import json
import pathlib
import py_compile
import shutil
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "codex-zotero-bridge"
SKILL = PLUGIN / "skills" / "manage-zotero-library"
SYSTEM_SKILLS = pathlib.Path.home() / ".codex" / "skills" / ".system"


def run(command: list[str]) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    for path in ROOT.rglob("*.json"):
        if any(part in {".git", "dist", "build"} for part in path.parts):
            continue
        json.loads(path.read_text(encoding="utf-8"))
    print("JSON validation passed")

    for path in (
        PLUGIN / "scripts" / "zotero_mcp.py",
        ROOT / "scripts" / "build_xpi.py",
        ROOT / "scripts" / "check_no_secrets.py",
        ROOT / "scripts" / "validate.py",
    ):
        py_compile.compile(str(path), doraise=True)
    print("Python syntax validation passed")

    node = shutil.which("node")
    if node:
        run([node, "--check", str(ROOT / "zotero-extension" / "bootstrap.js")])
    else:
        print("Node.js not found; JavaScript syntax check skipped")

    run([sys.executable, str(ROOT / "scripts" / "check_no_secrets.py")])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])

    plugin_validator = (
        SYSTEM_SKILLS / "plugin-creator" / "scripts" / "validate_plugin.py"
    )
    if plugin_validator.exists():
        run([sys.executable, str(plugin_validator), str(PLUGIN)])
    else:
        print("Codex plugin validator not found; skipped")

    skill_validator = (
        SYSTEM_SKILLS / "skill-creator" / "scripts" / "quick_validate.py"
    )
    if skill_validator.exists():
        run([sys.executable, str(skill_validator), str(SKILL)])
    else:
        print("Codex skill validator not found; skipped")

    print("All available validation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
