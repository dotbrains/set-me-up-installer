#!/usr/bin/env python3

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w"):
        pass


def _build_fixture(modules_dir):
    """Lay down a representative module tree under `modules_dir`."""
    # macos: nested group + script, plus a brewfile-only module
    _touch(os.path.join(modules_dir, "macos", "productivity-tools", "hyperkey", "hyperkey.sh"))
    _touch(os.path.join(modules_dir, "macos", "fonts", "brewfile"))

    # debian: simple script module + packages-only module
    _touch(os.path.join(modules_dir, "debian", "fonts", "fonts.sh"))
    _touch(os.path.join(modules_dir, "debian", "browsers", "chrome", "packages"))

    # arch: simple script module
    _touch(os.path.join(modules_dir, "arch", "fonts", "fonts.sh"))

    # universal: nested group with script + a top-level brewfile module
    _touch(os.path.join(modules_dir, "universal", "python", "pip", "pip.sh"))
    _touch(os.path.join(modules_dir, "universal", "shell", "brewfile"))

    # noise — a stray file that should not register as a module
    _touch(os.path.join(modules_dir, "universal", "README.md"))


class TestDiscoverModules(unittest.TestCase):
    def test_discovers_scripts_brewfiles_and_nested_groups(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            with patch.object(smu, "module_path", modules_dir):
                buckets = smu.discover_modules()

            self.assertEqual(set(buckets.keys()), {"macos", "debian", "arch", "universal"})
            self.assertIn(("productivity-tools/hyperkey", "script"), buckets["macos"])
            self.assertIn(("fonts", "brewfile"), buckets["macos"])
            self.assertIn(("browsers/chrome", "packages"), buckets["debian"])
            self.assertIn(("python/pip", "script"), buckets["universal"])
            self.assertIn(("shell", "brewfile"), buckets["universal"])

    def test_returns_empty_when_modules_dir_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing = os.path.join(tempdir, "does-not-exist")
            with patch.object(smu, "module_path", missing):
                self.assertEqual(smu.discover_modules(), {})


class TestListModulesOutput(unittest.TestCase):
    def _run(self, **kwargs):
        buf = io.StringIO()
        with redirect_stdout(buf):
            smu.list_modules(**kwargs)
        return buf.getvalue()

    def test_default_filters_to_current_os_and_universal(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                output = self._run()

            self.assertIn("macos/", output)
            self.assertIn("universal/", output)
            self.assertNotIn("debian/", output)
            self.assertNotIn("arch/", output)
            self.assertIn("productivity-tools/hyperkey", output)
            self.assertIn("[script]", output)
            self.assertIn("[brewfile]", output)

    def test_all_flag_includes_other_os_buckets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                output = self._run(show_all=True)

            self.assertIn("macos/", output)
            self.assertIn("debian/", output)
            self.assertIn("arch/", output)
            self.assertIn("universal/", output)

    def test_search_filters_modules_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                output = self._run(search="HYPER", show_all=True)

            self.assertIn("hyperkey", output)
            self.assertNotIn("python/pip", output)
            self.assertNotIn("shell", output.split("Found")[0])

    def test_search_with_no_matches_warns(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            with patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                output = self._run(search="nonexistent-xyz")

            self.assertIn("No modules match", output)

    def test_warns_when_modules_dir_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing = os.path.join(tempdir, "missing")
            with patch.object(smu, "module_path", missing):
                output = self._run()

            self.assertIn("No modules found", output)


if __name__ == "__main__":
    unittest.main()
