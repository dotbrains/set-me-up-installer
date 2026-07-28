#!/usr/bin/env python3

import unittest

import smu
import smu_parts


class TestSmuPartsPackage(unittest.TestCase):
    def test_package_declares_ordered_parts(self):
        self.assertEqual(smu_parts.PARTS[0].__name__, "smu_parts.core")
        self.assertEqual(smu_parts.PARTS[-1].__name__, "smu_parts.cli")

    def test_smu_exports_loaded_part_functions(self):
        self.assertTrue(callable(smu.main))
        self.assertTrue(callable(smu.catalog_install))
        self.assertTrue(callable(smu.materialize_adapters))
        self.assertEqual(smu.__smu_parts__[0], "smu_parts.core")
        self.assertEqual(smu.__smu_parts__[-1], "smu_parts.cli")


if __name__ == "__main__":
    unittest.main()
