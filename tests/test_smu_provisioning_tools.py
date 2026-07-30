#!/usr/bin/env python3

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


class TestProvisioningTools(unittest.TestCase):
    def test_validate_module_manifests_reports_missing_adapter_path(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "missing.nix"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.validate_module_manifests()

            self.assertEqual(result, 1)
            self.assertIn("path missing", output.getvalue())

    def test_validate_module_manifests_accepts_existing_adapter_path(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass

            self.assertEqual(smu.validate_module_manifests(), 0)

    def test_write_nix_flake_writes_adapter_output(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.nixos]\npath = "nixos.nix"\n')
            with open(os.path.join(module_dir, "nixos.nix"), "w"):
                pass

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.write_nix_flake("nixos", ["nushell"], profile="server-one")

            self.assertEqual(result, 0)
            flake_path = os.path.join(tempdir, "state", "nixos", "flake.nix")
            self.assertEqual(output.getvalue().strip(), flake_path)
            with open(flake_path) as f:
                self.assertIn('nixosConfigurations."server-one"', f.read())

    def test_apply_nix_import_adapter_dry_run_skips_switch(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch("smu.subprocess.run") as mock_run:
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            result = smu.apply_nix_import_adapter("home-manager", ["nushell"], dry_run=True, action="build")

            self.assertEqual(result, 0)
            mock_run.assert_not_called()

    def test_hybrid_module_plan_splits_nix_and_rcm_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            nix_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            rcm_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(nix_dir)
            os.makedirs(rcm_dir)
            with open(os.path.join(nix_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(rcm_dir, "brewfile"), "w"):
                pass

            plan = smu.hybrid_module_plan(["nushell", "shell"])

            self.assertEqual(plan["nix_modules"], ["nushell"])
            self.assertEqual(plan["rcm_modules"], ["shell"])


if __name__ == "__main__":
    unittest.main()
