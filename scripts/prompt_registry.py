#!/usr/bin/env python3

"""Shared prompt profile manifest and adapter contract helpers."""

import pathlib
import re


VALID_ENGINES = ("starship", "shell")
REQUIRED_ADAPTERS = ("bash", "zsh", "fish", "nushell")


def _parse_value(value):
    value = value.strip().strip('"').strip("'")
    if value == "true":
        return True
    if value == "false":
        return False
    return value


def read_manifest(path):
    data = {}
    current_section = None

    for raw_line in pathlib.Path(path).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.match(r"^\[([A-Za-z0-9_-]+)\]$", line)
        if section_match:
            current_section = section_match.group(1)
            data.setdefault(current_section, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _parse_value(value)
        if current_section:
            data[current_section][key] = value
        else:
            data[key] = value

    return data


def manifests(profiles_dir):
    return [
        read_manifest(path)
        for path in sorted(pathlib.Path(profiles_dir).glob("*.toml"))
    ]


def profile_by_id(profiles_dir):
    return {
        profile["id"]: profile
        for profile in manifests(profiles_dir)
        if profile.get("id")
    }


def validate_profile(profile):
    errors = []
    profile_id = profile.get("id", "<unknown>")

    for key in ("id", "name", "description", "engine", "theme_aware"):
        if key not in profile:
            errors.append(f"{profile_id}: missing {key}")

    if profile.get("id") and not re.match(r"^[a-z0-9][a-z0-9-]*$", profile["id"]):
        errors.append(f"{profile_id}: id must be kebab-case")

    if profile.get("engine") not in VALID_ENGINES:
        errors.append(f"{profile_id}: engine must be one of {', '.join(VALID_ENGINES)}")

    if not isinstance(profile.get("theme_aware"), bool):
        errors.append(f"{profile_id}: theme_aware must be boolean")

    adapters = profile.get("adapters", {})
    for shell in REQUIRED_ADAPTERS:
        if not adapters.get(shell):
            errors.append(f"{profile_id}: missing [adapters].{shell}")

    if profile.get("engine") == "starship" and "starship" not in profile:
        errors.append(f"{profile_id}: missing [starship]")
    if profile.get("engine") == "shell" and "shell" not in profile:
        errors.append(f"{profile_id}: missing [shell]")

    return errors


def adapter_paths(aggregate_root, profile):
    aggregate_root = pathlib.Path(aggregate_root)
    adapters = profile.get("adapters", {})
    roots = {
        "bash": aggregate_root / "home" / ".config" / "bash",
        "zsh": aggregate_root / "home" / ".config" / "zsh",
        "fish": aggregate_root / "home" / ".config" / "fish",
        "nushell": aggregate_root / "home" / ".config" / "nushell",
    }

    return [
        (f"{shell} adapter", roots[shell] / adapters[shell])
        for shell in REQUIRED_ADAPTERS
        if adapters.get(shell)
    ]
