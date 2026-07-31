#!/usr/bin/env python3

import os
import tempfile
import unittest

import smu


def write_provider_example(root, provider, mode, adapter, nix_adapter=None):
    provider_dir = os.path.join(root, "examples", "providers", provider)
    os.makedirs(provider_dir)
    with open(os.path.join(provider_dir, "smu.toml"), "w") as f:
        f.write("[provisioning]\n")
        f.write(f'mode = "{mode}"\n')
        f.write(f'adapter = "{adapter}"\n')
        if nix_adapter:
            f.write(f'nix_adapter = "{nix_adapter}"\n')


class TestBlueprintRecommendations(unittest.TestCase):
    def test_blueprint_provider_recommendation_uses_provider_matrix(self):
        with tempfile.TemporaryDirectory() as tempdir:
            os.makedirs(os.path.join(tempdir, "examples", "providers", "ubuntu-vps"))
            with open(os.path.join(tempdir, "examples", "providers", "ubuntu-vps", "smu.toml"), "w") as f:
                f.write('[provisioning]\nmode = "nix"\nadapter = "home-manager"\n')

            payload = smu.blueprint_provider_recommendation(target="ubuntu", root=tempdir)

            self.assertTrue(payload["valid"])
            self.assertEqual(payload["recommendation"]["provider"], "ubuntu-vps")
            self.assertEqual(payload["recommendation"]["adapter"], "home-manager")
            self.assertTrue(payload["recommendation"]["capability"]["requires_nix"])

    def test_blueprint_provider_recommendation_supports_rcm_only(self):
        payload = smu.blueprint_provider_recommendation(target="rcm-only")

        self.assertTrue(payload["valid"])
        self.assertEqual(payload["recommendation"]["mode"], "rcm")
        self.assertEqual(payload["recommendation"]["adapter"], "rcm")
        self.assertFalse(payload["recommendation"]["capability"]["requires_nix"])

    def test_blueprint_provider_recommendation_rejects_unknown_target(self):
        payload = smu.blueprint_provider_recommendation(target="solaris")

        self.assertFalse(payload["valid"])
        self.assertIn("unknown target 'solaris'", payload["errors"][0])

    def test_blueprint_recommendation_config_renders_target(self):
        payload = smu.blueprint_provider_recommendation(target="rcm-only")

        content = smu.blueprint_recommendation_config(payload["recommendation"])

        self.assertIn('mode = "rcm"', content)
        self.assertIn('adapter = "rcm"', content)
        self.assertIn("[profile.default]", content)

    def test_write_blueprint_recommendation_config_writes_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = os.path.join(tempdir, "smu.toml")

            result = smu.write_blueprint_recommendation_config(
                target="rcm-only",
                root=tempdir,
                output_path=output_path,
                json_output=False,
            )

            self.assertEqual(result, 0)
            with open(output_path) as f:
                content = f.read()
            self.assertIn('mode = "rcm"', content)

    def test_write_blueprint_recommendation_config_requires_force(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = os.path.join(tempdir, "smu.toml")
            with open(output_path, "w") as f:
                f.write("existing")

            result = smu.write_blueprint_recommendation_config(
                target="rcm-only",
                root=tempdir,
                output_path=output_path,
                json_output=False,
            )

            self.assertEqual(result, 1)
            with open(output_path) as f:
                self.assertEqual(f.read(), "existing")

    def test_validate_recommendation_config_accepts_generated_targets(self):
        for target in ("rcm-only", "ubuntu", "nixos", "macos", "digitalocean"):
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as tempdir:
                    if target == "ubuntu":
                        write_provider_example(tempdir, "ubuntu-vps", "nix", "home-manager")
                    if target == "nixos":
                        write_provider_example(tempdir, "nixos-vps", "nix", "nixos")
                    if target == "digitalocean":
                        write_provider_example(tempdir, "digitalocean-droplet", "hybrid", "hybrid", "home-manager")
                    output_path = os.path.join(tempdir, "smu.toml")
                    self.assertEqual(
                        smu.write_blueprint_recommendation_config(
                            target=target,
                            root=tempdir,
                            output_path=output_path,
                            json_output=False,
                        ),
                        0,
                    )

                    result = smu.validate_blueprint_recommendation_config(
                        target=target,
                        root=tempdir,
                        input_path=output_path,
                    )

                    self.assertEqual(result, 0)

    def test_validate_recommendation_config_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = os.path.join(tempdir, "smu.toml")
            with open(output_path, "w") as f:
                f.write('[provisioning]\nmode = "rcm"\nadapter = "rcm"\n')

            result = smu.validate_blueprint_recommendation_config(
                target="ubuntu",
                root=tempdir,
                input_path=output_path,
            )

            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
