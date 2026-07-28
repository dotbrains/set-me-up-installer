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


class TestProfileAdapters(unittest.TestCase):
    def test_init_commands_scaffold_user_catalog_manifests(self):
        with tempfile.TemporaryDirectory() as tempdir:
            theme_dir = os.path.join(tempdir, "catalogs", "themes")
            prompt_dir = os.path.join(tempdir, "catalogs", "prompt-profiles")
            preset_dir = os.path.join(tempdir, "catalogs", "presets")

            with (
                patch.object(smu, "theme_catalog_path", theme_dir),
                patch.object(smu, "prompt_catalog_path", prompt_dir),
                patch.object(smu, "preset_catalog_path", preset_dir),
                patch.object(smu, "current_theme", return_value="gruvbox"),
                patch.object(smu, "current_prompt", return_value="starship"),
            ):
                smu.handle_theme_command(["init", "work-theme"])
                smu.handle_prompt_command(["init", "work-prompt"])
                smu.handle_preset_command(["init", "work-preset"])

                self.assertTrue(os.path.exists(os.path.join(theme_dir, "work-theme.toml")))
                self.assertTrue(os.path.exists(os.path.join(prompt_dir, "work-prompt.toml")))
                self.assertTrue(os.path.exists(os.path.join(preset_dir, "work-preset.toml")))

                theme = smu._read_simple_toml(os.path.join(theme_dir, "work-theme.toml"))
                prompt = smu._read_simple_toml(os.path.join(prompt_dir, "work-prompt.toml"))
                preset = smu._read_simple_toml(os.path.join(preset_dir, "work-preset.toml"))
                self.assertEqual(theme["extends"], "gruvbox")
                self.assertEqual(prompt["extends"], "starship")
                self.assertEqual(preset["theme"], "gruvbox")
                self.assertEqual(preset["prompt"], "starship")

    def test_adapter_init_scaffolds_materializable_prompt_profile(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompt_dir = os.path.join(tempdir, "catalogs", "prompt-profiles")

            with patch.object(smu, "prompt_catalog_path", prompt_dir):
                smu.handle_adapter_command(["init", "work-shell"])
                manifest_path = os.path.join(prompt_dir, "work-shell.toml")
                manifest = smu._read_simple_toml(manifest_path)

                self.assertEqual(manifest["id"], "work-shell")
                self.assertEqual(manifest["engine"], "shell")
                self.assertEqual(manifest["adapters"]["bash"], "prompts/work-shell.bash")
                self.assertEqual(manifest["adapter_sources"]["bash"], "files/work-shell.bash")
                self.assertEqual(manifest["adapter_modes"]["bash"], "copy")
                self.assertTrue(os.path.exists(os.path.join(prompt_dir, "files", "work-shell.bash")))
                self.assertTrue(os.path.exists(os.path.join(prompt_dir, "files", "work-shell.nu")))

    def test_init_rejects_invalid_ids(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "themes")):
                with self.assertRaises(SystemExit):
                    smu.handle_theme_command(["init", "Bad_Theme"])

    def test_catalog_doctor_rejects_invalid_adapter_authoring(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            os.makedirs(prompts_dir)
            with open(os.path.join(prompts_dir, "bad.toml"), "w") as f:
                f.write('id = "bad"\n')
                f.write("[adapter_sources]\n")
                f.write('bash = "files/bad.bash"\n')
                f.write("[adapter_modes]\n")
                f.write('bash = "move"\n')

            with (
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "missing-prompts")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "missing-themes")),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "missing-presets")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu.catalog_doctor(), 1)

    def test_adapter_paths_include_theme_and_prompt_adapters(self):
        class FakeThemeRegistry:
            @staticmethod
            def manifests(themes_dir):
                return [{"id": "gruvbox"}]

            @staticmethod
            def adapter_paths(colorscheme_root, theme, aggregate_root=None):
                return [("starship config", pathlib.Path(colorscheme_root) / "starship.toml")]

        class FakePromptRegistry:
            @staticmethod
            def manifests(profiles_dir):
                return [{"id": "work"}]

            @staticmethod
            def adapter_paths(aggregate_root, profile):
                return [("bash adapter", pathlib.Path(aggregate_root) / "home/.config/bash/prompts/work.bash")]

        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            colorschemes = os.path.join(modules_dir, "colorschemes")
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            themes_dir = os.path.join(colorschemes, "themes")
            os.makedirs(prompts_dir)
            os.makedirs(themes_dir)
            with open(os.path.join(themes_dir, "gruvbox.toml"), "w") as f:
                f.write('id = "gruvbox"\n')
            with open(os.path.join(prompts_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')

            with (
                patch.object(smu, "module_path", modules_dir),
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "_load_theme_registry", return_value=FakeThemeRegistry),
                patch.object(smu, "_load_prompt_registry", return_value=FakePromptRegistry),
            ):
                paths = smu.adapter_paths("gruvbox", "work")
                self.assertEqual(paths[0][0:2], ("theme", "starship config"))
                self.assertEqual(paths[1][0:2], ("prompt", "bash adapter"))

    def test_adapter_doctor_checks_declared_paths(self):
        class FakeThemeRegistry:
            @staticmethod
            def manifests(themes_dir):
                return [{"id": "gruvbox"}]

            @staticmethod
            def adapter_paths(colorscheme_root, theme, aggregate_root=None):
                return [("theme adapter", pathlib.Path(colorscheme_root) / "themes/gruvbox.toml")]

        class FakePromptRegistry:
            @staticmethod
            def manifests(profiles_dir):
                return [{"id": "work"}]

            @staticmethod
            def adapter_paths(aggregate_root, profile):
                return [("prompt adapter", pathlib.Path(aggregate_root) / "home/.config/bash/prompts/work.bash")]

        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            colorschemes = os.path.join(modules_dir, "colorschemes")
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            _touch(os.path.join(colorschemes, "themes", "gruvbox.toml"))
            _touch(os.path.join(tempdir, "home/.config/bash/prompts/work.bash"))
            os.makedirs(prompts_dir)
            with open(os.path.join(prompts_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')

            with (
                patch.object(smu, "module_path", modules_dir),
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "__file__", os.path.join(tempdir, "installer", "smu.py")),
                patch.object(smu, "_load_theme_registry", return_value=FakeThemeRegistry),
                patch.object(smu, "_load_prompt_registry", return_value=FakePromptRegistry),
            ):
                self.assertEqual(smu.adapter_doctor("gruvbox", "work"), 0)

    def test_adapter_install_saves_profile_applies_theme_and_resolves_profile(self):
        with tempfile.TemporaryDirectory() as tempdir:
            profile = os.path.join(tempdir, "profile.env")

            with (
                patch.object(smu, "profile_path", profile),
                patch.object(smu, "supported_themes", return_value=("nord",)),
                patch.object(smu, "supported_prompts", return_value=("classic",)),
                patch.object(smu, "provision_module", return_value=True) as provision,
                patch.object(smu, "write_resolved_profile", return_value={}) as resolve,
            ):
                smu.handle_adapter_command(["install", "nord", "classic"])
                self.assertEqual(smu.read_profile()["SMU_THEME"], "nord")
                self.assertEqual(smu.read_profile()["SMU_PROMPT"], "classic")
                provision.assert_called_once_with("colorschemes")
                resolve.assert_called_once()

    def test_materialize_adapters_copies_declared_sources_and_tracks_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            target = os.path.join(tempdir, "target", "work.bash")
            state_dir = os.path.join(tempdir, "state")
            os.makedirs(os.path.join(prompts_dir, "files"))
            with open(os.path.join(prompts_dir, "files", "work.bash"), "w") as f:
                f.write("export PS1='work'\n")
            with open(os.path.join(prompts_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')
                f.write("[adapter_sources]\n")
                f.write('bash = "files/work.bash"\n')
                f.write("[adapter_targets]\n")
                f.write(f'bash = "{target}"\n')

            with (
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "missing-prompts")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "missing-themes")),
                patch.object(smu, "adapter_state_path", state_dir),
                patch.object(smu, "adapter_manifest_json_path", os.path.join(state_dir, "manifest.json")),
                patch.object(smu, "adapter_manifest_env_path", os.path.join(state_dir, "manifest.env")),
                patch.object(smu, "state_dir", os.path.join(tempdir, "ledger")),
                patch.object(smu, "state_ledger_path", os.path.join(tempdir, "ledger", "ledger.json")),
                patch.object(smu, "theme_manifest_by_id", return_value={}),
                patch.object(smu, "_load_theme_registry", return_value=None),
            ):
                entries = smu.materialize_adapters("missing-theme", "work")
                self.assertEqual(len(entries), 1)
                with open(target) as f:
                    self.assertEqual(f.read(), "export PS1='work'\n")
                self.assertTrue(os.path.exists(os.path.join(state_dir, "manifest.json")))
                self.assertTrue(os.path.exists(os.path.join(state_dir, "manifest.env")))

    def test_materialize_adapters_dry_run_does_not_write_targets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            target = os.path.join(tempdir, "target", "work.bash")
            os.makedirs(os.path.join(prompts_dir, "files"))
            with open(os.path.join(prompts_dir, "files", "work.bash"), "w") as f:
                f.write("prompt\n")
            with open(os.path.join(prompts_dir, "work.toml"), "w") as f:
                f.write('id = "work"\n')
                f.write("[adapter_sources]\n")
                f.write('bash = "files/work.bash"\n')
                f.write("[adapter_targets]\n")
                f.write(f'bash = "{target}"\n')

            with (
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "missing-prompts")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "missing-themes")),
                patch.object(smu, "theme_manifest_by_id", return_value={}),
                patch.object(smu, "_load_theme_registry", return_value=None),
            ):
                entries = smu.materialize_adapters("missing-theme", "work", dry_run=True)
                self.assertEqual(len(entries), 1)
                self.assertFalse(os.path.exists(target))

    def test_adapter_doctor_checks_materialized_targets_from_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manifest = os.path.join(tempdir, "manifest.json")
            with open(manifest, "w") as f:
                f.write('[{"kind": "prompt", "name": "bash", "target": "/missing"}]\n')

            with (
                patch.object(smu, "adapter_manifest_json_path", manifest),
                patch.object(smu, "supported_themes", return_value=("gruvbox",)),
                patch.object(smu, "supported_prompts", return_value=("work",)),
                patch.object(smu, "adapter_paths", return_value=[("prompt", "bash adapter", __file__)]),
                patch.object(smu, "materializable_adapters", return_value=[]),
            ):
                self.assertEqual(smu.adapter_doctor("gruvbox", "work"), 1)

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

