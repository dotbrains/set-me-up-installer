#!/usr/bin/env python3

"""Shared prompt profile manifest and adapter contract helpers."""

import pathlib

import smu_contract


VALID_ENGINES = ("starship", "shell")
REQUIRED_ADAPTERS = ("bash", "zsh", "fish", "nushell")


def read_manifest(path):
    return smu_contract.read_manifest(path)


def manifests(profiles_dir):
    return smu_contract.manifests(profiles_dir)


def profile_by_id(profiles_dir):
    return {
        profile["id"]: profile
        for profile in manifests(profiles_dir)
        if profile.get("id")
    }


def validate_profile(profile):
    errors = []
    profile_id = profile.get("id", "<unknown>")
    errors.extend(
        error.removeprefix("prompts: ")
        for error in smu_contract.schema_version_errors("prompts", [profile])
    )

    for key in ("id", "name", "description", "engine", "theme_aware"):
        if key not in profile:
            errors.append(f"{profile_id}: missing {key}")

    if profile.get("id") and not smu_contract.valid_id(profile["id"]):
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
