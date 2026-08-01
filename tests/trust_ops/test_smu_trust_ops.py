import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import smu


class TestTrustOps(unittest.TestCase):
    def test_machine_profiles_include_expected_defaults(self):
        self.assertIn("vps", smu.supported_machine_profiles())
        profile = smu.machine_profile("vps")
        self.assertEqual(profile["modules"], ("server/headless",))
        self.assertEqual(profile["adapter"], "hybrid")
        self.assertEqual(profile["submodule_scope"], "platform")

    def test_secrets_scan_reports_secret_like_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with open(os.path.join(tempdir, ".env"), "w") as f:
                f.write("TOKEN=abc12345678901234567890\n")
            payload = smu.secrets_scan(tempdir)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["findings"][0]["risk"], "secret-like-name")

    def test_rollback_doctor_summarizes_last_events(self):
        with patch.object(smu, "read_state_ledger", return_value=[{
            "id": "event-1",
            "operation": "materialize_adapters",
            "items": [{"before": {"path": "/tmp/example", "exists": False}}],
        }]):
            payload = smu.rollback_doctor_payload()
            self.assertEqual(payload["coverage"], "full")
            self.assertEqual(payload["events"][0]["id"], "event-1")

    def test_universal_plan_uses_machine_profile_modules(self):
        with tempfile.TemporaryDirectory() as tempdir, \
                patch.object(smu, "smu_home_dir", tempdir), \
                patch.object(smu, "module_path", os.path.join(tempdir, "dotfiles", "modules")), \
                patch.object(smu, "read_state_ledger", return_value=[]), \
                patch.object(smu, "blueprint_profile_modules", return_value=()):
            module_dir = os.path.join(tempdir, "dotfiles", "modules", "debian", "server", "headless")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "packages"), "w") as f:
                f.write('apt "git"\n')
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = smu.universal_plan(["--machine", "vps", "--json"])
            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["provisioning"]["modules"], ["server/headless"])
            self.assertEqual(payload["machine_profile"]["id"], "vps")

    def test_adapter_dashboard_suggests_next_blocking_module(self):
        with patch.object(smu, "blueprint_profile_modules", return_value=["base"]), \
                patch.object(smu, "resolve_module_provisioning_adapter", return_value={
                    "module": "base",
                    "adapter": "home-manager",
                    "state": "missing-adapter",
                    "available_adapters": ["rcm"],
                    "resolved_adapter": None,
                    "implementation": None,
                }):
            payload = smu.provisioning_adapter_dashboard()
            self.assertEqual(payload["suggested_next_port"], "base")
            self.assertIn("Port modules", payload["github_issue"])


if __name__ == "__main__":
    unittest.main()
