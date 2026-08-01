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

    def test_universal_plan_default_output_is_table(self):
        with patch.object(smu, "universal_plan_payload", return_value={
            "blueprint": {"repository": "owner/repo", "branch": "main", "submodule_scope": "platform"},
            "machine_profile": {"id": "vps"},
            "provisioning": {"adapter": "rcm", "plan": []},
            "packages": [],
            "dotfiles": {"conflicted": False, "items": []},
            "secrets": {"findings": []},
            "trust": {"warnings": []},
            "rollback": {"coverage": "partial", "total_events": 0},
        }):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = smu.universal_plan(["--machine", "vps"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(output.getvalue().startswith("section\titem\tstatus\tdetail"))

    def test_new_contract_examples_validate(self):
        for name in ("plan", "secrets-doctor", "trust-doctor", "support-bundle", "conformance"):
            with self.subTest(name=name):
                path = os.path.join(smu.contracts_path, f"{name}.example.json")
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
                self.assertFalse(smu.smu_contract.json_contract_errors(name, payload))

    def test_strict_doctor_payload_aggregates_checks(self):
        with patch.object(smu, "blueprint_profile_modules", return_value=[]), \
                patch.object(smu, "secrets_scan", return_value={"ok": True}), \
                patch.object(smu, "rollback_doctor_payload", return_value={"coverage": "partial"}), \
                patch.object(smu, "trust_report", return_value={"warnings": []}), \
                patch.object(smu, "provisioning_adapter_preflight_payload", return_value={"preflight": "passed"}), \
                patch.object(smu, "repository_update_doctor", return_value={"errors": []}), \
                patch.object(smu, "blueprint_conformance", return_value={"ready": True}):
            payload = smu.strict_doctor_payload()
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["checks"]), 6)

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

    def test_trust_enforcement_blocks_risky_modules(self):
        with patch.object(smu, "trust_report", return_value={"modules": [{
            "module": "server/headless",
            "state": "ok",
            "trust": "first-party",
            "network": True,
            "requires_sudo": True,
            "rollback": "partial",
            "writes": [],
        }], "warnings": []}):
            payload = smu.trust_enforcement_payload(["server/headless"])
            self.assertFalse(payload["ok"])
            self.assertIn("network access", payload["violations"][0])

    def test_support_bundle_redacts_known_secret_shapes(self):
        payload = smu._redact({
            "github_token": "ghp_123456789012345678901234567890123456",
            "line": "API_KEY=abc12345678901234567890",
        })
        self.assertEqual(payload["github_token"], "<redacted>")
        self.assertEqual(payload["line"], "API_KEY=<redacted>")

    def test_conformance_includes_score(self):
        with patch.object(smu, "dotfiles_compatibility_contract", return_value={"readiness": {}}), \
                patch.object(smu, "blueprint_ci_contract", return_value=0), \
                patch.object(smu, "read_state_ledger", return_value=[]):
            payload = smu.blueprint_conformance("/tmp/missing")
            self.assertIn("score", payload)
            self.assertEqual(payload["total"], len(payload["checks"]))

    def test_migration_pr_payload_includes_pr_body(self):
        payload = smu.blueprint_migration_pr_payload("/tmp/repo")
        self.assertEqual(payload["pull_request"]["title"], "Adopt set-me-up install surface")
        self.assertTrue(any("smu blueprint ci" in command for command in payload["commands"]))

    def test_release_notes_render_provenance(self):
        content = smu.release_notes_from_provenance({
            "provenance": {"timestamp": "2026-08-01T00:00:00Z", "installer": "abc123"},
            "repositories": [{"path": "installer", "head": "abc123", "sync": "synced"}],
        })
        self.assertIn("installer", content)
        self.assertIn("abc123", content)


if __name__ == "__main__":
    unittest.main()
