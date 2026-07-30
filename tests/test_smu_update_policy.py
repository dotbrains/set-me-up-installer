#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuUpdatePolicy(unittest.TestCase):
    def test_policy_command_sets_scheduler_and_report_fields(self):
        with tempfile.TemporaryDirectory() as tempdir:
            policy_path = os.path.join(tempdir, "update-policy.json")
            with patch.object(smu, "update_policy_path", policy_path), \
                    patch.object(smu, "sys") as mock_sys:
                mock_sys.argv = [
                    "smu.py", "update", "policy",
                    "--report-url", "https://updates.example.com/smu",
                    "--min-interval-seconds", "3600",
                    "--backoff-seconds", "900",
                    "--history-limit", "3",
                    "--json",
                ]
                buf = io.StringIO()
                with redirect_stdout(buf), self.assertRaises(SystemExit) as raised:
                    smu.main()

        payload = json.loads(buf.getvalue())
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(payload["policy"]["report_url"], "https://updates.example.com/smu")
        self.assertEqual(payload["policy"]["min_interval_seconds"], 3600)
        self.assertEqual(payload["policy"]["backoff_seconds"], 900)
        self.assertEqual(payload["policy"]["history_limit"], 3)

    def test_policy_validation_rejects_unknown_and_insecure_fields(self):
        errors = smu.validate_update_policy({
            **smu.default_update_policy(),
            "report_url": "http://updates.example.com/smu",
            "history_limit": 0,
            "extra": True,
        })

        fields = {error["field"] for error in errors}
        self.assertEqual(fields, {"extra", "history_limit", "report_url"})

    def test_update_history_keeps_policy_limit(self):
        with tempfile.TemporaryDirectory() as tempdir:
            history_path = os.path.join(tempdir, "update-history.json")
            with patch.object(smu, "update_history_path", history_path), \
                    patch.object(smu, "read_update_policy", return_value={
                        **smu.default_update_policy(),
                        "history_limit": 2,
                    }), \
                    patch.object(smu, "_utc_timestamp", side_effect=[
                        "2026-07-29T00:00:00+00:00",
                        "2026-07-29T00:01:00+00:00",
                        "2026-07-29T00:02:00+00:00",
                    ]):
                smu.append_update_history({"theme": "gruvbox", "exit_code": 0})
                smu.append_update_history({"theme": "nord", "exit_code": 1})
                smu.append_update_history({"theme": "dracula", "exit_code": 0})
                history = smu.read_update_history()

        self.assertEqual([entry["theme"] for entry in history], ["nord", "dracula"])

    def test_report_alias_posts_when_policy_has_report_url(self):
        policy = {**smu.default_update_policy(), "report_url": "https://updates.example.com/smu"}
        with patch.object(smu, "read_update_policy", return_value=policy), \
                patch.object(smu, "validate_update_policy", return_value=[]), \
                patch.object(smu, "update_rate_limit_status", return_value={"status": "ready", "wait_seconds": 0}), \
                patch.object(smu, "read_update_history", return_value=[]), \
                patch.object(smu, "client_update_repository_status", return_value=[]), \
                patch.object(smu, "read_update_lock", return_value={}), \
                patch.object(smu, "config_drift_report", return_value={"drifted": False, "items": []}), \
                patch.object(smu, "current_theme", return_value="nord"), \
                patch.object(smu, "current_prompt", return_value="classic"), \
                patch.object(smu, "current_preset", return_value="default"), \
                patch.object(smu, "post_update_report", return_value={"status": "sent", "code": 204}) as post, \
                patch.object(smu, "sys") as mock_sys:
            mock_sys.argv = ["smu.py", "update", "--report", "--json"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                smu.main()

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["report_delivery"]["status"], "sent")
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
