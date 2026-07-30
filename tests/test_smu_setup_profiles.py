#!/usr/bin/env python3

import unittest
from unittest.mock import patch

import smu
import smu_parts.setup_profiles as setup_profiles


class TestSetupProfiles(unittest.TestCase):
    def test_vps_profile_provisions_headless_server_module(self):
        with patch.object(setup_profiles, "debian", True), \
                patch.object(setup_profiles, "provision_modules_batch") as provision:
            smu.run_setup_profile("vps")

        provision.assert_called_once_with(["server/headless"])

    def test_vps_profile_rejects_non_debian_hosts(self):
        with patch.object(setup_profiles, "debian", False):
            with self.assertRaises(SystemExit):
                smu.run_setup_profile("vps")


if __name__ == "__main__":
    unittest.main()
