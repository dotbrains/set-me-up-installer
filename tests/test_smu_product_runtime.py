#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuProductRuntime(unittest.TestCase):
    def test_adapter_conflict_report_detects_unmanaged_target(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = os.path.join(tempdir, "source")
            target = os.path.join(tempdir, "target")
            with open(source, "w") as f:
                f.write("new")
            with open(target, "w") as f:
                f.write("old")
            entry = {"source": source, "target": target, "mode": "copy", "kind": "prompt", "name": "x"}

            with patch.object(smu, "materializable_adapters", return_value=[entry]):
                report = smu.adapter_conflict_report("gruvbox", "classic")

        self.assertTrue(report["conflicted"])
        self.assertEqual(report["items"][0]["status"], "conflict")

    def test_bootstrap_dry_run_json_outputs_plan(self):
        with patch.object(smu, "adapter_conflict_report", return_value={"conflicted": False, "items": []}), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "current_theme", return_value="gruvbox"), \
                patch.object(smu, "current_prompt", return_value="starship"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = smu.bootstrap(["--dry-run", "--json", "--theme", "nord"])

        payload = json.loads(buf.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["theme"], "nord")
        self.assertIn("baseline", payload["actions"])

    def test_catalog_trust_command_records_publisher(self):
        with tempfile.TemporaryDirectory() as tempdir:
            trust_path = os.path.join(tempdir, "catalog-trust.json")
            with patch.object(smu, "catalog_trust_path", trust_path), \
                    patch.object(smu, "_utc_timestamp", return_value="now"):
                smu.catalog_trust_command(["publisher", "dotbrains"], json_output=False)
                trust = smu.read_catalog_trust()

        self.assertIn("dotbrains", trust["trusted_publishers"])

    def test_rollback_preview_reports_restore_targets(self):
        with patch.object(smu, "last_state_event", return_value={
                "operation": "materialize_adapters",
                "items": [{"before": {"path": "/tmp/config", "exists": True}}],
        }):
            preview = smu.rollback_preview()

        self.assertEqual(preview["changes"][0]["path"], "/tmp/config")
        self.assertTrue(preview["changes"][0]["restore"])

    def test_doctor_json_uses_health_report(self):
        with patch.object(smu, "health_report", return_value={
                "preset": {"valid": True},
                "theme": {"valid": True},
                "prompt": {"valid": True},
                "catalogs": {"errors": []},
                "adapters": {"conflicted": False},
                "updates": {"preflight": "passed"},
        }):
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = smu.print_doctor_json()

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(buf.getvalue())["updates"]["preflight"], "passed")

    def test_catalog_package_writes_optional_publisher(self):
        with tempfile.TemporaryDirectory() as tempdir:
            manifest = os.path.join(tempdir, "catalogs", "prompt-profiles", "work.toml")
            os.makedirs(os.path.dirname(manifest))
            with open(manifest, "w") as f:
                f.write("schema_version = 1\nid = \"work\"\nname = \"Work\"\n")
            output = os.path.join(tempdir, "work.smu-pack")

            with patch.object(smu, "prompt_catalog_path", os.path.dirname(manifest)), \
                    patch.dict(os.environ, {"SMU_CATALOG_PUBLISHER": "dotbrains"}):
                smu.catalog_package("work", output=output, force=False)

            pack = smu._read_simple_toml(os.path.join(output, "pack.toml"))

        self.assertEqual(pack["publisher"], "dotbrains")


if __name__ == "__main__":
    unittest.main()
