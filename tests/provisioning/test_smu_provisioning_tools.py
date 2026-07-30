#!/usr/bin/env python3

import io
import json
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
            metadata_path = os.path.join(tempdir, "state", "home-manager", "default.apply.json")
            with open(metadata_path) as f:
                metadata = json.load(f)
            self.assertEqual(metadata["action"], "build")
            self.assertTrue(metadata["dry_run"])

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

    def test_hybrid_module_plan_strict_reports_rcm_fallback_as_missing(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            plan = smu.hybrid_module_plan(["shell"], strict=True)

            self.assertEqual(plan["rcm_modules"], [])
            self.assertEqual(plan["missing"][0]["module"], "shell")

    def test_provisioning_adapter_audit_json_summarizes_profile_coverage(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[profile.default]\nmodules = ["nushell", "shell"]\n')
            nix_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            rcm_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(nix_dir)
            os.makedirs(rcm_dir)
            with open(os.path.join(nix_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(rcm_dir, "brewfile"), "w"):
                pass

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.provisioning_adapter_audit("home-manager", json_output=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["summary"]["ready"], 1)
            self.assertEqual(payload["summary"]["missing"], 1)

    def test_provisioning_adapter_parity_reports_source_only_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            rcm_dir = os.path.join(tempdir, "modules", "universal", "shell")
            nix_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(rcm_dir)
            os.makedirs(nix_dir)
            with open(os.path.join(rcm_dir, "brewfile"), "w"):
                pass
            with open(os.path.join(nix_dir, "module.toml"), "w") as f:
                f.write('[adapters.rcm]\npath = "."\n[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(nix_dir, "home-manager.nix"), "w"):
                pass

            parity = smu.provisioning_adapter_parity(modules=["shell", "nushell"])

            self.assertEqual(parity["summary"]["ready"], 1)
            self.assertEqual(parity["summary"]["source_only"], 1)

    def test_write_provisioning_adapter_docs_writes_coverage_table(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass
            output_path = os.path.join(tempdir, "coverage.md")

            result = smu.write_provisioning_adapter_docs(output_path)

            self.assertEqual(result, 0)
            with open(output_path) as f:
                self.assertIn("| `home-manager` |", f.read())

    def test_print_nix_bootstrap_status_reports_known_binaries(self):
        with patch("smu.subprocess.call", side_effect=[0, 1, 1, 1]):
            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.print_nix_bootstrap_status(json_output=True)

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(payload["nix"])
        self.assertFalse(payload["home-manager"])

    def test_scaffold_module_adapter_all_writes_each_nix_adapter(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "demo")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "demo.sh"), "w"):
                pass

            result = smu.scaffold_module_adapter("demo", "all")

            self.assertEqual(result, 0)
            for adapter in smu.NIX_IMPORT_ADAPTERS:
                self.assertTrue(os.path.exists(os.path.join(module_dir, f"{adapter}.nix")))
            with open(os.path.join(module_dir, "module.toml")) as f:
                manifest = f.read()
            self.assertIn("[adapters.home-manager]", manifest)
            self.assertIn("[adapters.nix-darwin]", manifest)
            self.assertIn("[adapters.nixos]", manifest)


if __name__ == "__main__":
    unittest.main()
