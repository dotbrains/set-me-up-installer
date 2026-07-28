#!/usr/bin/env python3

"""Fail when tracked directories contain too many direct files."""

import argparse
import json
import pathlib
import subprocess
import sys
from collections import Counter


DEFAULT_BUDGET = {
    "default_files": 25,
    "directories": {},
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


def tracked_files():
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [pathlib.Path(line) for line in output.splitlines() if line]


def should_check(path):
    return not any(part in EXCLUDED_PARTS for part in path.parts)


def read_budget(path):
    if not path.exists():
        return DEFAULT_BUDGET
    with path.open() as f:
        budget = json.load(f)
    return {
        "default_files": budget.get("default_files", DEFAULT_BUDGET["default_files"]),
        "directories": budget.get("directories", {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--budget-file",
        default="scripts/flat-directory-budgets.json",
        help="JSON budget file path",
    )
    args = parser.parse_args()
    budget = read_budget(pathlib.Path(args.budget_file))
    default_limit = int(budget["default_files"])
    directory_limits = {
        pathlib.Path(path): int(settings.get("limit", default_limit))
        for path, settings in budget["directories"].items()
    }

    counts = Counter(path.parent for path in tracked_files() if should_check(path))
    failures = []
    for directory, actual in sorted(counts.items()):
        limit = directory_limits.get(directory, default_limit)
        if actual > limit:
            failures.append(f"{directory}: {actual} files > budget {limit}")

    if failures:
        for failure in failures:
            print(failure)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
