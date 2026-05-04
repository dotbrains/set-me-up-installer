#!/usr/bin/env python3

import os
import tempfile
import unittest
from unittest.mock import patch

import smu


class TestBrewfileModuleResolution(unittest.TestCase):
    def test_get_module_path_returns_os_specific_brewfile_when_shell_script_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            module_dir = os.path.join(modules_dir, "macos", "fonts")
            os.makedirs(module_dir, exist_ok=True)
            brewfile_path = os.path.join(module_dir, "brewfile")

            with open(brewfile_path, "w"):
                pass

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                resolved_path = smu.get_module_path("fonts")

            self.assertEqual(resolved_path, brewfile_path)

    def test_get_module_path_returns_nested_universal_brewfile_when_shell_script_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            module_dir = os.path.join(modules_dir, "universal", "python", "pip")
            os.makedirs(module_dir, exist_ok=True)
            brewfile_path = os.path.join(module_dir, "brewfile")

            with open(brewfile_path, "w"):
                pass

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", False), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                resolved_path = smu.get_module_path("python/pip")

            self.assertEqual(resolved_path, brewfile_path)


class TestBrewfileModuleProvisioning(unittest.TestCase):
    def test_provision_module_runs_brew_bundle_for_brewfile(self):
        with patch("smu.get_module_path", return_value="/tmp/module/brewfile"), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            was_provisioned = smu.provision_module("homebrew")

        self.assertTrue(was_provisioned)
        mock_run.assert_called_once_with("brew bundle install --file brewfile", shell=True)

    def test_provision_module_returns_false_when_module_path_missing(self):
        with patch("smu.get_module_path", return_value=None):
            was_provisioned = smu.provision_module("missing")

        self.assertIs(was_provisioned, False)


if __name__ == "__main__":
    unittest.main()
