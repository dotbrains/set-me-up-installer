#!/usr/bin/env python3

import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import smu


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w"):
        pass


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

    def test_prompt_doctor_checks_manifest_adapters(self):
        class FakePromptRegistry:
            @staticmethod
            def manifests(profiles_dir):
                return [{"id": "classic"}]

            @staticmethod
            def validate_profile(profile):
                return []

            @staticmethod
            def adapter_paths(aggregate_root, profile):
                return [
                    ("bash adapter", pathlib.Path(aggregate_root) / "home/.config/bash/prompts/classic.bash"),
                    ("zsh adapter", pathlib.Path(aggregate_root) / "home/.config/zsh/prompts/classic.zsh"),
                    ("fish adapter", pathlib.Path(aggregate_root) / "home/.config/fish/prompts/classic.fish"),
                    ("nushell adapter", pathlib.Path(aggregate_root) / "home/.config/nushell/prompts/classic.nu"),
                ]

        with tempfile.TemporaryDirectory() as tempdir:
            profiles_dir = os.path.join(tempdir, "installer", "prompt-profiles")
            os.makedirs(profiles_dir)
            with open(os.path.join(profiles_dir, "classic.toml"), "w") as f:
                f.write('id = "classic"\n')
                f.write('name = "Classic"\n')
                f.write('description = "Native prompt."\n')
                f.write('engine = "shell"\n')
                f.write('theme_aware = false\n')
                f.write("[shell]\n")
                f.write('mode = "native"\n')
                f.write("[adapters]\n")
                f.write('bash = "prompts/classic.bash"\n')
                f.write('zsh = "prompts/classic.zsh"\n')
                f.write('fish = "prompts/classic.fish"\n')
                f.write('nushell = "prompts/classic.nu"\n')

            for path in (
                "home/.config/bash/prompts/classic.bash",
                "home/.config/zsh/prompts/classic.zsh",
                "home/.config/fish/prompts/classic.fish",
                "home/.config/nushell/prompts/classic.nu",
            ):
                _touch(os.path.join(tempdir, path))

            with (
                patch.object(smu, "prompt_profiles_path", profiles_dir),
                patch.object(smu, "__file__", os.path.join(tempdir, "installer", "smu.py")),
                patch.object(smu, "_load_prompt_registry", return_value=FakePromptRegistry),
            ):
                self.assertEqual(smu.prompt_doctor("classic"), 0)


class TestThemeRegistry(unittest.TestCase):
    def test_supported_themes_are_read_from_manifests(self):
        with tempfile.TemporaryDirectory() as tempdir:
            colorschemes = os.path.join(tempdir, "modules", "colorschemes")
            themes = os.path.join(colorschemes, "themes")
            os.makedirs(themes)
            with open(os.path.join(themes, "oxocarbon.toml"), "w") as f:
                f.write('id = "oxocarbon"\n')
                f.write("[nvim]\n")
                f.write('colorscheme = "oxocarbon"\n')

            with patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
                self.assertEqual(smu.supported_themes(), ("oxocarbon",))

    def test_theme_doctor_uses_manifest_adapter_names(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            colorschemes = os.path.join(modules_dir, "colorschemes")
            home = os.path.join(tempdir, "home", ".config")

            for path in (
                os.path.join(colorschemes, "themes", "tokyo-night.toml"),
                os.path.join(colorschemes, "universal", "tokyo-night.sh"),
                os.path.join(colorschemes, "macos", "tokyo-night.sh"),
                os.path.join(colorschemes, "arch", "tokyo-night.sh"),
                os.path.join(colorschemes, "_shared", "configs", "starship", "tokyo-night.toml"),
                os.path.join(colorschemes, "_shared", "configs", "lazygit", "tokyo-night.yml"),
                os.path.join(home, "alacritty", "theme", "tokyo-night.toml"),
                os.path.join(home, "tmux", "themes", "tokyo-night.conf"),
                os.path.join(home, "zsh", "themes", "tokyo-night", "bat.zsh"),
                os.path.join(home, "nvim", "lua", "plugins", "ui", "tokyonight.lua"),
            ):
                _touch(path)

            with open(os.path.join(colorschemes, "themes", "tokyo-night.toml"), "w") as f:
                f.write('id = "tokyo-night"\n')
                f.write("[nvim]\n")
                f.write('colorscheme = "tokyonight"\n')

            with patch.object(smu, "module_path", modules_dir):
                self.assertEqual(smu.theme_doctor("tokyo-night"), 0)

    def test_theme_doctor_uses_shared_registry_adapter_paths(self):
        class FakeRegistry:
            @staticmethod
            def manifests(themes_dir):
                return [{"id": "nord"}]

            @staticmethod
            def adapter_paths(colorscheme_root, theme, aggregate_root=None):
                return [
                    (
                        "shared adapter",
                        pathlib.Path(colorscheme_root) / "shared" / f"{theme['id']}.txt",
                    ),
                ]

        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            colorschemes = os.path.join(modules_dir, "colorschemes")
            _touch(os.path.join(colorschemes, "themes", "nord.toml"))
            _touch(os.path.join(colorschemes, "shared", "nord.txt"))

            with open(os.path.join(colorschemes, "themes", "nord.toml"), "w") as f:
                f.write('id = "nord"\n')

            with (
                patch.object(smu, "module_path", modules_dir),
                patch.object(smu, "_load_theme_registry", return_value=FakeRegistry),
            ):
                self.assertEqual(smu.theme_doctor("nord"), 0)


class TestThemeModuleResolution(unittest.TestCase):
    def test_resolves_top_level_colorscheme_module(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _touch(os.path.join(modules_dir, "colorschemes", "colorschemes.sh"))

            with patch.object(smu, "module_path", modules_dir):
                self.assertEqual(
                    smu.get_module_path("colorschemes"),
                    os.path.join(modules_dir, "colorschemes", "colorschemes.sh"),
                )


if __name__ == "__main__":
    unittest.main()
