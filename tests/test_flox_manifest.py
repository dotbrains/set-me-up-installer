#!/usr/bin/env python3

import json
import os
import unittest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FLOX_DIR = os.path.join(REPO_ROOT, ".flox")
MANIFEST_PATH = os.path.join(FLOX_DIR, "env", "manifest.toml")
ENV_JSON_PATH = os.path.join(FLOX_DIR, "env.json")

# Packages the CI lint and test jobs depend on. Keep in sync with
# .github/workflows/tests.yml so the smoke job and the local activate
# produce the same environment.
REQUIRED_PACKAGES = {
    "bash",
    "python3",
    "shellcheck",
    "nodejs",
    "git",
}

REQUIRED_SYSTEMS = {
    "aarch64-darwin",
    "x86_64-darwin",
    "aarch64-linux",
    "x86_64-linux",
}


class TestFloxManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MANIFEST_PATH, "rb") as f:
            cls.manifest = tomllib.load(f)
        with open(ENV_JSON_PATH) as f:
            cls.env_json = json.load(f)

    def test_manifest_version_is_one(self):
        self.assertEqual(self.manifest.get("version"), 1)

    def test_install_section_contains_required_packages(self):
        install = self.manifest.get("install", {})
        missing = REQUIRED_PACKAGES - set(install.keys())
        self.assertFalse(
            missing,
            f"Manifest is missing required CI packages: {sorted(missing)}",
        )

    def test_install_entries_declare_pkg_path(self):
        install = self.manifest.get("install", {})
        for name in REQUIRED_PACKAGES:
            with self.subTest(package=name):
                entry = install.get(name, {})
                self.assertIsInstance(entry, dict)
                self.assertIn(
                    "pkg-path",
                    entry,
                    f"{name} entry must declare pkg-path",
                )
                self.assertTrue(
                    entry["pkg-path"],
                    f"{name} pkg-path must be non-empty",
                )

    def test_systems_covers_macos_and_linux(self):
        systems = set(self.manifest.get("options", {}).get("systems", []))
        missing = REQUIRED_SYSTEMS - systems
        self.assertFalse(
            missing,
            f"Manifest must support all four systems; missing: {sorted(missing)}",
        )

    def test_on_activate_bootstraps_pytest_venv(self):
        hook = self.manifest.get("hook", {}).get("on-activate", "")
        self.assertIn("python3 -m venv", hook)
        self.assertIn("pytest", hook)
        self.assertIn("FLOX_ENV_CACHE", hook)

    def test_on_activate_exports_venv_path(self):
        # PATH export must live in on-activate (not [profile]) so that
        # `flox activate -- <cmd>` in CI sees the venv's pytest.
        hook = self.manifest.get("hook", {}).get("on-activate", "")
        self.assertIn("FLOX_ENV_CACHE/venv/bin", hook)
        self.assertIn("export PATH", hook)

    def test_blueprint_vars_match_ci_defaults(self):
        # CI workflow exports SMU_BLUEPRINT=owner/repo and
        # SMU_BLUEPRINT_BRANCH=main; the manifest seeds the same defaults
        # so `flox activate && pytest` works locally with no extra setup.
        vars_section = self.manifest.get("vars", {})
        self.assertEqual(vars_section.get("SMU_BLUEPRINT"), "owner/repo")
        self.assertEqual(vars_section.get("SMU_BLUEPRINT_BRANCH"), "main")

    def test_env_json_well_formed(self):
        self.assertEqual(self.env_json.get("version"), 1)
        self.assertEqual(self.env_json.get("name"), "set-me-up-installer")


if __name__ == "__main__":
    unittest.main()
