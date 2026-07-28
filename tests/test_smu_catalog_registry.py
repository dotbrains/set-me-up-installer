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


class TestCatalogRegistry(unittest.TestCase):
    def test_catalog_registry_add_lists_and_searches_local_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry = os.path.join(tempdir, "registry")
            pack = os.path.join(registry, "packs", "work.smu-pack")
            os.makedirs(pack)
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('description = "Work prompt pack."\n')
                f.write('source = "packs/work.smu-pack"\n')
                f.write(f'sha256 = "{"1" * 64}"\n')

            with patch.object(smu, "catalog_registries_path", registry_config):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu._catalog_registry_list(), 0)
                self.assertEqual(smu.catalog_search("work"), 0)
                entries = smu._catalog_registry_entries()
                self.assertEqual(entries[0]["id"], "work")
                self.assertEqual(entries[0]["source"], pack)
                self.assertEqual(entries[0]["sha256"], "1" * 64)

    def test_catalog_install_resolves_pack_id_from_registry(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry_lock = os.path.join(tempdir, "registry.lock")
            registry = os.path.join(tempdir, "registry")
            pack = os.path.join(registry, "packs", "work.smu-pack")
            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(os.path.join(pack, "prompt-profiles"))
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('source = "packs/work.smu-pack"\n')
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
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu.catalog_install("work"), 0)
                self.assertTrue(os.path.exists(os.path.join(prompt_target, "work.toml")))

    def test_catalog_registry_lock_writes_and_reports_status(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry_lock = os.path.join(tempdir, "registry.lock")
            registry = os.path.join(tempdir, "registry")
            pack = os.path.join(registry, "packs", "work.smu-pack")
            os.makedirs(pack)
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('description = "Work prompt pack."\n')
                f.write('source = "packs/work.smu-pack"\n')

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "catalog_registry_lock_path", registry_lock),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu._catalog_registry_lock(), 0)
                self.assertEqual(smu._catalog_registry_status(), 0)
                with open(registry_lock) as f:
                    lock = json.load(f)
                self.assertEqual(lock["schema_version"], 1)
                self.assertEqual(lock["registries"]["local"]["packs"]["work"]["source"], pack)
                self.assertEqual(len(lock["registries"]["local"]["index_sha256"]), 64)

    def test_catalog_registry_status_detects_index_drift(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry_lock = os.path.join(tempdir, "registry.lock")
            registry = os.path.join(tempdir, "registry")
            pack = os.path.join(registry, "packs", "work.smu-pack")
            os.makedirs(pack)
            index_path = os.path.join(registry, "index.toml")
            with open(index_path, "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('source = "packs/work.smu-pack"\n')

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "catalog_registry_lock_path", registry_lock),
                patch.object(smu, "theme_manifests_dir", return_value=os.path.join(tempdir, "themes")),
                patch.object(smu, "prompt_profiles_path", os.path.join(tempdir, "prompt-profiles")),
                patch.object(smu, "preset_profiles_path", os.path.join(tempdir, "presets")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "catalogs", "prompt-profiles")),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu._catalog_registry_lock(), 0)
                with open(index_path, "a") as f:
                    f.write('description = "Changed."\n')
                self.assertEqual(smu._catalog_registry_status(), 1)
                self.assertEqual(smu.catalog_doctor(), 1)

    def test_catalog_install_prefers_locked_pack_metadata(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry_lock = os.path.join(tempdir, "registry.lock")
            registry = os.path.join(tempdir, "registry")
            locked_pack = os.path.join(registry, "packs", "locked.smu-pack")
            live_pack = os.path.join(registry, "packs", "live.smu-pack")
            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            os.makedirs(os.path.join(locked_pack, "prompt-profiles"))
            os.makedirs(os.path.join(live_pack, "prompt-profiles"))
            index_path = os.path.join(registry, "index.toml")
            with open(index_path, "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('source = "packs/locked.smu-pack"\n')
            for pack_dir, prompt_name in ((locked_pack, "Locked"), (live_pack, "Live")):
                with open(os.path.join(pack_dir, "pack.toml"), "w") as f:
                    f.write("schema_version = 1\n")
                    f.write('id = "work"\n')
                    f.write('name = "Work"\n')
                with open(os.path.join(pack_dir, "prompt-profiles", "work.toml"), "w") as f:
                    f.write("schema_version = 1\n")
                    f.write('id = "work"\n')
                    f.write(f'name = "{prompt_name}"\n')

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "catalog_registry_lock_path", registry_lock),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu._catalog_registry_lock(), 0)
                with open(index_path, "w") as f:
                    f.write("schema_version = 1\n")
                    f.write("[packs.work]\n")
                    f.write('name = "Work"\n')
                    f.write('source = "packs/live.smu-pack"\n')
                self.assertEqual(smu.catalog_install("work"), 0)
                with open(os.path.join(prompt_target, "work.toml")) as f:
                    self.assertIn('name = "Locked"', f.read())

    def test_catalog_registry_entries_skip_invalid_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry = os.path.join(tempdir, "registry")
            os.makedirs(registry)
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 99\n")
                f.write("[packs.future]\n")
                f.write('name = "Future"\n')
                f.write('source = "missing.smu-pack"\n')

            with patch.object(smu, "catalog_registries_path", registry_config):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu._catalog_registry_entries(), [])

    def test_catalog_doctor_rejects_invalid_registry_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry = os.path.join(tempdir, "registry")
            os.makedirs(registry)
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 99\n")

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "theme_manifests_dir", return_value=os.path.join(tempdir, "themes")),
                patch.object(smu, "prompt_profiles_path", os.path.join(tempdir, "prompt-profiles")),
                patch.object(smu, "preset_profiles_path", os.path.join(tempdir, "presets")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "catalogs", "prompt-profiles")),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu.catalog_doctor(), 1)

    def test_catalog_registry_add_rejects_non_https_urls(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(smu, "catalog_registries_path", os.path.join(tempdir, "registries.toml")):
                with self.assertRaises(SystemExit):
                    smu._catalog_registry_add("remote", "http://example.com/index.toml")

    def test_catalog_search_reads_https_registry_index(self):
        index_url = "https://example.com/index.toml"
        pack_url = "https://example.com/work.smu-pack.zip"
        responses = {
            index_url: (
                "schema_version = 1\n"
                "[packs.work]\n"
                'name = "Work"\n'
                'description = "Remote work pack."\n'
                f'source = "{pack_url}"\n'
            ).encode(),
        }

        def fake_urlopen(url, timeout=30):
            return _FakeResponse(responses[url])

        with tempfile.TemporaryDirectory() as tempdir:
            with (
                patch.object(smu, "catalog_registries_path", os.path.join(tempdir, "registries.toml")),
                patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")),
                patch("smu.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                self.assertEqual(smu._catalog_registry_add("remote", index_url), 0)
                self.assertEqual(smu.catalog_search("remote"), 0)
                entries = smu._catalog_registry_entries()
                self.assertEqual(entries[0]["id"], "work")
                self.assertEqual(entries[0]["source"], pack_url)

    def test_catalog_install_resolves_https_pack_zip_from_registry(self):
        index_url = "https://example.com/index.toml"
        pack_url = "https://example.com/work.smu-pack.zip"
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, "work.smu-pack.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("pack.toml", 'schema_version = 1\nid = "work"\nname = "Work"\n')
                archive.writestr("prompt-profiles/work.toml", 'schema_version = 1\nid = "work"\nname = "Work"\n')
            with open(archive_path, "rb") as f:
                archive_bytes = f.read()
            checksum = smu.hashlib.sha256(archive_bytes).hexdigest()
            responses = {
                index_url: (
                    "schema_version = 1\n"
                    "[packs.work]\n"
                    'name = "Work"\n'
                    f'source = "{pack_url}"\n'
                    f'sha256 = "{checksum}"\n'
                ).encode(),
                pack_url: archive_bytes,
            }

            def fake_urlopen(url, timeout=30):
                return _FakeResponse(responses[url])

            prompt_target = os.path.join(tempdir, "catalogs", "prompt-profiles")
            with (
                patch.object(smu, "catalog_registries_path", os.path.join(tempdir, "registries.toml")),
                patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", prompt_target),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
                patch("smu.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                self.assertEqual(smu._catalog_registry_add("remote", index_url), 0)
                self.assertEqual(smu.catalog_install("work"), 0)
                self.assertTrue(os.path.exists(os.path.join(prompt_target, "work.toml")))

    def test_catalog_install_rejects_remote_pack_checksum_mismatch(self):
        index_url = "https://example.com/index.toml"
        pack_url = "https://example.com/work.smu-pack.zip"
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, "work.smu-pack.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("pack.toml", 'schema_version = 1\nid = "work"\nname = "Work"\n')
            with open(archive_path, "rb") as f:
                archive_bytes = f.read()
            responses = {
                index_url: (
                    "schema_version = 1\n"
                    "[packs.work]\n"
                    'name = "Work"\n'
                    f'source = "{pack_url}"\n'
                    'sha256 = "0000000000000000000000000000000000000000000000000000000000000000"\n'
                ).encode(),
                pack_url: archive_bytes,
            }

            def fake_urlopen(url, timeout=30):
                return _FakeResponse(responses[url])

            with (
                patch.object(smu, "catalog_registries_path", os.path.join(tempdir, "registries.toml")),
                patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")),
                patch("smu.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                self.assertEqual(smu._catalog_registry_add("remote", index_url), 0)
                self.assertEqual(smu.catalog_install("work"), 1)

    def test_catalog_doctor_rejects_malformed_pack_checksum(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry_config = os.path.join(tempdir, "registries.toml")
            registry = os.path.join(tempdir, "registry")
            pack = os.path.join(registry, "packs", "work.smu-pack")
            os.makedirs(pack)
            with open(os.path.join(registry, "index.toml"), "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('source = "packs/work.smu-pack"\n')
                f.write('sha256 = "bad"\n')

            with (
                patch.object(smu, "catalog_registries_path", registry_config),
                patch.object(smu, "theme_manifests_dir", return_value=os.path.join(tempdir, "themes")),
                patch.object(smu, "prompt_profiles_path", os.path.join(tempdir, "prompt-profiles")),
                patch.object(smu, "preset_profiles_path", os.path.join(tempdir, "presets")),
                patch.object(smu, "theme_catalog_path", os.path.join(tempdir, "catalogs", "themes")),
                patch.object(smu, "prompt_catalog_path", os.path.join(tempdir, "catalogs", "prompt-profiles")),
                patch.object(smu, "preset_catalog_path", os.path.join(tempdir, "catalogs", "presets")),
                patch.object(smu, "_load_theme_registry", return_value=None),
                patch.object(smu, "_load_prompt_registry", return_value=None),
                patch.object(smu, "_load_preset_registry", return_value=None),
            ):
                self.assertEqual(smu._catalog_registry_add("local", registry), 0)
                self.assertEqual(smu.catalog_doctor(), 1)

    def test_catalog_install_rejects_unsafe_remote_zip_paths(self):
        pack_url = "https://example.com/unsafe.smu-pack.zip"
        with tempfile.TemporaryDirectory() as tempdir:
            archive_path = os.path.join(tempdir, "unsafe.smu-pack.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.toml", "bad\n")
            with open(archive_path, "rb") as f:
                archive_bytes = f.read()

            def fake_urlopen(url, timeout=30):
                return _FakeResponse(archive_bytes)

            with (
                patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")),
                patch("smu.urllib.request.urlopen", side_effect=fake_urlopen),
            ):
                self.assertEqual(smu.catalog_install(pack_url, dry_run=True), 1)


