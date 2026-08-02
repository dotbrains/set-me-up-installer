#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuProductizationRuntime(unittest.TestCase):
    def test_release_package_payload_has_latest_known_good_channel(self):
        payload = smu.release_package_payload("1.2.3", "latest-known-good")

        self.assertEqual(payload["version"], "1.2.3")
        self.assertTrue(payload["tag"]["signed_required"])
        self.assertTrue(payload["latest_known_good"]["requires_release_readiness"])

    def test_fleet_plan_reads_hosts_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            hosts = os.path.join(tempdir, "hosts.txt")
            with open(hosts, "w") as f:
                f.write("app1 root\napp2 deploy\n")

            payload = smu.fleet_plan_payload(["plan", "--hosts", hosts, "--profile", "vps"])

        self.assertEqual(len(payload["hosts"]), 2)
        self.assertIn("smu plan --machine vps", payload["commands"][0]["command"])
        self.assertFalse(payload["executes_remote"])

    def test_blueprint_registry_filters_entries(self):
        payload = smu.blueprint_registry_payload("nicholas")

        self.assertEqual(payload["count"], 1)
        self.assertIn("hybrid", payload["entries"][0]["modes"])

    def test_module_graph_orders_dependencies(self):
        payload = smu.module_graph_payload(["rcm", "base"])

        self.assertEqual(payload["order"], ["base", "rcm"])
        self.assertTrue(payload["explanations"])

    def test_tui_payload_reports_review_screens(self):
        payload = smu.tui_payload(["--profile", "vps"])

        self.assertIn("rollback", payload["screens"])
        self.assertIn("modules", payload["selected"])

    def test_drift_doctor_reports_adapter_conflicts(self):
        with patch.object(smu, "adapter_conflict_report", return_value={"conflicted": False, "items": []}):
            payload = smu.drift_payload("/tmp/blueprint")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["root"], "/tmp/blueprint")

    def test_post_install_health_requires_core_tools_only_for_ok(self):
        with patch.object(smu.shutil, "which", side_effect=lambda name: "/bin/tool" if name in ("bash", "git", "ssh") else None):
            payload = smu.post_install_health_payload("vps")

        self.assertTrue(payload["ok"])
        self.assertFalse([check for check in payload["checks"] if check["name"] == "nix"][0]["ok"])

    def test_policy_command_reports_adapter_errors(self):
        payload = smu.policy_payload(["check", "--preset", "strict", "--provisioning-adapter", "home-manager"])

        self.assertFalse(payload["ok"])
        self.assertIn("home-manager", payload["errors"][0])

    def test_policy_command_does_not_treat_preset_value_as_module(self):
        payload = smu.policy_payload(["check", "--preset", "ci"])

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["trust"]["modules"], [])

    def test_rollback_restore_fixture_reports_restored(self):
        payload = smu.rollback_restore_test_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["preview"]["guarantee"]["coverage"], "full")

    def test_product_docs_command_writes_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = os.path.join(tempdir, "product.md")
            payload = smu.product_docs_payload(output)

            with open(output) as f:
                content = f.read()

        self.assertEqual(payload["output"], output)
        self.assertIn("fleet", content)

    def test_release_package_command_prints_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = smu.release_package_command(["--version", "1.2.3", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(buf.getvalue())["version"], "1.2.3")


if __name__ == "__main__":
    unittest.main()
