from ..core import *


def blueprint_migration_pr_payload(root, mode="hybrid", adapter="hybrid"):
    root = os.path.abspath(os.path.expanduser(root))
    install_path = os.path.join(root, "dotfiles", "modules", "install.sh")
    workflow_path = os.path.join(root, ".github", "workflows", "set-me-up.yml")
    smu_path = os.path.join(root, "smu.toml")
    return {
        "root": root,
        "branch": f"set-me-up/{mode}-install-surface",
        "files": [
            {"path": smu_path, "exists": os.path.exists(smu_path)},
            {"path": install_path, "exists": os.path.exists(install_path)},
            {"path": workflow_path, "exists": os.path.exists(workflow_path)},
        ],
        "commands": [
            f"git checkout -b set-me-up/{mode}-install-surface",
            f"smu blueprint init --mode {mode} --adapter {adapter} --force",
            "smu blueprint ci --path . --check-docs --json",
            "smu conformance --repo . --markdown --output SET-ME-UP-CONFORMANCE.md",
        ],
        "pull_request": {
            "title": "Adopt set-me-up install surface",
            "body": "\n".join([
                "## Summary",
                "",
                "- Add smu.toml provisioning configuration",
                "- Add installer shim and CI contract validation",
                "- Publish conformance output for setup readiness",
                "",
                "## Validation",
                "",
                "- smu blueprint ci --path . --check-docs --json",
                "- smu conformance --repo . --json",
            ]),
        },
    }


def migration_pr_command(argv):
    root = _option_value(argv, "--repo") or _option_value(argv, "--root") or "."
    output = _option_value(argv, "--output")
    payload = blueprint_migration_pr_payload(
        root,
        mode=_option_value(argv, "--mode") or "hybrid",
        adapter=_option_value(argv, "--adapter") or "hybrid",
    )
    if output:
        write_json_file(output, payload)
        print(output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
