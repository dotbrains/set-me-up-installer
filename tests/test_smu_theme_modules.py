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


class TestThemeModuleResolution(unittest.TestCase):
    def test_resolves_top_level_colorscheme_module(self):
        with tempfile.TemporaryDirectory() as tempdir:
            modules_dir = os.path.join(tempdir, "modules")
            _touch(os.path.join(modules_dir, "colorschemes", "colorschemes.sh"))

            with patch.object(smu, "module_path", modules_dir):
                self.assertEqual(
                    smu.get_module_path("colorschemes"),
                    os.path.join(modules_dir, "colorschemes", "colorschemes.sh"),
                )


if __name__ == "__main__":
    unittest.main()
