#!/usr/bin/env python3

import json
import os
import pathlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import smu


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w"):
        pass


class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size == -1:
            data = self.data
            self.data = b""
            return data
        data = self.data[:size]
        self.data = self.data[size:]
        return data


class TestProfile(unittest.TestCase):
    def test_writes_and_reads_profile(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")

            with patch.object(smu, "profile_path", profile):
                smu.write_profile({
                    "SMU_THEME": "nord",
                    "SMU_PROMPT": "classic",
                })

                self.assertEqual(
                    smu.read_profile(),
                    {"SMU_PRESET": "default", "SMU_THEME": "nord", "SMU_PROMPT": "classic"},
                )

    def test_set_profile_value_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")

            with patch.object(smu, "profile_path", profile):
                with self.assertRaises(SystemExit):
                    smu.set_profile_value("SMU_THEME", "unknown", smu.SUPPORTED_THEMES)

    def test_supported_prompts_are_read_from_profile_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompt_dir = os.path.join(tempdir, "prompt-profiles")
            os.makedirs(prompt_dir)
            with open(os.path.join(prompt_dir, "lean.toml"), "w") as f:
                f.write('id = "lean"\n')
                f.write('description = "Compact prompt."\n')

            with patch.object(smu, "prompt_profiles_path", prompt_dir):
                self.assertEqual(smu.supported_prompts(), ("lean",))
                self.assertEqual(smu.prompt_profiles()[0]["description"], "Compact prompt.")

    def test_prompt_catalog_extends_builtin_profile(self):
        with tempfile.TemporaryDirectory() as tempdir:
            builtins_dir = os.path.join(tempdir, "prompt-profiles")
            catalog_dir = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(builtins_dir)
            os.makedirs(catalog_dir)
            with open(os.path.join(builtins_dir, "starship.toml"), "w") as f:
                f.write('id = "starship"\n')
                f.write('name = "Starship"\n')
                f.write('description = "Full prompt."\n')
                f.write('engine = "starship"\n')
                f.write('theme_aware = true\n')
                f.write("[starship]\n")
                f.write('config = "starship.toml"\n')
                f.write("[adapters]\n")
                f.write('bash = "prompts/starship.bash"\n')
            with open(os.path.join(catalog_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')
                f.write('extends = "starship"\n')
                f.write('name = "Work"\n')
                f.write('description = "Work prompt."\n')
                f.write("[adapters]\n")
                f.write('bash = "prompts/work.bash"\n')

            with (
                patch.object(smu, "prompt_profiles_path", builtins_dir),
                patch.object(smu, "prompt_catalog_path", catalog_dir),
            ):
                profiles = {entry["id"]: entry for entry in smu.prompt_profiles()}
                self.assertEqual(smu.supported_prompts(), ("starship", "work"))
                self.assertEqual(profiles["work"]["engine"], "starship")
                self.assertEqual(profiles["work"]["theme_aware"], True)
                self.assertEqual(profiles["work"]["adapters"]["bash"], "prompts/work.bash")

    def test_supported_presets_are_read_from_manifest_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            presets_dir = os.path.join(tempdir, "presets")
            os.makedirs(presets_dir)
            with open(os.path.join(presets_dir, "lean.toml"), "w") as f:
                f.write('id = "lean"\n')
                f.write('description = "Lean preset."\n')
                f.write('theme = "nord"\n')
                f.write('prompt = "classic"\n')

            with patch.object(smu, "preset_profiles_path", presets_dir):
                self.assertEqual(smu.supported_presets(), ("lean",))
                self.assertEqual(smu.preset_profiles()[0]["description"], "Lean preset.")

    def test_preset_catalog_extends_builtin_preset(self):
        with tempfile.TemporaryDirectory() as tempdir:
            presets_dir = os.path.join(tempdir, "presets")
            catalog_dir = os.path.join(tempdir, "catalogs", "presets")
            os.makedirs(presets_dir)
            os.makedirs(catalog_dir)
            with open(os.path.join(presets_dir, "default.toml"), "w") as f:
                f.write('id = "default"\n')
                f.write('name = "Default"\n')
                f.write('description = "Default preset."\n')
                f.write('theme = "gruvbox"\n')
                f.write('prompt = "starship"\n')
            with open(os.path.join(catalog_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')
                f.write('extends = "default"\n')
                f.write('name = "Work"\n')
                f.write('description = "Work preset."\n')
                f.write('prompt = "classic"\n')

            with (
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "preset_catalog_path", catalog_dir),
            ):
                presets = {entry["id"]: entry for entry in smu.preset_profiles()}
                self.assertEqual(smu.supported_presets(), ("default", "work"))
                self.assertEqual(presets["work"]["theme"], "gruvbox")
                self.assertEqual(presets["work"]["prompt"], "classic")

    def test_set_preset_writes_theme_and_prompt(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")
            presets_dir = os.path.join(tempdir, "presets")
            os.makedirs(presets_dir)
            with open(os.path.join(presets_dir, "nord-minimal.toml"), "w") as f:
                f.write('id = "nord-minimal"\n')
                f.write('name = "Nord Minimal"\n')
                f.write('description = "Nord and minimal Starship."\n')
                f.write('theme = "nord"\n')
                f.write('prompt = "starship-minimal"\n')

            with (
                patch.object(smu, "profile_path", profile),
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "supported_themes", return_value=("nord",)),
                patch.object(smu, "supported_prompts", return_value=("starship-minimal",)),
            ):
                smu.set_preset("nord-minimal")
                self.assertEqual(
                    smu.read_profile(),
                    {
                        "SMU_PRESET": "nord-minimal",
                        "SMU_THEME": "nord",
                        "SMU_PROMPT": "starship-minimal",
                    },
                )

    def test_current_values_honor_override_files_before_profile(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")
            theme_override = os.path.join(tempdir, "theme.toml")
            prompt_override = os.path.join(tempdir, "prompt.toml")
            preset_override = os.path.join(tempdir, "preset.toml")

            with open(profile, "w") as f:
                f.write('export SMU_PRESET="default"\n')
                f.write('export SMU_THEME="gruvbox"\n')
                f.write('export SMU_PROMPT="starship"\n')
            with open(theme_override, "w") as f:
                f.write('theme = "nord"\n')
            with open(prompt_override, "w") as f:
                f.write('id = "classic"\n')
            with open(preset_override, "w") as f:
                f.write('preset = "classic-gruvbox"\n')

            with (
                patch.object(smu, "profile_path", profile),
                patch.object(smu, "theme_override_path", theme_override),
                patch.object(smu, "prompt_override_path", prompt_override),
                patch.object(smu, "preset_override_path", preset_override),
                patch.dict(os.environ, {"SMU_THEME": "", "SMU_PROMPT": "", "SMU_PRESET": ""}, clear=False),
            ):
                os.environ.pop("SMU_THEME", None)
                os.environ.pop("SMU_PROMPT", None)
                os.environ.pop("SMU_PRESET", None)
                self.assertEqual(smu.current_theme(), "nord")
                self.assertEqual(smu.current_prompt(), "classic")
                self.assertEqual(smu.current_preset(), "classic-gruvbox")

    def test_write_resolved_profile_exports_manifest_fields(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")
            resolved = os.path.join(tempdir, "resolved.env")
            presets_dir = os.path.join(tempdir, "presets")
            themes_dir = os.path.join(tempdir, "themes")
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            os.makedirs(presets_dir)
            os.makedirs(themes_dir)
            os.makedirs(prompts_dir)

            with open(profile, "w") as f:
                f.write('export SMU_PRESET="default"\n')
                f.write('export SMU_THEME="gruvbox"\n')
                f.write('export SMU_PROMPT="starship"\n')
            with open(os.path.join(presets_dir, "default.toml"), "w") as f:
                f.write('id = "default"\n')
                f.write('name = "Default"\n')
                f.write('description = "Default preset."\n')
                f.write('theme = "gruvbox"\n')
                f.write('prompt = "starship"\n')
            with open(os.path.join(themes_dir, "gruvbox.toml"), "w") as f:
                f.write('id = "gruvbox"\n')
                f.write('name = "Gruvbox"\n')
                f.write("[nvim]\n")
                f.write('colorscheme = "gruvbox"\n')
            with open(os.path.join(prompts_dir, "starship.toml"), "w") as f:
                f.write('id = "starship"\n')
                f.write('name = "Starship"\n')
                f.write('description = "Full prompt."\n')
                f.write('engine = "starship"\n')
                f.write('theme_aware = true\n')

            with (
                patch.object(smu, "profile_path", profile),
                patch.object(smu, "resolved_profile_path", resolved),
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "theme_manifests_dir", return_value=themes_dir),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "missing-themes")),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "missing-prompts")),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "missing-presets")),
                patch.object(smu, "theme_override_path", os.path.join(tempdir, "missing-theme.toml")),
                patch.object(smu, "prompt_override_path", os.path.join(tempdir, "missing-prompt.toml")),
                patch.object(smu, "preset_override_path", os.path.join(tempdir, "missing-preset.toml")),
                patch.dict(os.environ, {}, clear=True),
            ):
                smu.write_resolved_profile()
                values = smu.read_profile_file(resolved)
                self.assertEqual(values["SMU_PRESET"], "default")
                self.assertEqual(values["SMU_THEME"], "gruvbox")
                self.assertEqual(values["SMU_PROMPT"], "starship")
                self.assertEqual(values["SMU_THEME_NAME"], "Gruvbox")
                self.assertEqual(values["SMU_THEME_NVIM_COLORSCHEME"], "gruvbox")
                self.assertEqual(values["SMU_PROMPT_ENGINE"], "starship")
                self.assertEqual(values["SMU_PROMPT_THEME_AWARE"], "true")
                self.assertEqual(smu.resolved_profile_doctor(), 0)

    def test_resolved_profile_doctor_rejects_stale_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")
            resolved = os.path.join(tempdir, "resolved.env")
            with open(profile, "w") as f:
                f.write('export SMU_PRESET="default"\n')
                f.write('export SMU_THEME="gruvbox"\n')
                f.write('export SMU_PROMPT="starship"\n')
            with open(resolved, "w") as f:
                f.write('export SMU_PRESET="default"\n')
                f.write('export SMU_THEME="nord"\n')
                f.write('export SMU_PROMPT="starship"\n')

            with (
                patch.object(smu, "profile_path", profile),
                patch.object(smu, "resolved_profile_path", resolved),
                patch.object(smu, "supported_themes", return_value=("gruvbox",)),
                patch.object(smu, "prompt_profile_by_id", return_value={"id": "starship"}),
                patch.object(smu, "preset_by_id", return_value={"id": "default"}),
                patch.object(smu, "theme_manifest_by_id", return_value={"id": "gruvbox"}),
                patch.object(smu, "theme_override_path", os.path.join(tempdir, "missing-theme.toml")),
                patch.object(smu, "prompt_override_path", os.path.join(tempdir, "missing-prompt.toml")),
                patch.object(smu, "preset_override_path", os.path.join(tempdir, "missing-preset.toml")),
                patch.dict(os.environ, {}, clear=True),
            ):
                self.assertEqual(smu.resolved_profile_doctor(), 1)

    def test_preset_doctor_validates_theme_and_prompt(self):
        with tempfile.TemporaryDirectory() as tempdir:
            presets_dir = os.path.join(tempdir, "presets")
            os.makedirs(presets_dir)
            with open(os.path.join(presets_dir, "default.toml"), "w") as f:
                f.write('id = "default"\n')
                f.write('name = "Default"\n')
                f.write('description = "Default preset."\n')
                f.write('theme = "gruvbox"\n')
                f.write('prompt = "starship"\n')

            with (
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "supported_themes", return_value=("gruvbox",)),
                patch.object(smu, "supported_prompts", return_value=("starship",)),
            ):
                self.assertEqual(smu.preset_doctor("default"), 0)

    def test_catalog_doctor_rejects_duplicate_user_ids(self):
        with tempfile.TemporaryDirectory() as tempdir:
            presets_dir = os.path.join(tempdir, "presets")
            catalog_dir = os.path.join(tempdir, "catalogs", "presets")
            os.makedirs(presets_dir)
            os.makedirs(catalog_dir)
            with open(os.path.join(catalog_dir, "one.toml"), "w") as f:
                f.write('id = "work"\n')
            with open(os.path.join(catalog_dir, "two.toml"), "w") as f:
                f.write('id = "work"\n')

            with (
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "preset_catalog_path", catalog_dir),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "missing-prompts")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "missing-themes")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu.catalog_doctor(), 1)

