#!/usr/bin/env python3

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import smu


class TestVpsTools(unittest.TestCase):
    def test_dotfiles_compatibility_contract_detects_vps_ready_repo(self):
        with tempfile.TemporaryDirectory() as tempdir:
            os.makedirs(os.path.join(tempdir, "dotfiles", "modules"))
            os.makedirs(os.path.join(tempdir, ".github", "workflows"))
            with open(os.path.join(tempdir, "dotfiles", "modules", "install.sh"), "w") as f:
                f.write('export SMU_BLUEPRINT=${SMU_BLUEPRINT:-"owner/dotfiles"}\n')
                f.write('export SMU_SUBMODULE_SCOPE=${SMU_SUBMODULE_SCOPE:-"platform"}\n')
            with open(os.path.join(tempdir, "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "hybrid"\nadapter = "hybrid"\nnix_adapter = "home-manager"\n')
            with open(os.path.join(tempdir, ".github", "workflows", "set-me-up.yml"), "w") as f:
                f.write("run: smu blueprint dotfiles-contract --repo . --json\n")

            payload = smu.dotfiles_compatibility_contract(root=tempdir)

            self.assertTrue(payload["valid"])
            self.assertTrue(payload["readiness"]["vps_ready"])
            self.assertTrue(payload["readiness"]["hybrid_ready"])

    def test_migrate_dotfiles_repo_generates_install_surface(self):
        with tempfile.TemporaryDirectory() as tempdir:
            result = smu.migrate_dotfiles_repo(
                tempdir,
                mode="hybrid",
                blueprint="owner/dotfiles",
                json_output=False,
            )

            self.assertEqual(result, 0)
            with open(os.path.join(tempdir, "dotfiles", "modules", "install.sh")) as f:
                shim = f.read()
            with open(os.path.join(tempdir, "smu.toml")) as f:
                config = f.read()
            self.assertIn("SMU_BLUEPRINT", shim)
            self.assertIn("SMU_SUBMODULE_SCOPE", shim)
            self.assertIn('mode = "hybrid"', config)
            self.assertTrue(os.path.exists(os.path.join(tempdir, ".github", "workflows", "set-me-up.yml")))

    def test_vps_plan_includes_debian_prerequisites_and_lifecycle(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = smu.vps_plan(target="debian", mode="nix", json_output=True)

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertIn("apt-get install", payload["commands"]["prerequisites"])
        self.assertIn("--plan", payload["commands"]["plan"])
        self.assertIn("rollback", payload["commands"])
        self.assertEqual(payload["adapter"], "home-manager")

    def test_dotfiles_compatibility_contract_schema_validates_example(self):
        contract = smu.json_contracts()["dotfiles-compatibility"]

        errors = smu.smu_contract.json_contract_errors("dotfiles-compatibility", contract)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
