#!/usr/bin/env python3

"""Shared preset manifest contract helpers."""

import pathlib
import re


def _parse_value(value):
    return value.strip().strip('"').strip("'")


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


def manifests(presets_dir):
    return [
        read_manifest(path)
        for path in sorted(pathlib.Path(presets_dir).glob("*.toml"))
    ]


def preset_by_id(presets_dir):
    return {
        preset["id"]: preset
        for preset in manifests(presets_dir)
        if preset.get("id")
    }


def validate_preset(preset, supported_themes, supported_prompts):
    errors = []
    preset_id = preset.get("id", "<unknown>")

    for key in ("id", "name", "description", "theme", "prompt"):
        if key not in preset:
            errors.append(f"{preset_id}: missing {key}")

    if preset.get("id") and not re.match(r"^[a-z0-9][a-z0-9-]*$", preset["id"]):
        errors.append(f"{preset_id}: id must be kebab-case")

    if preset.get("theme") not in supported_themes:
        errors.append(f"{preset_id}: unknown theme {preset.get('theme')}")

    if preset.get("prompt") not in supported_prompts:
        errors.append(f"{preset_id}: unknown prompt {preset.get('prompt')}")

    return errors
