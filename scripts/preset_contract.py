#!/usr/bin/env python3

import argparse
import pathlib
import sys

import preset_registry
import prompt_registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
PRESETS_DIR = ROOT / "presets"
PROFILES_DIR = ROOT / "prompt-profiles"
COLORSCHEME_THEMES_DIR = ROOT.parent / "modules" / "colorschemes" / "themes"
FALLBACK_THEMES = (
    "gruvbox",
    "nord",
    "catppuccin",
    "tokyo-night",
    "rose-pine",
    "dracula",
    "everforest",
    "solarized",
    "kanagawa",
)


def _supported_themes():
    if COLORSCHEME_THEMES_DIR.is_dir():
        themes = [
            preset_registry.read_manifest(path).get("id")
            for path in sorted(COLORSCHEME_THEMES_DIR.glob("*.toml"))
        ]
        themes = [theme for theme in themes if theme]
        if themes:
            return tuple(themes)
    return FALLBACK_THEMES


def main():
    parser = argparse.ArgumentParser(description="Validate set-me-up presets.")
    parser.add_argument("presets", nargs="*", help="Preset IDs to validate.")
    args = parser.parse_args()

    presets = preset_registry.preset_by_id(PRESETS_DIR)
    prompts = tuple(prompt_registry.profile_by_id(PROFILES_DIR).keys())
    themes = _supported_themes()
    selected = args.presets or sorted(presets)
    failed = False

    for preset_id in selected:
        preset = presets.get(preset_id)
        if not preset:
            print(f"FAIL unknown preset: {preset_id}")
            failed = True
            continue

        errors = preset_registry.validate_preset(preset, themes, prompts)
        if errors:
            print(f"FAIL {preset_id}")
            failed = True
            for error in errors:
                print(f"  {error}")
        else:
            print(f"OK   {preset_id}")

    if failed:
        return 1
    print(f"Validated {len(selected)} preset(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
