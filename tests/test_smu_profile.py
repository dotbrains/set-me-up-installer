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
                    {"SMU_THEME": "nord", "SMU_PROMPT": "classic"},
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
