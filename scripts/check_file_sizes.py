#!/usr/bin/env python3

"""Fail when tracked repository files exceed the configured line budget."""

import argparse
import json
import pathlib
import subprocess
import sys


DEFAULT_BUDGET = {
    "default_lines": 500,
    "files": {},
}

EXCLUDED_PARTS = {
    ".git",
    "build",
    "deps",
    "dist",
    "node_modules",
    "site",
    "target",
    "vendor",
}

CHECKED_SUFFIXES = {
    ".bash",
    ".fish",
    ".json",
    ".md",
    ".nu",
    ".py",
    ".sh",
    ".toml",
    ".yml",
    ".zsh",
}

CHECKED_NAMES = {
    "smu",
    "symlinks",
}


def tracked_files():
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [pathlib.Path(line) for line in output.splitlines() if line]


def should_check(path):
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.name in CHECKED_NAMES:
        return True
    return path.suffix in CHECKED_SUFFIXES


def line_count(path):
    try:
        return len(path.read_text().splitlines())
    except UnicodeDecodeError:
        return 0


def read_budget(path):
    if not path.exists():
        return DEFAULT_BUDGET
    with path.open() as f:
        budget = json.load(f)
    return {
        "default_lines": budget.get("default_lines", DEFAULT_BUDGET["default_lines"]),
        "files": budget.get("files", {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--budget-file",
        default="scripts/file-size-budgets.json",
        help="JSON budget file path",
    )
    args = parser.parse_args()
    budget = read_budget(pathlib.Path(args.budget_file))
    default_limit = int(budget["default_lines"])
    file_limits = {
        pathlib.Path(path): int(limit)
        for path, limit in budget["files"].items()
    }

    failures = []
    for path in tracked_files():
        if not should_check(path) or not path.exists():
            continue
        actual = line_count(path)
        limit = file_limits.get(path, default_limit)
        if actual > limit:
            failures.append(f"{path}: {actual} lines > budget {limit}")

    if failures:
        for failure in failures:
            print(failure)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
