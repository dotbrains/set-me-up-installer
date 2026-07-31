#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuOperabilityRuntime(unittest.TestCase):
    def test_help_topic_prints_new_command_usage(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = smu.print_help_topic("update preflight")

        self.assertEqual(exit_code, 0)
        self.assertIn("smu update preflight", buf.getvalue())

    def test_help_topic_prints_update_doctor_usage(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = smu.print_help_topic("update doctor")

        self.assertEqual(exit_code, 0)
        self.assertIn("smu update doctor", buf.getvalue())

    def test_contract_show_prints_json_contract(self):
        with patch.object(smu, "json_contracts", return_value={"doctor": {"updates": {"preflight": "passed"}}}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = smu.contract_command(["show", "doctor"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(buf.getvalue())["updates"]["preflight"], "passed")

    def test_contracts_include_provisioning_preflight_shape(self):
        with patch.object(smu, "status_report", return_value={}), \
                patch.object(smu, "repository_update_doctor", return_value={}), \
                patch.object(smu, "client_update_preflight", return_value={}):
            payload = smu.json_contracts()["provisioning-preflight"]

        self.assertEqual(payload["preflight"], "passed")
        self.assertEqual(payload["plan"]["kind"], "nix")
        self.assertIn("commands", payload["plan"])

    def test_contracts_include_adapter_capabilities_shape(self):
        with patch.object(smu, "status_report", return_value={}), \
                patch.object(smu, "repository_update_doctor", return_value={}), \
                patch.object(smu, "client_update_preflight", return_value={}):
            payload = smu.json_contracts()["provisioning-capabilities"]

        self.assertEqual(payload["contract"]["version"], 1)
        self.assertIn("provisioning.adapter", payload["contract"]["blueprint_keys"])
        self.assertIn("path", payload["contract"]["module_adapter_required_keys"])
        self.assertEqual(payload["adapters"][0]["id"], "rcm")

    def test_contracts_include_blueprint_readiness_shape(self):
        with patch.object(smu, "status_report", return_value={}), \
                patch.object(smu, "repository_update_doctor", return_value={}), \
                patch.object(smu, "client_update_preflight", return_value={}):
            payload = smu.json_contracts()["blueprint-ci-readiness"]

        self.assertTrue(payload["valid"])
        self.assertEqual(payload["readiness"]["preflight"], "passed")
        self.assertEqual(payload["readiness"]["summary"]["workflow_preflight"], 3)

    def test_contract_validate_accepts_runtime_contract(self):
        with patch.object(smu, "status_report", return_value={}), \
                patch.object(smu, "repository_update_doctor", return_value={}), \
                patch.object(smu, "client_update_preflight", return_value={}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = smu.contract_command(["validate", "provisioning-preflight"])

        self.assertEqual(exit_code, 0)
        self.assertIn("valid\tprovisioning-preflight", buf.getvalue())

    def test_contract_validate_reads_stdin_and_reports_json_errors(self):
        stdin = io.StringIO(json.dumps({
            "readiness": {
                "preflight": "passed",
                "summary": {
                    "provider_examples": 6,
                    "workflow_preflight": 2,
                },
            },
        }))
        buf = io.StringIO()
        with patch("sys.stdin", stdin), redirect_stdout(buf):
            exit_code = smu.contract_command(["validate", "blueprint-ci-readiness", "--path", "-", "--json"])

        payload = json.loads(buf.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["valid"])
        self.assertIn(
            "blueprint-ci-readiness.readiness.summary.workflow_preflight must be 3",
            payload["errors"],
        )

    def test_update_manifest_command_writes_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = os.path.join(tempdir, "manifest.json")
            with patch.object(smu, "update_manifest_payload", return_value={"schema_version": 1}):
                exit_code = smu.update_manifest_command(["manifest", "--output", output], json_output=False)
            with open(output) as f:
                payload = json.load(f)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], 1)

    def test_state_prune_dry_run_reports_candidates(self):
        with tempfile.TemporaryDirectory() as tempdir:
            schedule = os.path.join(tempdir, "update-schedule.json")
            with open(schedule, "w") as f:
                f.write("{}")
            with patch.object(smu, "update_schedule_path", schedule), \
                    patch.object(smu, "update_launchd_path", os.path.join(tempdir, "missing.plist")), \
                    patch.object(smu, "update_systemd_dir", os.path.join(tempdir, "systemd")), \
                    patch.object(smu, "catalog_cache_path", os.path.join(tempdir, "cache")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    exit_code = smu.state_prune(["--dry-run", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(json.loads(buf.getvalue())["dry_run"])

    def test_completion_command_outputs_shell_words(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = smu.completion_command(["bash"])

        self.assertEqual(exit_code, 0)
        self.assertIn("complete -W", buf.getvalue())
        self.assertIn("bootstrap", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
