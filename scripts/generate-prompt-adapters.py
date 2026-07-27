#!/usr/bin/env python3

import argparse
import pathlib
import sys

import prompt_registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
SET_ME_UP_ROOT = ROOT.parent
PROFILES_DIR = ROOT / "prompt-profiles"
TEMPLATES_DIR = ROOT / "templates" / "prompts"


def _template_path(profile_id, shell):
    suffix = {
        "bash": "bash",
        "zsh": "zsh",
        "fish": "fish",
        "nushell": "nu",
    }[shell]
    return TEMPLATES_DIR / f"{profile_id}.{suffix}.tmpl"


def _content(profile, shell):
    return _template_path(profile["id"], shell).read_text()


def _profiles(selected):
    profiles = prompt_registry.profile_by_id(PROFILES_DIR)
    if selected:
        missing = [profile_id for profile_id in selected if profile_id not in profiles]
        if missing:
            raise SystemExit(f"Unknown prompt profile(s): {', '.join(missing)}")
        return [profiles[profile_id] for profile_id in selected]
    return [profiles[profile_id] for profile_id in sorted(profiles)]


def _adapter_entries(profile):
    paths = dict(prompt_registry.adapter_paths(SET_ME_UP_ROOT, profile))
    return [
        ("bash", paths["bash adapter"]),
        ("zsh", paths["zsh adapter"]),
        ("fish", paths["fish adapter"]),
        ("nushell", paths["nushell adapter"]),
    ]


def write_adapters(profiles):
    written = []
    for profile in profiles:
        for shell, path in _adapter_entries(profile):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_content(profile, shell))
            if shell in ("bash", "zsh"):
                path.chmod(0o755)
            written.append(path)

    for path in written:
        print(f"wrote {path}")
    print(f"Wrote {len(written)} prompt adapter file(s).")


def check_adapters(profiles):
    failed = False
    for profile in profiles:
        for shell, path in _adapter_entries(profile):
            if not path.exists():
                failed = True
                print(f"missing {shell} adapter: {path}")
                continue
            if path.read_text() != _content(profile, shell):
                failed = True
                print(f"stale {shell} adapter: {path}")

    if failed:
        raise SystemExit(1)
    print(f"Prompt adapters are current for {len(profiles)} profile(s).")


def check_templates(profiles):
    failed = False
    for profile in profiles:
        for shell in prompt_registry.REQUIRED_ADAPTERS:
            path = _template_path(profile["id"], shell)
            if not path.exists():
                failed = True
                print(f"missing {shell} template: {path}")

    if failed:
        raise SystemExit(1)
    print(f"Prompt templates exist for {len(profiles)} profile(s).")


def main():
    parser = argparse.ArgumentParser(description="Generate prompt adapters.")
    parser.add_argument("profiles", nargs="*", help="Prompt profile IDs.")
    parser.add_argument("--write", action="store_true", help="Write prompt adapters.")
    parser.add_argument("--check", action="store_true", help="Check generated adapters.")
    parser.add_argument("--check-templates", action="store_true", help="Check template coverage.")
    args = parser.parse_args()

    selected_modes = sum(1 for mode in (args.write, args.check, args.check_templates) if mode)
    if selected_modes != 1:
        raise SystemExit("Use exactly one of --write, --check, or --check-templates.")

    profiles = _profiles(args.profiles)
    if args.write:
        write_adapters(profiles)
    elif args.check:
        check_adapters(profiles)
    else:
        check_templates(profiles)


if __name__ == "__main__":
    sys.exit(main())
