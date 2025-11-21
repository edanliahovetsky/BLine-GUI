#!/usr/bin/env python3
"""Helper to run PySide6 deployment with the repo spec."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _preferred_cli_args(executable: str, spec_file: Path) -> list[str]:
    """Return the correct arguments for the installed pyside6-deploy."""
    help_cmd = [executable, "--help"]
    help_proc = subprocess.run(
        help_cmd,
        capture_output=True,
        text=True,
    )
    help_text = (help_proc.stdout or "") + (help_proc.stderr or "")
    normalized = help_text.lower()
    if "--config-file" in normalized or "-c config_file" in normalized:
        return ["-c", str(spec_file)]
    return ["--spec", str(spec_file)]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    spec_file = repo_root / "pysidedeploy.spec"
    build_dir = repo_root / "build"
    build_dir.mkdir(exist_ok=True)

    if not spec_file.exists():
        print(f"[package] Spec file not found: {spec_file}", file=sys.stderr)
        return 1

    executable = "pyside6-deploy"
    try:
        cli_args = _preferred_cli_args(executable, spec_file)
    except FileNotFoundError:
        print(f"[package] {executable!r} not found on PATH", file=sys.stderr)
        return 1

    cmd = [executable, *cli_args]
    print(f"[package] Running: {' '.join(cmd)}")
    try:
        # Provide input="y\n" to automatically answer "Proceed? [Y/n]" prompts
        # which occur when not running in a virtual environment.
        subprocess.run(cmd, check=True, cwd=repo_root, input="y\n", text=True)
    except FileNotFoundError:
        print(f"[package] {executable!r} not found on PATH", file=sys.stderr)
        return 1

    print(f"[package] Artifacts available under: {build_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
