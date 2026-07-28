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


class TestCatalogPacks(unittest.TestCase):
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

    def test_catalog_doctor_rejects_unsupported_schema_version(self):
        with tempfile.TemporaryDirectory() as tempdir:
            themes_dir = os.path.join(tempdir, "themes")
            prompts_dir = os.path.join(tempdir, "prompt-profiles")
            presets_dir = os.path.join(tempdir, "presets")
            user_prompts_dir = os.path.join(tempdir, "catalogs", "prompt-profiles")
            for path in (themes_dir, prompts_dir, presets_dir, user_prompts_dir):
                os.makedirs(path)

            with open(os.path.join(user_prompts_dir, "future.toml"), "w") as f:
                f.write("schema_version = 99\n")
                f.write('id = "future"\n')

            with (
                patch.object(smu, "theme_manifests_dir", return_value=themes_dir),
                patch.object(smu, "prompt_profiles_path", prompts_dir),
                patch.object(smu, "preset_profiles_path", presets_dir),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", user_prompts_dir),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu.catalog_doctor(), 1)

    def test_catalog_migrate_dry_run_and_apply_user_catalogs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            theme_catalog = os.path.join(tempdir, "catalogs", "themes")
            prompt_catalog = os.path.join(tempdir, "catalogs", "prompt-profiles")
            preset_catalog = os.path.join(tempdir, "catalogs", "presets")
            os.makedirs(prompt_catalog)
            manifest_path = os.path.join(prompt_catalog, "work.toml")
            with open(manifest_path, "w") as f:
                f.write('id = "work"\n')
                f.write('name = "Work"\n')

            with (
                patch.object(smu, "theme_catalog_path", theme_catalog),
                patch.object(smu, "prompt_catalog_path", prompt_catalog),
                patch.object(smu, "preset_catalog_path", preset_catalog),
            ):
                self.assertEqual(smu.catalog_migrate(dry_run=True), 0)
                with open(manifest_path) as f:
                    self.assertNotIn("schema_version", f.read())

                self.assertEqual(smu.catalog_migrate(dry_run=False), 0)
                with open(manifest_path) as f:
                    self.assertIn("schema_version = 1", f.read())

    def test_catalog_package_exports_user_manifest_and_adapter_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prompt_catalog = os.path.join(tempdir, "catalogs", "prompt-profiles")
            output = os.path.join(tempdir, "work-shell.smu-pack")
            os.makedirs(os.path.join(prompt_catalog, "files"))
            with open(os.path.join(prompt_catalog, "files", "work.bash"), "w") as f:
                f.write("prompt\n")
            with open(os.path.join(prompt_catalog, "work-shell.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work-shell"\n')
                f.write('name = "Work Shell"\n')
                f.write("[adapter_sources]\n")
                f.write('bash = "files/work.bash"\n')
                f.write("[adapter_targets]\n")
                f.write('bash = "~/.config/bash/prompts/work.bash"\n')

            with (
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_catalog),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu.catalog_package("work-shell", output=output), 0)

            self.assertTrue(os.path.exists(os.path.join(output, "pack.toml")))
            self.assertTrue(os.path.exists(os.path.join(output, "prompt-profiles", "work-shell.toml")))
            self.assertTrue(os.path.exists(os.path.join(output, "prompt-profiles", "files", "work.bash")))

    def test_catalog_publish_creates_registry_zip_and_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack = os.path.join(tempdir, "work.smu-pack")
            registry = os.path.join(tempdir, "registry")
            os.makedirs(os.path.join(pack, "prompt-profiles"))
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
                f.write('description = "Work prompt pack."\n')
            with open(os.path.join(pack, "prompt-profiles", "work.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')

            self.assertEqual(smu.catalog_publish(pack, registry=registry), 0)
            archive = os.path.join(registry, "packs", "work.smu-pack.zip")
            first_checksum = smu._sha256_file(archive)
            self.assertTrue(os.path.exists(archive))
            self.assertTrue(zipfile.is_zipfile(archive))
            index = smu._read_simple_toml(os.path.join(registry, "index.toml"))
            self.assertEqual(index["packs"]["work"]["name"], "Work")
            self.assertEqual(index["packs"]["work"]["description"], "Work prompt pack.")
            self.assertEqual(index["packs"]["work"]["source"], "packs/work.smu-pack.zip")
            self.assertEqual(index["packs"]["work"]["sha256"], first_checksum)
            self.assertEqual(smu._registry_index_errors("published", registry, index), [])
            self.assertEqual(smu.catalog_publish(pack, registry=registry, force=True), 0)
            self.assertEqual(smu._sha256_file(archive), first_checksum)

    def test_catalog_publish_updates_existing_registry_entry_with_force(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack = os.path.join(tempdir, "work.smu-pack")
            registry = os.path.join(tempdir, "registry")
            os.makedirs(os.path.join(pack, "prompt-profiles"))
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
            with open(os.path.join(pack, "prompt-profiles", "work.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')

            self.assertEqual(smu.catalog_publish(pack, registry=registry), 0)
            with self.assertRaises(SystemExit):
                smu.catalog_publish(pack, registry=registry)
            with open(os.path.join(pack, "prompt-profiles", "work.toml"), "a") as f:
                f.write('description = "Changed."\n')
            self.assertEqual(smu.catalog_publish(pack, registry=registry, force=True), 0)
            index = smu._read_simple_toml(os.path.join(registry, "index.toml"))
            archive = os.path.join(registry, "packs", "work.smu-pack.zip")
            self.assertEqual(index["packs"]["work"]["sha256"], smu._sha256_file(archive))

    def test_catalog_install_resolves_published_local_zip_registry_pack(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry_lock = os.path.join(tempdir, "registry.lock")
            pack = os.path.join(tempdir, "work.smu-pack")
            registry = os.path.join(tempdir, "registry")
            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(os.path.join(pack, "prompt-profiles"))
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
            with open(os.path.join(pack, "prompt-profiles", "work.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "catalog_registry_lock_path", registry_lock),
                patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu.catalog_publish(pack, registry=registry), 0)
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu.catalog_install("work"), 0)
                self.assertTrue(os.path.exists(os.path.join(prompt_target, "work.toml")))

    def test_catalog_install_dry_run_and_apply_pack(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack = os.path.join(tempdir, "work.smu-pack")
            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(os.path.join(pack, "prompt-profiles", "files"))
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
            with open(os.path.join(pack, "prompt-profiles", "work.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
            with open(os.path.join(pack, "prompt-profiles", "files", "work.bash"), "w") as f:
                f.write("prompt\n")

            with (
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu.catalog_install(pack, dry_run=True), 0)
                self.assertFalse(os.path.exists(os.path.join(prompt_target, "work.toml")))

                self.assertEqual(smu.catalog_install(pack), 0)
                self.assertTrue(os.path.exists(os.path.join(prompt_target, "work.toml")))
                self.assertTrue(os.path.exists(os.path.join(prompt_target, "files", "work.bash")))

    def test_catalog_install_rejects_unsupported_pack_schema_version(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack = os.path.join(tempdir, "future.smu-pack")
            os.makedirs(pack)
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 99\n")
                f.write('id = "future"\n')
                f.write('name = "Future"\n')

            self.assertEqual(smu.catalog_install(pack, dry_run=True), 1)

    def test_catalog_install_rejects_manifest_id_conflicts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            pack = os.path.join(tempdir, "work.smu-pack")
            builtins = os.path.join(tempdir, "builtins", "prompt-profiles")
            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(os.path.join(pack, "prompt-profiles"))
            os.makedirs(builtins)
            with open(os.path.join(pack, "pack.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write('name = "Work"\n')
            with open(os.path.join(pack, "prompt-profiles", "renamed.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "starship"\n')
                f.write('name = "Starship Override"\n')
            with open(os.path.join(builtins, "starship.toml"), "w") as f:
                f.write('id = "starship"\n')

            with (
                patch.object(smu, "theme_manifests_dir", return_value=os.path.join(tempdir, "builtins", "themes")),
                patch.object(smu, "prompt_profiles_path", builtins),
                patch.object(smu, "preset_profiles_path", os.path.join(tempdir, "builtins", "presets")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu.catalog_install(pack, dry_run=True), 1)

