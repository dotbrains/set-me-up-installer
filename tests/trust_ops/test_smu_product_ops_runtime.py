#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import smu


class TestSmuProductOpsRuntime(unittest.TestCase):
    def test_inventory_reads_host_groups_and_policy(self):
        with tempfile.TemporaryDirectory() as tempdir:
            inventory = os.path.join(tempdir, "inventory.json")
            with open(inventory, "w") as f:
                json.dump({
                    "groups": {"web": ["app1"]},
                    "hosts": [{"id": "app1", "host": "10.0.0.1", "user": "deploy", "policy": {"sudo": False}}],
                }, f)

            payload = smu.inventory_payload(["--inventory", inventory])

        self.assertEqual(payload["groups"]["web"], ["app1"])
        self.assertEqual(payload["hosts"][0]["policy"]["sudo"], False)

    def test_host_facts_reports_core_tools(self):
        with patch.object(smu.shutil, "which", side_effect=lambda name: f"/bin/{name}" if name in ("sudo", "nix") else None):
            payload = smu.host_facts_payload([])

        self.assertTrue(payload["facts"]["sudo"])
        self.assertTrue(payload["facts"]["nix"])
        self.assertIn("package_managers", payload["facts"])

    def test_plan_diff_reports_changed_top_level_keys(self):
        with tempfile.TemporaryDirectory() as tempdir:
            before = os.path.join(tempdir, "before.json")
            after = os.path.join(tempdir, "after.json")
            with open(before, "w") as f:
                json.dump({"provisioning": {"adapter": "rcm"}}, f)
            with open(after, "w") as f:
                json.dump({"provisioning": {"adapter": "home-manager"}}, f)

            payload = smu.plan_diff_payload(["--from", before, "--to", after])

        self.assertTrue(payload["changed"])
        self.assertEqual(payload["changes"][0]["path"], "provisioning")

    def test_approval_blocks_ci_non_dry_run(self):
        with patch.dict(os.environ, {"CI": "true"}):
            payload = smu.approval_payload(["--preset", "ci"])

        self.assertFalse(payload["ok"])
        self.assertIn("CI may only run dry-run", payload["errors"][0])

    def test_state_timeline_combines_ledger_and_drift(self):
        with patch.object(smu, "read_state_ledger", return_value=[{"operation": "materialize_adapters", "timestamp": "2026-01-01T00:00:00Z"}]), \
                patch.object(smu, "_read_json_file", return_value=[]), \
                patch.object(smu, "drift_payload", return_value={"ok": True}):
            payload = smu.state_timeline_payload()

        self.assertEqual(payload["events"][0]["source"], "ledger")
        self.assertTrue([event for event in payload["events"] if event["source"] == "drift"])

    def test_lock_payload_records_blueprint_and_registry(self):
        with patch.object(smu, "_git_head", return_value="abc123"), \
                patch.object(smu, "config_drift_report", return_value={"items": []}):
            payload = smu.blueprint_lock_payload(["--profile", "vps"])

        self.assertEqual(payload["blueprint"]["head"], "abc123")
        self.assertIn("registry", payload)

    def test_bootstrap_bundle_writes_archive(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = os.path.join(tempdir, "bundle.zip")
            with patch.object(smu, "universal_plan_payload", return_value={"ok": True}), \
                    patch.object(smu, "blueprint_lock_payload", return_value={"schema_version": 1}):
                payload = smu.bootstrap_bundle_payload(["--output", output])
                exists = os.path.exists(payload["output"])

        self.assertTrue(exists)
        self.assertIn("smu.lock", payload["files"])

    def test_policy_explain_reports_adapter_reason(self):
        payload = smu.policy_explain_payload(["--preset", "strict", "--provisioning-adapter", "home-manager"])

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["explanations"][0]["subject"], "adapter:home-manager")

    def test_golden_examples_cover_expected_paths(self):
        payload = smu.golden_examples_payload()

        self.assertEqual(payload["count"], 5)
        self.assertTrue([example for example in payload["examples"] if example["id"] == "macos-nix-darwin"])

    def test_release_provenance_includes_schema_versions(self):
        with patch.object(smu, "_git_head", return_value="abc123"):
            payload = smu.release_provenance_payload(["--version", "1.2.3"])

        self.assertEqual(payload["provenance"]["installer_sha"], "abc123")
        self.assertIn("plan", payload["provenance"]["contract_schemas"])


if __name__ == "__main__":
    unittest.main()
