#!/usr/bin/env python3

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import smu


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w"):
        pass


def _build_fixture(modules_dir):
    _touch(os.path.join(modules_dir, "macos", "productivity-tools", "hyperkey", "hyperkey.sh"))
    _touch(os.path.join(modules_dir, "macos", "fonts", "brewfile"))
    _touch(os.path.join(modules_dir, "universal", "python", "pip", "pip.sh"))


class TestFzfFormatting(unittest.TestCase):
    def test_format_fzf_lines_aligns_columns(self):
        entries = [
            ("macos", "productivity-tools/hyperkey", "script"),
            ("universal", "shell", "brewfile"),
        ]
        lines = smu._format_fzf_lines(entries)
        self.assertEqual(len(lines), 2)
        # Bucket column should be ljust-padded to the longer of "macos"/"universal" = 9.
        self.assertTrue(lines[0].startswith("macos    "))
        self.assertTrue(lines[1].startswith("universal"))
        self.assertIn("[script]", lines[0])
        self.assertIn("[brewfile]", lines[1])

    def test_format_fzf_lines_handles_empty(self):
        self.assertEqual(smu._format_fzf_lines([]), [])

    def test_parse_fzf_selection_extracts_module_name(self):
        line = "macos    productivity-tools/hyperkey  [script]"
        self.assertEqual(smu._parse_fzf_selection(line), "productivity-tools/hyperkey")

    def test_parse_fzf_selection_returns_none_for_short_line(self):
        self.assertIsNone(smu._parse_fzf_selection("oneword"))


class TestInteractiveSelectModules(unittest.TestCase):
    def test_dies_when_fzf_not_installed(self):
        with patch.object(smu.subprocess, "call", return_value=1):
            with self.assertRaises(SystemExit):
                smu.interactive_select_modules()

    def test_returns_empty_when_no_modules_dir(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing = os.path.join(tempdir, "missing")
            with patch.object(smu.subprocess, "call", return_value=0), \
                    patch.object(smu, "module_path", missing):
                self.assertEqual(smu.interactive_select_modules(), [])

    def test_passes_filtered_entries_to_fzf_and_parses_selection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            # Simulate fzf returning two selections.
            fake_result = MagicMock()
            fake_result.returncode = 0
            fake_result.stdout = (
                "macos      productivity-tools/hyperkey  [script]\n"
                "universal  python/pip                   [script]\n"
            )

            with patch.object(smu.subprocess, "call", return_value=0), \
                    patch.object(smu.subprocess, "run", return_value=fake_result) as mock_run, \
                    patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                selected = smu.interactive_select_modules(search="py", show_all=True)

            self.assertEqual(selected, ["productivity-tools/hyperkey", "python/pip"])

            # Verify fzf was invoked with --multi, the space binding, and the search query.
            args, kwargs = mock_run.call_args
            cmd = args[0]
            self.assertEqual(cmd[0], "fzf")
            self.assertIn("--multi", cmd)
            self.assertIn("--bind=space:toggle+down", cmd)
            self.assertIn("--query", cmd)
            self.assertEqual(cmd[cmd.index("--query") + 1], "py")

            # Input piped to fzf should include all three modules (show_all=True).
            piped = kwargs["input"]
            self.assertIn("productivity-tools/hyperkey", piped)
            self.assertIn("fonts", piped)
            self.assertIn("python/pip", piped)

    def test_returns_empty_when_fzf_cancelled(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)

            fake_result = MagicMock()
            fake_result.returncode = 130  # fzf exit code on ESC
            fake_result.stdout = ""

            with patch.object(smu.subprocess, "call", return_value=0), \
                    patch.object(smu.subprocess, "run", return_value=fake_result), \
                    patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                selected = smu.interactive_select_modules()

            self.assertEqual(selected, [])

    def test_default_filter_excludes_other_os_buckets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _build_fixture(modules_dir)
            _touch(os.path.join(modules_dir, "debian", "fonts", "fonts.sh"))

            fake_result = MagicMock()
            fake_result.returncode = 0
            fake_result.stdout = "macos  fonts  [brewfile]\n"

            with patch.object(smu.subprocess, "call", return_value=0), \
                    patch.object(smu.subprocess, "run", return_value=fake_result) as mock_run, \
                    patch.object(smu, "module_path", modules_dir), \
                    patch.object(smu, "macOS", True), \
                    patch.object(smu, "debian", False), \
                    patch.object(smu, "arch", False):
                smu.interactive_select_modules()

            piped = mock_run.call_args.kwargs["input"]
            self.assertIn("macos", piped)
            self.assertIn("universal", piped)
            self.assertNotIn("debian", piped)


if __name__ == "__main__":
    unittest.main()
