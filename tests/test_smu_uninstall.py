#!/usr/bin/env python3

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


def _touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class TestUninstallModule(unittest.TestCase):
    def test_brewfile_runs_brew_bundle_cleanup_force(self):
        with patch("smu.get_module_path", return_value="/tmp/m/brewfile"), \
                patch.object(smu, "macOS", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            ok = smu.uninstall_module("homebrew", dry_run=False)

        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            "brew bundle cleanup --file brewfile --force", shell=True
        )

    def test_brewfile_dry_run_executes_nothing(self):
        with patch("smu.get_module_path", return_value="/tmp/m/brewfile"), \
                patch.object(smu, "macOS", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            ok = smu.uninstall_module("homebrew", dry_run=True)

        self.assertTrue(ok)
        # Dry-run prints the plan and runs nothing — brew is never invoked.
        mock_run.assert_not_called()

    def test_packages_runs_apt_remove_from_file(self):
        with patch("smu.get_module_path", return_value="/tmp/m/packages"), \
                patch.object(smu, "debian", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            ok = smu.uninstall_module("browsers/chrome", dry_run=False)

        self.assertTrue(ok)
        cmd = mock_run.call_args[0][0]
        self.assertIn("apt_remove_from_file packages", cmd)

    def test_packages_skips_on_non_debian(self):
        with patch("smu.get_module_path", return_value="/tmp/m/packages"), \
                patch.object(smu, "debian", False), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            ok = smu.uninstall_module("browsers/chrome", dry_run=False)

        self.assertFalse(ok)
        mock_run.assert_not_called()

    def test_script_with_sibling_uninstaller_runs_it(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "modules", "macos", "development-tools", "cursor")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "cursor.sh"))
            uninstaller = os.path.join(module_dir, "cursor.uninstall.sh")
            _touch(uninstaller, "echo gone\n")

            with patch("smu.get_module_path", return_value=os.path.join(module_dir, "cursor.sh")), \
                    patch("smu.subprocess.call", return_value=0), \
                    patch("smu.subprocess.run") as mock_run, \
                    patch("smu.os.chdir"):
                ok = smu.uninstall_module("development-tools/cursor", dry_run=False)

            self.assertTrue(ok)
            cmd = mock_run.call_args[0][0]
            self.assertIn("cursor.uninstall.sh", cmd)

    def test_script_without_sibling_skipped(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "modules", "macos", "installers")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "installers.sh"))

            with patch("smu.get_module_path", return_value=os.path.join(module_dir, "installers.sh")), \
                    patch("smu.subprocess.call", return_value=0), \
                    patch("smu.subprocess.run") as mock_run, \
                    patch("smu.os.chdir"):
                ok = smu.uninstall_module("installers", dry_run=False)

            self.assertFalse(ok)
            mock_run.assert_not_called()

    def test_returns_false_when_module_path_missing(self):
        with patch("smu.get_module_path", return_value=None):
            self.assertFalse(smu.uninstall_module("missing"))

    def test_script_with_sibling_packages_chains_both_inverses(self):
        """A debian *.sh module that ships a sibling 'packages' file should
        run BOTH the .uninstall.sh AND apt_remove_from_file packages."""
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "modules", "debian", "development-tools", "cursor")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "cursor.sh"))
            _touch(os.path.join(module_dir, "cursor.uninstall.sh"))
            _touch(os.path.join(module_dir, "packages"), 'apt "curl"\n')

            with patch("smu.get_module_path", return_value=os.path.join(module_dir, "cursor.sh")), \
                    patch.object(smu, "debian", True), \
                    patch.object(smu, "macOS", False), \
                    patch("smu.subprocess.call", return_value=0), \
                    patch("smu.subprocess.run") as mock_run, \
                    patch("smu.os.chdir"):
                ok = smu.uninstall_module("development-tools/cursor", dry_run=False)

            self.assertTrue(ok)
            self.assertEqual(mock_run.call_count, 2)
            commands = [call.args[0] for call in mock_run.call_args_list]
            # Order: per-module uninstaller first, declarative inverse second.
            self.assertIn("cursor.uninstall.sh", commands[0])
            self.assertIn("apt_remove_from_file packages", commands[1])

    def test_script_with_sibling_brewfile_chains_both_inverses_on_macos(self):
        """A macOS *.sh module with a sibling brewfile should chain
        brew bundle cleanup after the per-module uninstaller."""
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "modules", "macos", "development-tools", "xcode")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "xcode.sh"))
            _touch(os.path.join(module_dir, "xcode.uninstall.sh"))
            _touch(os.path.join(module_dir, "brewfile"), 'cask "xcode"\n')

            with patch("smu.get_module_path", return_value=os.path.join(module_dir, "xcode.sh")), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch("smu.subprocess.call", return_value=0), \
                    patch("smu.subprocess.run") as mock_run, \
                    patch("smu.os.chdir"):
                ok = smu.uninstall_module("development-tools/xcode", dry_run=False)

            self.assertTrue(ok)
            self.assertEqual(mock_run.call_count, 2)
            commands = [call.args[0] for call in mock_run.call_args_list]
            self.assertIn("xcode.uninstall.sh", commands[0])
            self.assertIn("brew bundle cleanup --file brewfile --force", commands[1])


class TestUninstallModulesBatch(unittest.TestCase):
    def test_dry_run_skips_confirmation_and_executes_nothing_destructive(self):
        with patch("smu.get_module_path", return_value="/tmp/m/brewfile"), \
                patch.object(smu, "macOS", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.uninstall_modules_batch(["ai/chatgpt"], dry_run=True, no_confirm=False)

        self.assertIn("Dry run", buf.getvalue())
        # Dry-run never invokes the destructive command.
        mock_run.assert_not_called()

    def test_yes_flag_skips_confirmation_prompt(self):
        with patch("smu.get_module_path", return_value="/tmp/m/brewfile"), \
                patch.object(smu, "macOS", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"), \
                patch("builtins.input") as mock_input:
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.uninstall_modules_batch(["ai/chatgpt"], dry_run=False, no_confirm=True)

        mock_input.assert_not_called()
        mock_run.assert_called_once()

    def test_no_at_prompt_aborts(self):
        with patch("smu.get_module_path", return_value="/tmp/m/brewfile"), \
                patch.object(smu, "macOS", True), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run, \
                patch("smu.os.chdir"), \
                patch("builtins.input", return_value="n"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.uninstall_modules_batch(["ai/chatgpt"], dry_run=False, no_confirm=False)

        mock_run.assert_not_called()
        self.assertIn("Aborted", buf.getvalue())

    def test_unsupported_modules_listed_and_remaining_skipped(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "modules", "macos", "installers")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "installers.sh"))

            with patch("smu.get_module_path", return_value=os.path.join(module_dir, "installers.sh")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    smu.uninstall_modules_batch(["installers"], dry_run=False, no_confirm=True)

        out = buf.getvalue()
        self.assertIn("Cannot auto-uninstall", out)
        self.assertIn("installers", out)
        self.assertIn("Nothing to uninstall", out)


if __name__ == "__main__":
    unittest.main()
