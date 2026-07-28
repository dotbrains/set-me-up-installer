#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
