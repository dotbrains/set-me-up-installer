#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuState(unittest.TestCase):
    def test_state_ledger_round_trips_events(self):
        with tempfile.TemporaryDirectory() as tempdir:
            ledger = os.path.join(tempdir, "state", "ledger.json")
            with patch.object(smu, "state_dir", os.path.dirname(ledger)), \
                    patch.object(smu, "state_ledger_path", ledger), \
                    patch.object(smu, "_utc_timestamp", return_value="2026-07-28T00:00:00Z"):
                event = smu.record_state_event("provision_modules", [{"module": "base"}])

                self.assertEqual(event["operation"], "provision_modules")
                self.assertEqual(smu.last_state_event()["items"][0]["module"], "base")

    def test_file_snapshot_restores_overwritten_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = os.path.join(tempdir, "target.txt")
            with open(target, "w") as f:
                f.write("before")
            snapshot = smu.file_snapshot(target)
            with open(target, "w") as f:
                f.write("after")

            smu.restore_file_snapshot(snapshot)

            with open(target) as f:
                self.assertEqual(f.read(), "before")

    def test_rollback_materialized_adapters_restores_prior_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            ledger = os.path.join(tempdir, "state", "ledger.json")
            target = os.path.join(tempdir, "target.txt")
            with open(target, "w") as f:
                f.write("before")
            snapshot = smu.file_snapshot(target)
            with open(target, "w") as f:
                f.write("after")

            with patch.object(smu, "state_dir", os.path.dirname(ledger)), \
                    patch.object(smu, "state_ledger_path", ledger):
                smu.write_state_ledger([{
                    "id": "event",
                    "operation": "materialize_adapters",
                    "items": [{"before": snapshot}],
                }])

                self.assertTrue(smu.rollback_last_state_event())
                with open(target) as f:
                    self.assertEqual(f.read(), "before")
                self.assertEqual(smu.read_state_ledger(), [])

    def test_status_report_includes_modules_adapters_and_ledger(self):
        with tempfile.TemporaryDirectory() as tempdir:
            ledger = os.path.join(tempdir, "state", "ledger.json")
            adapter_manifest = os.path.join(tempdir, "adapters", "manifest.json")
            target = os.path.join(tempdir, "target.txt")
            os.makedirs(os.path.dirname(adapter_manifest))
            with open(target, "w"):
                pass
            with open(adapter_manifest, "w") as f:
                json.dump([{"name": "bash", "target": target}], f)

            with patch.object(smu, "state_dir", os.path.dirname(ledger)), \
                    patch.object(smu, "state_ledger_path", ledger), \
                    patch.object(smu, "adapter_manifest_json_path", adapter_manifest), \
                    patch.object(smu, "module_status_report", return_value=[{"name": "base"}]):
                smu.record_state_event("provision_modules", [{"module": "base"}])
                report = smu.status_report()

            self.assertEqual(report["modules"], [{"name": "base"}])
            self.assertTrue(report["adapters"][0]["exists"])
            self.assertEqual(report["ledger"]["entries"], 1)

    def test_status_subcommand_supports_json(self):
        with patch.object(smu, "print_status_json") as print_json, \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "status", "--json", "--search", "font"]

            smu.main()

        print_json.assert_called_once_with(search="font", show_all=False, verbose=False)

    def test_diff_subcommand_prints_module_and_adapter_plan(self):
        with patch.object(smu, "module_change_plan", return_value=[{"module": "base", "state": "missing", "change": "install"}]), \
                patch.object(smu, "materializable_adapters", return_value=[]), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "diff", "base"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.main()

        self.assertIn("install\tmodule\tbase\tmissing", buf.getvalue())

    def test_update_subcommand_supports_json_dry_run(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "--dry-run", "--json", "--validate"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as raised:
                    smu.main()

        payload = json.loads(buf.getvalue())
        self.assertEqual(raised.exception.code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertNotIn("self-update", payload["actions"])
        self.assertIn("doctor", payload["actions"])
        self.assertEqual(payload["theme"], "nord")

    def test_client_update_applies_refresh_steps(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "self_update") as self_update, \
                patch.object(smu, "update_submodules") as update_submodules, \
                patch.object(smu, "write_resolved_profile") as write_profile, \
                patch.object(smu, "materialize_adapters") as materialize, \
                patch.object(smu, "doctor", return_value=0) as doctor:
            exit_code = smu.client_update(validate=True)

        self.assertEqual(exit_code, 0)
        self_update.assert_not_called()
        update_submodules.assert_called_once_with()
        write_profile.assert_called_once_with()
        materialize.assert_called_once_with("nord", "classic", dry_run=False)
        doctor.assert_called_once_with()

    def test_client_update_self_applies_self_update(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "self_update") as self_update, \
                patch.object(smu, "update_submodules"), \
                patch.object(smu, "write_resolved_profile"), \
                patch.object(smu, "materialize_adapters"), \
                patch.object(smu, "doctor", return_value=0):
            exit_code = smu.client_update(validate=True, self_update_requested=True)

        self.assertEqual(exit_code, 0)
        self_update.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
