#!/usr/bin/env python3

import os
import tempfile
import unittest
from unittest.mock import patch

import smu


def _touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class TestPackagesEntryParsing(unittest.TestCase):
    def test_skips_comments_and_blank_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix="-packages", delete=False) as f:
            f.write("# top comment\n\n")
            f.write('apt "vim"\n')
            f.write("# inline\n")
            f.write('snap "code" [args: "--classic"]\n')
            path = f.name
        try:
            entries = list(smu._packages_entries(path))
        finally:
            os.unlink(path)

        self.assertEqual(entries, [
            ("apt", ("vim",)),
            ("snap", ("code", "--classic")),
        ])

    def test_parses_each_kind(self):
        with tempfile.NamedTemporaryFile("w", suffix="-packages", delete=False) as f:
            f.write('ppa "user/repo"\n')
            f.write('apt "curl"\n')
            f.write('snap "code" [args: "--classic"]\n')
            f.write('deb "google-chrome-stable" [args: "https://example.com/c.deb", "c.deb"]\n')
            f.write('source "myrepo.list" [args: "deb https://example.com stable main"]\n')
            path = f.name
        try:
            kinds = [k for k, _ in smu._packages_entries(path)]
        finally:
            os.unlink(path)

        self.assertEqual(kinds, ["ppa", "apt", "snap", "deb", "source"])

    def test_empty_when_file_missing(self):
        self.assertEqual(list(smu._packages_entries("/nonexistent")), [])


class TestModuleStatus(unittest.TestCase):
    def _modules_root(self, tempdir):
        return os.path.join(tempdir, "modules")

    def test_brewfile_installed_when_brew_check_succeeds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "macos", "ai", "chatgpt")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "brewfile"), 'cask "chatgpt"\n')

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False), \
                    patch("smu.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                state, _ = smu.module_status("ai/chatgpt")

            self.assertEqual(state, "installed")
            self.assertTrue(mock_run.call_args[0][0].startswith("cd "))
            self.assertIn("brew bundle check --file brewfile", mock_run.call_args[0][0])

    def test_brewfile_missing_when_brew_check_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "macos", "ai", "chatgpt")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "brewfile"))

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False), \
                    patch("smu.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                state, _ = smu.module_status("ai/chatgpt")

            self.assertEqual(state, "missing")

    def test_packages_partial_when_some_entries_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "debian", "browsers", "chrome")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "packages"),
                   'apt "curl"\napt "wget"\napt "missing-pkg"\n')

            call_results = {"curl": 0, "wget": 0, "missing-pkg": 1}

            def fake_call(cmd, **_):
                for pkg, rc in call_results.items():
                    if pkg in cmd:
                        return rc
                return 1

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", False), \
                    patch.object(smu, "debian", True), \
                    patch.object(smu, "arch", False), \
                    patch("smu.subprocess.call", side_effect=fake_call):
                state, detail = smu.module_status("browsers/chrome")

            self.assertEqual(state, "partial")
            self.assertEqual(detail, "2/3 entries present")

    def test_packages_installed_when_all_entries_present(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "debian", "browsers", "chrome")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "packages"), 'apt "curl"\n')

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", False), \
                    patch.object(smu, "debian", True), \
                    patch.object(smu, "arch", False), \
                    patch("smu.subprocess.call", return_value=0):
                state, _ = smu.module_status("browsers/chrome")

            self.assertEqual(state, "installed")

    def test_script_unknown_without_marker(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "macos", "development-tools", "xcode")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "xcode.sh"))

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                state, detail = smu.module_status("development-tools/xcode")

            self.assertEqual(state, "unknown")
            self.assertIn("xcode.installed", detail)

    def test_script_marker_drives_status(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(self._modules_root(tempdir), "macos", "development-tools", "xcode")
            os.makedirs(module_dir)
            _touch(os.path.join(module_dir, "xcode.sh"))
            _touch(os.path.join(module_dir, "xcode.installed"), "exit 0\n")

            with patch.object(smu, "module_path", self._modules_root(tempdir)), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False), \
                    patch("smu.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                state, _ = smu.module_status("development-tools/xcode")

            self.assertEqual(state, "installed")
            self.assertIn("source", mock_run.call_args[0][0])
            self.assertIn("xcode.installed", mock_run.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
