#!/usr/bin/env python3

"""Shared preset manifest contract helpers."""

import pathlib

import smu_contract


def read_manifest(path):
    return smu_contract.read_manifest(path)


def manifests(presets_dir):
    return smu_contract.manifests(presets_dir)


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

    if preset.get("id") and not smu_contract.valid_id(preset["id"]):
        errors.append(f"{preset_id}: id must be kebab-case")

    if preset.get("theme") not in supported_themes:
        errors.append(f"{preset_id}: unknown theme {preset.get('theme')}")

    if preset.get("prompt") not in supported_prompts:
        errors.append(f"{preset_id}: unknown prompt {preset.get('prompt')}")

    return errors
