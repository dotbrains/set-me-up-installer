#!/usr/bin/env python3

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


class TestProvisioningAdapters(unittest.TestCase):
    def test_defaults_to_rcm_without_blueprint_config(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            self.assertEqual(smu.configured_provisioning_adapter(), "rcm")

    def test_reads_blueprint_provisioning_adapter(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            path = os.path.join(tempdir, "smu.toml")
            with open(path, "w") as f:
                f.write('[provisioning]\nadapter = "home-manager"\n')

            self.assertEqual(smu.configured_provisioning_adapter(), "home-manager")

    def test_reads_blueprint_profile_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            path = os.path.join(tempdir, "smu.toml")
            with open(path, "w") as f:
                f.write('[profile.default]\n')
                f.write('modules = ["nushell", "editor/nvim"]\n')

            self.assertEqual(
                smu.blueprint_profile_modules("default"),
                ("nushell", "editor/nvim"),
            )

    def test_rejects_unknown_blueprint_adapter(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            path = os.path.join(tempdir, "smu.toml")
            with open(path, "w") as f:
                f.write('[provisioning]\nadapter = "unknown"\n')

            with self.assertRaises(SystemExit):
                smu.configured_provisioning_adapter()

    def test_unknown_adapters_cannot_apply(self):
        with self.assertRaises(SystemExit):
            smu.require_available_provisioning_adapter("unknown")

    def test_available_adapters_can_apply(self):
        self.assertEqual(smu.require_available_provisioning_adapter("rcm"), "rcm")
        self.assertEqual(
            smu.require_available_provisioning_adapter("home-manager"),
            "home-manager",
        )
        self.assertEqual(smu.require_available_provisioning_adapter("nixos"), "nixos")
        self.assertEqual(smu.require_available_provisioning_adapter("hybrid"), "hybrid")

    def test_home_manager_cannot_run_rcm_shell_provisioning(self):
        with self.assertRaises(SystemExit):
            smu.require_rcm_provisioning_adapter("home-manager")

    def test_list_provisioning_adapters_json_marks_current(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir):
            path = os.path.join(tempdir, "smu.toml")
            with open(path, "w") as f:
                f.write('[provisioning]\nadapter = "nixos"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                smu.list_provisioning_adapters(json_output=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["current"], "nixos")
            current = [item for item in payload["adapters"] if item["current"]]
            self.assertEqual(current[0]["id"], "nixos")

    def test_doctor_reports_unsupported_host(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "linux", False):
            path = os.path.join(tempdir, "smu.toml")
            with open(path, "w") as f:
                f.write('[provisioning]\nadapter = "nix-darwin"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                result = smu.doctor_provisioning_adapter(json_output=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 1)
            self.assertFalse(payload["host_supported"])
            self.assertFalse(payload["can_apply"])

    def test_module_report_infers_rcm_for_legacy_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            rows = smu.module_provisioning_adapter_report()

            self.assertEqual(rows[0]["adapters"], ["rcm"])

    def test_module_report_reads_manifest_adapters(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "editor", "nvim")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.rcm]\npath = "."\n[adapters.home-manager]\npath = "home-manager.nix"\n')

            rows = smu.module_provisioning_adapter_report()

            self.assertEqual(rows[0]["name"], "editor/nvim")
            self.assertEqual(rows[0]["adapters"], ["home-manager", "rcm"])

    def test_resolves_legacy_module_to_rcm(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            resolution = smu.resolve_module_provisioning_adapter("shell", "rcm")

            self.assertEqual(resolution["state"], "ready")
            self.assertEqual(resolution["resolved_adapter"], "rcm")

    def test_resolves_manifest_module_to_home_manager(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "editor", "nvim")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            resolution = smu.resolve_module_provisioning_adapter("editor/nvim", "home-manager")

            self.assertEqual(resolution["state"], "ready")
            self.assertEqual(resolution["resolved_adapter"], "home-manager")
            self.assertEqual(resolution["implementation"]["path"], "home-manager.nix")
            self.assertTrue(resolution["implementation_path"].endswith("home-manager.nix"))

    def test_hybrid_falls_back_to_rcm(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            resolution = smu.resolve_module_provisioning_adapter("shell", "hybrid")

            self.assertEqual(resolution["state"], "fallback")
            self.assertEqual(resolution["resolved_adapter"], "rcm")

    def test_reports_missing_adapter_for_unimplemented_nix_module(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            resolution = smu.resolve_module_provisioning_adapter("shell", "home-manager")

            self.assertEqual(resolution["state"], "missing-adapter")
            self.assertIsNone(resolution["resolved_adapter"])

    def test_provisioning_module_change_plan_includes_adapter_state(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            plan = smu.provisioning_module_change_plan(["shell"], adapter_id="home-manager")

            self.assertEqual(plan[0]["provisioning_adapter"], "home-manager")
            self.assertEqual(plan[0]["adapter_state"], "missing-adapter")

    def test_home_manager_import_plan_collects_ready_and_missing_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            nvim_dir = os.path.join(tempdir, "modules", "universal", "editor", "nvim")
            shell_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(nvim_dir)
            os.makedirs(shell_dir)
            with open(os.path.join(nvim_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')
            with open(os.path.join(shell_dir, "brewfile"), "w"):
                pass

            plan = smu.home_manager_import_plan(["editor/nvim", "shell"])

            self.assertEqual(plan["adapter"], "home-manager")
            self.assertEqual(plan["imports"][0]["module"], "editor/nvim")
            self.assertTrue(plan["imports"][0]["path"].endswith("home-manager.nix"))
            self.assertEqual(plan["missing"][0]["module"], "shell")
            self.assertEqual(plan["missing"][0]["state"], "missing-adapter")

    def test_home_manager_import_plan_uses_blueprint_profile_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "module_path", os.path.join(tempdir, "dotfiles", "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[profile.default]\nmodules = ["nushell"]\n')
            module_dir = os.path.join(tempdir, "dotfiles", "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            plan = smu.home_manager_import_plan(profile="default")

            self.assertEqual(plan["modules"], ["nushell"])
            self.assertEqual(plan["imports"][0]["module"], "nushell")

    def test_print_home_manager_import_plan_outputs_nix_module(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "editor", "nvim")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                smu.print_home_manager_import_plan(["editor/nvim"])

            rendered = output.getvalue()
            self.assertIn("{ ... }:", rendered)
            self.assertIn("imports = [", rendered)
            self.assertIn("home-manager.nix", rendered)

    def test_write_home_manager_import_plan_writes_stable_artifact(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False):
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            output = io.StringIO()
            with redirect_stdout(output):
                smu.write_home_manager_import_plan(["nushell"], profile="default")

            artifact = os.path.join(tempdir, "state", "home-manager", "default.nix")
            self.assertEqual(output.getvalue().strip(), artifact)
            with open(artifact) as f:
                content = f.read()
            self.assertIn("imports = [", content)
            self.assertIn("home-manager.nix", content)

    def test_write_nix_import_plan_supports_nixos_adapter(self):
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

            output = io.StringIO()
            with redirect_stdout(output):
                smu.write_nix_import_plan("nixos", ["nushell"], profile="server")

            artifact = os.path.join(tempdir, "state", "nixos", "server.nix")
            self.assertEqual(output.getvalue().strip(), artifact)
            with open(artifact) as f:
                self.assertIn("nixos.nix", f.read())

    def test_apply_home_manager_modules_writes_artifact_and_switches(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.home-manager]\npath = "home-manager.nix"\n')

            result = smu.apply_home_manager_modules(["nushell"], profile="default")

            artifact = os.path.join(tempdir, "state", "home-manager", "default.nix")
            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(artifact))
            mock_run.assert_called_once_with(["home-manager", "switch", "-f", artifact])

    def test_apply_nix_import_adapter_runs_nix_darwin_switch(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", True), \
                patch.object(smu, "linux", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.nix-darwin]\npath = "nix-darwin.nix"\n')

            result = smu.apply_nix_import_adapter("nix-darwin", ["nushell"], profile="mac")

            artifact = os.path.join(tempdir, "state", "nix-darwin", "mac.nix")
            self.assertEqual(result, 0)
            mock_run.assert_called_once_with([
                "darwin-rebuild",
                "switch",
                "-I",
                f"darwin-config={artifact}",
            ])

    def test_apply_nix_import_adapter_runs_nixos_switch(self):
        real_exists = os.path.exists
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "adapter_state_path", os.path.join(tempdir, "state")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "linux", True), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False), \
                patch("smu.os.path.exists", side_effect=lambda path: path == "/etc/NIXOS" or real_exists(path)), \
                patch("smu.subprocess.call", return_value=0), \
                patch("smu.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            module_dir = os.path.join(tempdir, "modules", "universal", "nushell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('[adapters.nixos]\npath = "nixos.nix"\n')

            result = smu.apply_nix_import_adapter("nixos", ["nushell"], profile="server")

            artifact = os.path.join(tempdir, "state", "nixos", "server.nix")
            self.assertEqual(result, 0)
            mock_run.assert_called_once_with([
                "sudo",
                "nixos-rebuild",
                "switch",
                "-I",
                f"nixos-config={artifact}",
            ])

    def test_nixos_apply_rejects_non_linux_hosts(self):
        with patch.object(smu, "linux", False):
            with self.assertRaises(SystemExit):
                smu.nix_apply_command("nixos", "/tmp/configuration.nix")

    def test_apply_provisioning_adapter_routes_nix_adapters(self):
        with patch("smu.apply_nix_import_adapter", return_value=0) as apply:
            result = smu.apply_provisioning_adapter_modules(
                "nixos",
                ["nushell"],
                profile="server",
                json_output=True,
            )

            self.assertEqual(result, 0)
            apply.assert_called_once_with(
                "nixos",
                ["nushell"],
                profile="server",
                json_output=True,
            )

    def test_apply_home_manager_modules_stops_on_missing_coverage(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "module_path", os.path.join(tempdir, "modules")), \
                patch.object(smu, "macOS", False), \
                patch.object(smu, "debian", False), \
                patch.object(smu, "arch", False), \
                patch("smu.subprocess.run") as mock_run:
            module_dir = os.path.join(tempdir, "modules", "universal", "shell")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "brewfile"), "w"):
                pass

            result = smu.apply_home_manager_modules(["shell"])

            self.assertEqual(result, 1)
            mock_run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
