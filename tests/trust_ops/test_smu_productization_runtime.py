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
        with patch.object(smu, "adapter_conflict_report", return_value={"conflicted": False, "items": []}), \
                patch.object(smu, "config_drift_report", return_value={"drifted": False, "items": []}):
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

    def test_release_package_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            exit_code = smu.release_package_command(["--version", "1.2.3", "--output", tempdir, "--json"])

            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.exists(os.path.join(tempdir, "release-manifest.json")))
            self.assertTrue(os.path.exists(os.path.join(tempdir, "checksums.txt")))

    def test_blueprint_registry_loads_third_party_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry = os.path.join(tempdir, "registry.json")
            with open(registry, "w") as f:
                json.dump({"entries": [{"id": "example/blueprint", "url": "https://example.com/bp", "modes": ["nix"]}]}, f)

            payload = smu.blueprint_registry_payload("example", registry)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["id"], "example/blueprint")

    def test_fleet_apply_runs_guarded_ssh_and_writes_logs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            hosts = os.path.join(tempdir, "hosts.txt")
            with open(hosts, "w") as f:
                f.write("app1 deploy\n")
            completed = smu.subprocess.CompletedProcess(["ssh"], 0, "ok\n", "")

            with patch.object(smu.subprocess, "run", return_value=completed) as run:
                payload = smu.fleet_plan_payload(["apply", "--apply", "--hosts", hosts, "--log-dir", tempdir])
                payload = smu._fleet_apply(payload)
                log_exists = os.path.exists(payload["results"][0]["log"])

        self.assertTrue(payload["ok"])
        self.assertEqual(run.call_args[0][0][0], "ssh")
        self.assertTrue(log_exists)

    def test_policy_file_overrides_preset(self):
        with tempfile.TemporaryDirectory() as tempdir:
            os.makedirs(os.path.join(tempdir, ".smu"))
            with open(os.path.join(tempdir, ".smu", "policy.toml"), "w") as f:
                f.write('adapters = ["rcm"]\nsudo = false\nnetwork = false\n')

            payload = smu.policy_payload(["check", "--root", tempdir, "--provisioning-adapter", "home-manager"])

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["policy"]["adapters"], ["rcm"])

    def test_module_graph_reads_manifest_blockers(self):
        with tempfile.TemporaryDirectory() as tempdir:
            module_dir = os.path.join(tempdir, "custom")
            os.makedirs(module_dir)
            with open(os.path.join(module_dir, "module.toml"), "w") as f:
                f.write('depends_on = ["base"]\nconflicts_with = ["rcm"]\nprovides = ["custom"]\norder = 5\n')

            with patch.object(smu, "module_path", tempdir):
                payload = smu.module_graph_payload(["custom", "rcm"])

        custom = [node for node in payload["nodes"] if node["module"] == "custom"][0]
        self.assertEqual(custom["blockers"][0]["type"], "missing_dependency")
        self.assertTrue([item for item in custom["blockers"] if item["type"] == "conflict"])

    def test_drift_payload_includes_state_engines(self):
        with patch.object(smu, "adapter_conflict_report", return_value={"conflicted": False, "items": []}), \
                patch.object(smu, "config_drift_report", return_value={"drifted": False, "items": []}), \
                patch.object(smu, "rollback_doctor_payload", return_value={"events": []}), \
                patch.object(smu.shutil, "which", return_value=None):
            payload = smu.drift_payload("/tmp/blueprint")

        self.assertIn("generated_files", payload)
        self.assertIn("state_ledger", payload)

    def test_product_docs_reads_executable_workflow_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = os.path.join(tempdir, "EXECUTABLE-WORKFLOWS.md")
            output = os.path.join(tempdir, "out.md")
            with open(source, "w") as f:
                f.write("# Workflows\n\n## Fleet Apply\n\n```bash\nsmu fleet apply\n```\n")

            payload = smu.product_docs_payload(output, source)

        self.assertEqual(payload["workflows"], ["Fleet Apply"])


if __name__ == "__main__":
    unittest.main()
