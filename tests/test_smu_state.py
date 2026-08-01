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

    def test_rollback_to_event_preserves_other_events(self):
        with tempfile.TemporaryDirectory() as tempdir:
            ledger = os.path.join(tempdir, "state", "ledger.json")
            first = os.path.join(tempdir, "first.txt")
            second = os.path.join(tempdir, "second.txt")
            for path in (first, second):
                with open(path, "w") as f:
                    f.write("before")
            first_snapshot = smu.file_snapshot(first)
            second_snapshot = smu.file_snapshot(second)
            for path in (first, second):
                with open(path, "w") as f:
                    f.write("after")

            with patch.object(smu, "state_dir", os.path.dirname(ledger)), \
                    patch.object(smu, "state_ledger_path", ledger):
                smu.write_state_ledger([
                    {"id": "first", "operation": "materialize_adapters", "items": [{"before": first_snapshot}]},
                    {"id": "second", "operation": "client_update", "items": [{"before": second_snapshot}]},
                ])

                self.assertTrue(smu.rollback_state_event(event_id="first"))
                with open(first) as f:
                    self.assertEqual(f.read(), "before")
                with open(second) as f:
                    self.assertEqual(f.read(), "after")
                self.assertEqual([event["id"] for event in smu.read_state_ledger()], ["second"])

    def test_rollback_client_update_restores_generated_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            ledger = os.path.join(tempdir, "state", "ledger.json")
            resolved = os.path.join(tempdir, "resolved.env")
            adapter_manifest = os.path.join(tempdir, "manifest.json")
            target = os.path.join(tempdir, "target.txt")
            for path in (resolved, adapter_manifest, target):
                with open(path, "w") as f:
                    f.write("before")
            items = [
                {"before": smu.file_snapshot(resolved)},
                {"before": smu.file_snapshot(adapter_manifest)},
                {"before": smu.file_snapshot(target)},
            ]
            for path in (resolved, adapter_manifest, target):
                with open(path, "w") as f:
                    f.write("after")

            with patch.object(smu, "state_dir", os.path.dirname(ledger)), \
                    patch.object(smu, "state_ledger_path", ledger):
                smu.write_state_ledger([{
                    "id": "event",
                    "operation": "client_update",
                    "items": items,
                }])

                self.assertTrue(smu.rollback_last_state_event())

            for path in (resolved, adapter_manifest, target):
                with open(path) as f:
                    self.assertEqual(f.read(), "before")

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

    def test_status_report_includes_update_lock(self):
        with tempfile.TemporaryDirectory() as tempdir:
            lock_path = os.path.join(tempdir, "update.lock")
            with open(lock_path, "w") as f:
                json.dump({"theme": "nord"}, f)

            with patch.object(smu, "update_lock_path", lock_path), \
                    patch.object(smu, "module_status_report", return_value=[]), \
                    patch.object(smu, "_read_adapter_manifest", return_value=[]), \
                    patch.object(smu, "read_state_ledger", return_value=[]), \
                    patch.object(smu, "last_state_event", return_value=None), \
                    patch.object(smu, "config_drift_report", return_value={"drifted": False, "items": []}):
                report = smu.status_report()

            self.assertEqual(report["updates"]["last"]["theme"], "nord")
            self.assertEqual(report["updates"]["policy"]["ref"], None)
            self.assertFalse(report["updates"]["config_drift"]["drifted"])

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
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "client_update_repository_status", return_value=[]), \
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
        self.assertEqual(payload["preset"], "default")

    def test_update_check_reports_available_updates(self):
        with patch.object(smu, "client_update_repository_status", return_value=[{
                "name": "smu_home",
                "path": "/tmp/smu",
                "head": "abc",
                "branch": "main",
                "status": "behind",
                "ahead": 0,
                "behind": 2,
        }]), \
                patch.object(smu, "read_update_lock", return_value={}), \
                patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "--check", "--json"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.main()

        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["updates_available"])
        self.assertEqual(payload["repositories"][0]["behind"], 2)

    def test_update_report_alias_outputs_fleet_report(self):
        with patch.object(smu, "client_update_repository_status", return_value=[]), \
                patch.object(smu, "read_update_lock", return_value={}), \
                patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "config_drift_report", return_value={"drifted": False, "items": []}), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "--report", "--json"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.main()

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["theme"], "nord")
        self.assertFalse(payload["updates_available"])

    def test_update_baseline_writes_current_fingerprints(self):
        with tempfile.TemporaryDirectory() as tempdir:
            generated = os.path.join(tempdir, "resolved.env")
            lock_path = os.path.join(tempdir, "update.lock")
            with open(generated, "w") as f:
                f.write("current")

            with patch.object(smu, "update_lock_path", lock_path), \
                    patch.object(smu, "generated_config_paths", return_value=[generated]), \
                    patch.object(smu, "client_update_repository_status", return_value=[]), \
                    patch.object(smu, "current_theme", return_value="nord"), \
                    patch.object(smu, "current_prompt", return_value="classic"), \
                    patch.object(smu, "current_preset", return_value="default"), \
                    patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()):
                exit_code = smu.client_update_baseline(json_output=False)
                drifted = smu.config_drift_report()["drifted"]

            self.assertEqual(exit_code, 0)
            self.assertFalse(drifted)

    def test_update_policy_command_persists_policy(self):
        with tempfile.TemporaryDirectory() as tempdir:
            policy_path = os.path.join(tempdir, "update-policy.json")
            with patch.object(smu, "update_policy_path", policy_path), \
                    patch.object(smu, "sys") as mock_sys:
                mock_sys.argv = [
                    "smu.py", "update", "policy", "--set-ref", "stable",
                    "--require-signed", "--validate", "--json",
                ]
                buf = io.StringIO()
                with redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as raised:
                        smu.main()

            payload = json.loads(buf.getvalue())
            self.assertEqual(raised.exception.code, 0)
            self.assertEqual(payload["policy"]["ref"], "stable")
            self.assertTrue(payload["policy"]["require_signed"])
            self.assertTrue(payload["policy"]["validate"])

    def test_update_policy_json_is_read_only(self):
        with patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "write_update_policy") as write_policy:
            policy = smu.update_policy_from_args(["policy", "--json"])

        self.assertEqual(policy["ref"], None)
        write_policy.assert_not_called()

    def test_update_policy_doctor_reports_policy_health(self):
        with patch.object(smu, "update_policy_doctor", return_value={
                "policy": {},
                "report": {},
                "checks": [{"name": "config_drift", "status": "passed"}],
        }), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "policy", "doctor", "--json"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as raised:
                    smu.main()

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(json.loads(buf.getvalue())["checks"][0]["status"], "passed")

    def test_update_doctor_reports_repository_health(self):
        with patch.object(smu, "repository_update_doctor", return_value={
                "repositories": [{"name": "blueprint", "update_status": "current", "dirty": False}],
                "submodules": {"gitmodules": True},
        }), \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "doctor", "--json"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as raised:
                    smu.main()

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(json.loads(buf.getvalue())["repositories"][0]["name"], "blueprint")

    def test_config_drift_report_detects_changed_generated_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            generated = os.path.join(tempdir, "resolved.env")
            with open(generated, "w") as f:
                f.write("before")
            previous = smu.file_sha256(generated)
            with open(generated, "w") as f:
                f.write("after")

            with patch.object(smu, "read_update_lock", return_value={
                    "generated_config": [{
                        "path": generated,
                        "exists": True,
                        "sha256": previous,
                    }],
                }), \
                    patch.object(smu, "generated_config_paths", return_value=[generated]):
                report = smu.config_drift_report()

        self.assertTrue(report["drifted"])
        self.assertEqual(report["items"][0]["status"], "changed")

    def test_client_update_applies_refresh_steps(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "client_update_repository_status", side_effect=[[], []]), \
                patch.object(smu, "self_update") as self_update, \
                patch.object(smu, "update_submodules") as update_submodules, \
                patch.object(smu, "write_resolved_profile") as write_profile, \
                patch.object(smu, "materialize_adapters") as materialize, \
                patch.object(smu, "client_update_snapshots", return_value=[{"before": {"exists": False, "path": "/tmp/generated"}}]), \
                patch.object(smu, "collapse_materialize_event", return_value=[]), \
                patch.object(smu, "generated_config_fingerprints", return_value=[]), \
                patch.object(smu, "record_state_event") as record_event, \
                patch.object(smu, "doctor", return_value=0) as doctor, \
                patch.object(smu, "write_update_lock") as write_lock:
            exit_code = smu.client_update(validate=True)

        self.assertEqual(exit_code, 0)
        self_update.assert_not_called()
        update_submodules.assert_called_once_with()
        write_profile.assert_called_once_with()
        materialize.assert_called_once_with("nord", "classic", dry_run=False)
        doctor.assert_called_once_with()
        write_lock.assert_called_once()
        record_event.assert_called_once()

    def test_client_update_self_applies_self_update(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "client_update_repository_status", side_effect=[[], []]), \
                patch.object(smu, "self_update") as self_update, \
                patch.object(smu, "update_submodules"), \
                patch.object(smu, "write_resolved_profile"), \
                patch.object(smu, "materialize_adapters"), \
                patch.object(smu, "doctor", return_value=0), \
                patch.object(smu, "write_update_lock"):
            exit_code = smu.client_update(validate=True, self_update_requested=True)

        self.assertEqual(exit_code, 0)
        self_update.assert_called_once_with()

    def test_client_update_ref_checks_out_ref(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "client_update_repository_status", side_effect=[[], []]), \
                patch.object(smu, "checkout_client_update_ref", return_value=[{"status": "checked-out"}]) as checkout_ref, \
                patch.object(smu, "update_submodules"), \
                patch.object(smu, "write_resolved_profile"), \
                patch.object(smu, "materialize_adapters"), \
                patch.object(smu, "write_update_lock"):
            exit_code = smu.client_update(ref="stable")

        self.assertEqual(exit_code, 0)
        checkout_ref.assert_called_once_with("stable")

    def test_client_update_ref_failure_stops_update(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "client_update_repository_status", return_value=[]), \
                patch.object(smu, "checkout_client_update_ref", return_value=[{"status": "failed"}]), \
                patch.object(smu, "update_submodules") as update_submodules, \
                patch.object(smu, "write_update_lock") as write_lock:
            exit_code = smu.client_update(ref="missing")

        self.assertEqual(exit_code, 1)
        update_submodules.assert_not_called()
        write_lock.assert_called_once()

    def test_client_update_require_signed_stops_unverified_update(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value=smu.default_update_policy()), \
                patch.object(smu, "client_update_repository_status", side_effect=[
                    [],
                    [{"name": "smu_home", "signature": "unverified"}],
                ]), \
                patch.object(smu, "checkout_client_update_ref", return_value=[]), \
                patch.object(smu, "update_submodules") as update_submodules, \
                patch.object(smu, "write_update_lock") as write_lock:
            exit_code = smu.client_update(require_signed=True)

        self.assertEqual(exit_code, 1)
        update_submodules.assert_not_called()
        write_lock.assert_called_once()

    def test_client_update_uses_policy_defaults(self):
        with patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "read_update_policy", return_value={
                    "ref": "stable",
                    "require_signed": True,
                    "validate": True,
                    "auto_apply": False,
                    "schedule": None,
                }), \
                patch.object(smu, "client_update_repository_status", side_effect=[
                    [], [{"name": "smu_home", "signature": "verified"}], []
                ]), \
                patch.object(smu, "checkout_client_update_ref", return_value=[]) as checkout_ref, \
                patch.object(smu, "update_submodules"), \
                patch.object(smu, "write_resolved_profile"), \
                patch.object(smu, "materialize_adapters"), \
                patch.object(smu, "doctor", return_value=0) as doctor, \
                patch.object(smu, "write_update_lock"), \
                patch.object(smu, "record_state_event"):
            exit_code = smu.client_update()

        self.assertEqual(exit_code, 0)
        checkout_ref.assert_called_once_with("stable")
        doctor.assert_called_once_with()

    def test_update_rollback_uses_state_ledger(self):
        with patch.object(smu, "rollback_last_state_event", return_value=True) as rollback, \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "--rollback", "--dry-run"]

            with self.assertRaises(SystemExit) as raised:
                smu.main()

        self.assertEqual(raised.exception.code, 0)
        rollback.assert_called_once_with(dry_run=True)


if __name__ == "__main__":
    unittest.main()
