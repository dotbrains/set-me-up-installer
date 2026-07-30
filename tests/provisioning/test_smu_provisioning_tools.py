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
                f.write('id = "nushell"\n[adapters.home-manager]\npath = "missing.nix"\n')

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
                f.write('id = "nushell"\n[adapters.home-manager]\npath = "home-manager.nix"\n')
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

    def test_validate_module_manifests_rejects_invalid_policy_fields(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('id = "nushell"\n[adapters.home-manager]\n')
                f.write('path = "home-manager.nix"\nrequires_root = "yes"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass

            self.assertEqual(smu.validate_module_manifests(), 1)

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

    def test_nix_profile_doctor_reports_policy_errors(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "linux", True), \
                patch.object(smu, "debian", True), \
                patch.object(smu, "arch", False), \
                patch("smu.subprocess.call", return_value=1):
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[profile.default]\nmodules = ["nushell"]\n')
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('id = "nushell"\n[adapters.home-manager]\n')
                f.write('path = "home-manager.nix"\nplatforms = ["macos"]\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.nix_profile_doctor(json_output=True, strict=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 1)
            self.assertTrue(payload["policy_errors"])

    def test_write_migration_state_tracks_review_status(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('id = "nushell"\n[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass

            result = smu.write_migration_state("home-manager", modules=["nushell"])

            self.assertEqual(result, 0)
            with open(os.path.join(tempdir, "state", "home-manager-migration-state.json")) as f:
                payload = json.load(f)
            self.assertEqual(payload["modules"][0]["review_status"], "accepted")

    def test_generate_home_manager_adapter_writes_manifest_entry(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "zsh")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "zsh.sh"), "w"):
                pass

            result = smu.generate_home_manager_adapter("zsh")

            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(os.path.join(module_dir, "home-manager.nix")))
            with open(os.path.join(module_dir, "module.toml")) as f:
                self.assertIn("[adapters.home-manager]", f.read())

    def test_blueprint_init_writes_requested_mode(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            result = smu.blueprint_init(mode="hybrid")

            self.assertEqual(result, 0)
            with open(os.path.join(tempdir, "smu.toml")) as f:
                content = f.read()
            self.assertIn('mode = "hybrid"', content)
            self.assertIn('adapter = "hybrid"', content)
            self.assertIn('allow_rcm_fallback = true', content)

    def test_write_blueprint_schema_check_detects_fresh_schema(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = os.path.join(tempdir, "blueprint.schema.json")

            self.assertEqual(smu.write_blueprint_schema(output_path), 0)
            self.assertEqual(smu.write_blueprint_schema(output_path, check=True), 0)

    def test_rcm_to_nix_migration_report_classifies_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            ported_dir = os.path.join(tempdir, "modules", "universal", "ported")
            kept_dir = os.path.join(tempdir, "modules", "universal", "kept")
            os.makedirs(ported_dir)
            os.makedirs(kept_dir)
            with open(os.path.join(ported_dir, "module.toml"), "w") as f:
                f.write('[adapters.rcm]\npath = "."\n[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(ported_dir, "home-manager.nix"), "w"):
                pass
            with open(os.path.join(kept_dir, "brewfile"), "w"):
                pass

            payload = smu.rcm_to_nix_migration_report(modules=["ported", "kept"])

            statuses = {row["module"]: row["status"] for row in payload["files"]}
            self.assertEqual(statuses["ported"], "ported")
            self.assertEqual(statuses["kept"], "kept-rcm")

    def test_provisioning_compatibility_matrix_lists_adapter_states(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass

            payload = smu.provisioning_compatibility_matrix()

            self.assertEqual(payload["modules"][0]["module"], "nushell")
            self.assertEqual(payload["modules"][0]["home-manager"], "ready")

    def test_blueprint_doctor_rejects_mode_adapter_drift(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "rcm"\nadapter = "home-manager"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.blueprint_doctor(json_output=True, strict=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 1)
            self.assertFalse(payload["valid"])
            self.assertIn("mode 'rcm' requires adapter 'rcm'", payload["errors"][0])

    def test_blueprint_migrate_writes_target_mode(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            result = smu.blueprint_migrate(target_mode="hybrid", force=True)

            self.assertEqual(result, 0)
            with open(os.path.join(tempdir, "smu.toml")) as f:
                content = f.read()
            self.assertIn('mode = "hybrid"', content)
            self.assertIn('adapter = "hybrid"', content)

    def test_blueprint_compatibility_docs_check_detects_fresh_docs(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(module_dir, "home-manager.nix"), "w"):
                pass
            output_path = os.path.join(tempdir, "compatibility.md")

            self.assertEqual(smu.write_blueprint_compatibility_docs(output_path), 0)
            self.assertEqual(smu.write_blueprint_compatibility_docs(output_path, check=True), 0)

    def test_blueprint_ci_contract_validates_checkout(self):
        with tempfile.TemporaryDirectory() as tempdir:
            os.makedirs(os.path.join(tempdir, "examples", "github-actions"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "debian-vps"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "ubuntu-vps"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "arch-vps"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "nixos-vps"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "digitalocean-droplet"))
            os.makedirs(os.path.join(tempdir, "examples", "providers", "hetzner-cloud"))
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "rcm"\nadapter = "rcm"\n')
            for workflow in ("rcm.yml", "nix.yml", "hybrid.yml"):
                with open(os.path.join(tempdir, "examples", "github-actions", workflow), "w"):
                    pass
            for provider in ("debian-vps", "ubuntu-vps", "arch-vps"):
                with open(os.path.join(tempdir, "examples", "providers", provider, "smu.toml"), "w") as f:
                    f.write('[provisioning]\nmode = "nix"\nadapter = "home-manager"\n')
            with open(os.path.join(tempdir, "examples", "providers", "nixos-vps", "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "nix"\nadapter = "nixos"\n')
            for provider in ("digitalocean-droplet", "hetzner-cloud"):
                with open(os.path.join(tempdir, "examples", "providers", provider, "smu.toml"), "w") as f:
                    f.write('[provisioning]\nmode = "hybrid"\nadapter = "hybrid"\nnix_adapter = "home-manager"\n')
            with open(os.path.join(tempdir, "PROVISIONING-COMPATIBILITY.md"), "w") as f:
                f.write("examples/providers/debian-vps\nexamples/github-actions/nix.yml\n")

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.blueprint_ci_contract(root=tempdir, json_output=True, check_docs=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertTrue(payload["valid"])

    def test_blueprint_ci_contract_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "rcm"\nadapter = "home-manager"\n')

            result = smu.blueprint_ci_contract(root=tempdir, check_docs=True)

            self.assertEqual(result, 1)

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
