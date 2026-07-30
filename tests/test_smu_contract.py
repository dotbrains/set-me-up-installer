#!/usr/bin/env python3

import os
import tempfile
import unittest

from scripts import smu_contract


class TestSmuContract(unittest.TestCase):
    def test_read_manifest_parses_booleans_and_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "manifest.toml")
            with open(path, "w") as f:
                f.write("schema_version = 1\n")
                f.write('id = "work"\n')
                f.write("theme_aware = true\n")
                f.write("[adapters]\n")
                f.write('bash = "prompts/work.bash"\n')

            manifest = smu_contract.read_manifest(path)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["id"], "work")
            self.assertEqual(manifest["theme_aware"], True)
            self.assertEqual(manifest["adapters"]["bash"], "prompts/work.bash")

    def test_schema_version_errors_reject_unsupported_versions(self):
        errors = smu_contract.schema_version_errors("prompts", [{
            "id": "future",
            "schema_version": 99,
        }])

        self.assertEqual(
            errors,
            ["prompts: future schema_version 99 is not supported; expected 1"],
        )

    def test_migrate_manifest_adds_current_schema_version(self):
        migrated = smu_contract.migrate_manifest({
            "id": "work",
            "adapters": {"bash": "prompts/work.bash"},
        })

        self.assertEqual(migrated["schema_version"], smu_contract.SUPPORTED_SCHEMA_VERSION)
        self.assertEqual(migrated["id"], "work")
        self.assertEqual(migrated["adapters"]["bash"], "prompts/work.bash")

    def test_write_manifest_round_trips_typed_values(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "manifest.toml")
            smu_contract.write_manifest(path, {
                "schema_version": 1,
                "id": "work",
                "theme_aware": True,
                "adapters": {"bash": "prompts/work.bash"},
            })

            manifest = smu_contract.read_manifest(path)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["theme_aware"], True)
            self.assertEqual(manifest["adapters"]["bash"], "prompts/work.bash")

    def test_read_manifest_parses_dotted_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "index.toml")
            with open(path, "w") as f:
                f.write("schema_version = 1\n")
                f.write("[packs.work]\n")
                f.write('name = "Work"\n')
                f.write('source = "packs/work.smu-pack"\n')

            manifest = smu_contract.read_manifest(path)
            self.assertEqual(manifest["packs"]["work"]["name"], "Work")
            self.assertEqual(manifest["packs"]["work"]["source"], "packs/work.smu-pack")

    def test_read_manifest_parses_string_arrays(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "manifest.toml")
            with open(path, "w") as f:
                f.write('[profile.default]\n')
                f.write('modules = ["nushell", "editor/nvim"]\n')

            manifest = smu_contract.read_manifest(path)

        self.assertEqual(
            manifest["profile"]["default"]["modules"],
            ["nushell", "editor/nvim"],
        )

    def test_read_manifest_preserves_quoted_numeric_strings(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, "index.toml")
            with open(path, "w") as f:
                f.write("schema_version = 1\n")
                f.write('sha256 = "0000000000000000000000000000000000000000000000000000000000000000"\n')

            manifest = smu_contract.read_manifest(path)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["sha256"], "0" * 64)

    def test_merge_catalog_manifests_resolves_inheritance_without_overriding_builtins(self):
        builtins = [
            {"id": "default", "theme": "gruvbox", "prompt": "starship"},
        ]
        user = [
            {"id": "default", "theme": "nord"},
            {"id": "work", "extends": "default", "prompt": "classic"},
        ]

        merged = smu_contract.merge_catalog_manifests(builtins, user)
        by_id = {entry["id"]: entry for entry in merged}
        self.assertEqual(by_id["default"]["theme"], "gruvbox")
        self.assertEqual(by_id["work"]["theme"], "gruvbox")
        self.assertEqual(by_id["work"]["prompt"], "classic")

    def test_adapter_authoring_errors_validate_pairs_and_modes(self):
        errors = smu_contract.adapter_authoring_errors("prompts", [{
            "id": "Bad_Prompt",
            "adapter_sources": {"bash": "files/bash"},
            "adapter_targets": {"zsh": "~/.config/zsh/prompts/work.zsh"},
            "adapter_modes": {"bash": "move", "fish": "copy"},
        }])

        self.assertIn("prompts: Bad_Prompt id must be kebab-case", errors)
        self.assertIn("prompts: Bad_Prompt adapter bash has source without target", errors)
        self.assertIn("prompts: Bad_Prompt adapter zsh has target without source", errors)
        self.assertIn("prompts: Bad_Prompt adapter bash mode must be one of copy, symlink", errors)
        self.assertIn("prompts: Bad_Prompt adapter fish has mode without source", errors)


if __name__ == "__main__":
    unittest.main()
