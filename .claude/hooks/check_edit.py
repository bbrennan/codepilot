#!/usr/bin/env python3
"""PostToolUse hook for Edit/Write: lint the file just changed. Exit 2 feeds the problem back to the model.

Python files get ruff (the rules pinned in pyproject.toml); codepilot/static/app.js gets `node --check`.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def check(path):
    if path.suffix == ".py":
        ruff = [shutil.which("ruff")] if shutil.which("ruff") else ["uvx", "ruff"]
        return subprocess.run([*ruff, "check", "--no-cache", str(path)], cwd=path.parent, capture_output=True,
                              text=True, timeout=120)
    if path.name == "app.js" and shutil.which("node"):
        return subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=60)
    return None


def main():
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path")
    if not file_path or not Path(file_path).is_file():
        return 0
    try:
        result = check(Path(file_path))
    except (OSError, subprocess.SubprocessError):
        return 0  # a missing tool must not block work; CI is the backstop
    if result and result.returncode != 0:
        print(f"{file_path} failed its check:\n{result.stdout}{result.stderr}".strip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
