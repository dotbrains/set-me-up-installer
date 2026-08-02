#!/usr/bin/env python3

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

import smu


class TestSmuSafetyRuntime(unittest.TestCase):
    def test_runtime_lock_rejects_concurrent_holder(self):
        with tempfile.TemporaryDirectory() as tempdir:
            lock_path = os.path.join(tempdir, "runtime.lock")
            with patch.object(smu, "runtime_lock_path", lock_path), \
                    patch.object(smu, "config_dir", tempdir):
                with smu.runtime_lock("outer"):
                    with self.assertRaises(SystemExit):
                        with smu.runtime_lock("inner"):
                            pass

    def test_locked_call_returns_callback_value(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(smu, "runtime_lock_path", os.path.join(tempdir, "runtime.lock")), \
                    patch.object(smu, "config_dir", tempdir):
                self.assertEqual(smu.locked_call("test", lambda: 7), 7)

    def test_materialize_copy_replaces_target_atomically(self):
        with tempfile.TemporaryDirectory() as tempdir:
            source = os.path.join(tempdir, "source")
            target = os.path.join(tempdir, "target")
            with open(source, "w") as f:
                f.write("after")
            with open(target, "w") as f:
                f.write("before")
            entry = {
                "kind": "prompt",
                "manifest_id": "work",
                "name": "bash",
                "mode": "copy",
                "source": source,
                "target": target,
            }
            with patch.object(smu, "materializable_adapters", return_value=[entry]), \
                    patch.object(smu, "_write_adapter_manifest"), \
                    patch.object(smu, "record_state_event"):
                smu.materialize_adapters("gruvbox", "classic", force=True)

            with open(target) as f:
                self.assertEqual(f.read(), "after")

    def test_static_contract_examples_parse(self):
        contract_dir = os.path.join(smu.installer_root, "docs", "json-contracts")
        for root, _, filenames in os.walk(contract_dir):
            for filename in filenames:
                if filename.endswith(".json"):
                    with open(os.path.join(root, filename)) as f:
                        self.assertIsInstance(json.load(f), dict)

    def test_static_contract_examples_ignore_non_json(self):
        contract_dir = os.path.join(smu.installer_root, "docs", "json-contracts")
        for filename in os.listdir(contract_dir):
            if filename.endswith(".json"):
                with open(os.path.join(contract_dir, filename)) as f:
                    self.assertIsInstance(json.load(f), dict)

    def test_documented_modern_commands_are_discoverable(self):
        checks = [
            ["bootstrap"],
            ["catalog", "trust"],
            ["update", "preflight"],
            ["update", "doctor"],
            ["update", "schedule"],
            ["rollback"],
            ["contracts"],
            ["completion"],
            ["state", "prune"],
            ["manifest"],
        ]
        for topic in checks:
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(smu.print_help_topic(topic), 0)
            self.assertIn("smu", buf.getvalue())

    def test_contracts_include_update_doctor(self):
        with patch.object(smu, "repository_update_doctor", return_value={"repositories": []}), \
                patch.object(smu, "status_report", return_value={}), \
                patch.object(smu, "client_update_preflight", return_value={}):
            self.assertIn("update-doctor", smu.json_contracts())


if __name__ == "__main__":
    unittest.main()
