#!/usr/bin/env python3

import argparse
import pathlib
import sys

import prompt_registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
SET_ME_UP_ROOT = ROOT.parent
PROFILES_DIR = ROOT / "prompt-profiles"


def main():
    parser = argparse.ArgumentParser(description="Validate prompt profile adapters.")
    parser.add_argument("profiles", nargs="*", help="Profile IDs to validate.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Only validate prompt profile manifests.",
    )
    args = parser.parse_args()

    profiles = prompt_registry.profile_by_id(PROFILES_DIR)
    selected = args.profiles or sorted(profiles)
    failed = False

    for profile_id in selected:
        profile = profiles.get(profile_id)
        if not profile:
            print(f"FAIL unknown prompt profile: {profile_id}")
            failed = True
            continue

        errors = prompt_registry.validate_profile(profile)
        missing = []
        if not args.local:
            missing = [
                (label, path)
                for label, path in prompt_registry.adapter_paths(SET_ME_UP_ROOT, profile)
                if not path.exists()
            ]

        if errors or missing:
            print(f"FAIL {profile_id}")
            failed = True
            for error in errors:
                print(f"  {error}")
            for label, path in missing:
                print(f"  missing {label}: {path}")
        else:
            print(f"OK   {profile_id}")

    if failed:
        return 1
    print(f"Validated {len(selected)} prompt profile(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
