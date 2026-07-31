#!/usr/bin/env python3

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


class TestProvisioningPreflight(unittest.TestCase):
    def test_preflight_reports_rcm_plan(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.provisioning_adapter_preflight(
                    adapter_id="rcm",
                    modules=["shell"],
                    json_output=True,
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["preflight"], "passed")
            self.assertEqual(payload["plan"]["kind"], "rcm")
            self.assertEqual(payload["plan"]["commands"][0][0], "smu")

    def test_preflight_reports_nix_artifact_and_command(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.provisioning_adapter_preflight(
                    adapter_id="home-manager",
                    modules=["shell"],
                    json_output=True,
                    action="build",
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["plan"]["kind"], "nix")
            self.assertTrue(payload["plan"]["artifacts"][0].endswith("default.nix"))
            self.assertEqual(payload["plan"]["commands"][0][:2], ["home-manager", "build"])

    def test_preflight_reports_hybrid_nix_and_rcm_phases(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            nix_dir = os.path.join(tempdir, "modules", "universal", "nix-shell")
            rcm_dir = os.path.join(tempdir, "modules", "universal", "rcm-shell")
            os.makedirs(nix_dir)
            os.makedirs(rcm_dir)
            with open(os.path.join(nix_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(rcm_dir, "brewfile"), "w"):
                pass

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.provisioning_adapter_preflight(
                    adapter_id="hybrid",
                    modules=["nix-shell", "rcm-shell"],
                    json_output=True,
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["plan"]["kind"], "hybrid")
            self.assertEqual(payload["plan"]["nix_modules"], ["nix-shell"])
            self.assertEqual(payload["plan"]["rcm_modules"], ["rcm-shell"])
            self.assertEqual(len(payload["plan"]["commands"]), 2)

    def test_preflight_rejects_unsupported_host(self):
        output = io.StringIO()
        with patch.object(smu, "macOS", False), \
                patch.object(smu, "linux", False), \
                redirect_stdout(output):
            result = smu.provisioning_adapter_preflight(
                adapter_id="nix-darwin",
                modules=["shell"],
                json_output=True,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 1)
        self.assertFalse(payload["host_supported"])
        self.assertEqual(payload["preflight"], "failed")


if __name__ == "__main__":
    unittest.main()
