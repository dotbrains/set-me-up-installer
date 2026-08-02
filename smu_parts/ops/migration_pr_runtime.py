from ..core import *


def _migration_smu_toml(mode, adapter):
    if mode == "nix" and adapter == "hybrid":
        adapter = "home-manager"
    lines = ["[provisioning]", f'mode = "{mode}"', f'adapter = "{adapter}"']
    if mode == "hybrid":
        lines.append('nix_adapter = "home-manager"')
    lines.extend(["", "[profile.default]", 'modules = ["base"]', ""])
    return "\n".join(lines)


def _migration_install_sh():
    return "\n".join([
        "#!/bin/bash",
        "",
        'export SMU_BLUEPRINT=${SMU_BLUEPRINT:-"${GITHUB_REPOSITORY:-dotbrains/set-me-up-blueprint}"}',
        'export SMU_BLUEPRINT_BRANCH=${SMU_BLUEPRINT_BRANCH:-"main"}',
        'export SMU_SUBMODULE_SCOPE=${SMU_SUBMODULE_SCOPE:-"platform"}',
        "",
        'bash <(curl -s -L https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh) "$@"',
        "",
    ])


def downstream_conformance_workflow_template():
    return "\n".join([
        "name: set-me-up conformance",
        "",
        "on:",
        "  pull_request:",
        "  push:",
        "    branches: [main, master]",
        "",
        "jobs:",
        "  conformance:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v5",
        "      - name: Checkout installer",
        "        run: git clone --depth 1 https://github.com/dotbrains/set-me-up-installer set-me-up-installer",
        "      - name: Validate blueprint",
        "        # smu blueprint ci --path . --check-docs --json",
        "        run: python3 set-me-up-installer/smu.py blueprint ci --path . --check-docs --json",
        "      - name: Validate conformance",
        "        # smu conformance --repo . --json",
        "        run: python3 set-me-up-installer/smu.py conformance --repo . --json",
        "",
    ])


def _conformance_badge():
    return "\n".join([
        "# set-me-up conformance",
        "",
        "Run this in CI to refresh the generated readiness payload:",
        "",
        "```bash",
        "smu conformance --repo . --json",
        "```",
        "",
    ])


def blueprint_migration_pr_payload(root, mode="hybrid", adapter="hybrid", include_ci_template=False, include_badge=False):
    root = os.path.abspath(os.path.expanduser(root))
    install_path = os.path.join(root, "dotfiles", "modules", "install.sh")
    workflow_path = os.path.join(root, ".github", "workflows", "set-me-up.yml")
    smu_path = os.path.join(root, "smu.toml")
    conformance_path = os.path.join(root, "SET-ME-UP-CONFORMANCE.md")
    files = [
        {"path": smu_path, "exists": os.path.exists(smu_path), "content": _migration_smu_toml(mode, adapter)},
        {"path": install_path, "exists": os.path.exists(install_path), "content": _migration_install_sh()},
    ]
    if include_ci_template:
        files.append({"path": workflow_path, "exists": os.path.exists(workflow_path), "content": downstream_conformance_workflow_template()})
    else:
        files.append({"path": workflow_path, "exists": os.path.exists(workflow_path)})
    if include_badge:
        files.append({"path": conformance_path, "exists": os.path.exists(conformance_path), "content": _conformance_badge()})
    return {
        "root": root,
        "branch": f"set-me-up/{mode}-install-surface",
        "files": files,
        "ci_template": downstream_conformance_workflow_template() if include_ci_template else "",
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


def apply_migration_pr_payload(root, mode="hybrid", adapter="hybrid", dry_run=True, include_ci_template=False, include_badge=False):
    payload = blueprint_migration_pr_payload(
        root,
        mode=mode,
        adapter=adapter,
        include_ci_template=include_ci_template,
        include_badge=include_badge,
    )
    planned = []
    for item in payload["files"]:
        if "content" not in item:
            continue
        planned.append({"action": "write", "path": item["path"], "exists": item["exists"]})
        if not dry_run:
            os.makedirs(os.path.dirname(item["path"]), exist_ok=True)
            with open(item["path"], "w") as f:
                f.write(item["content"])
            if item["path"].endswith("install.sh"):
                os.chmod(item["path"], 0o755)
    payload["dry_run"] = dry_run
    payload["planned"] = planned
    return payload


def migration_pr_command(argv):
    root = _option_value(argv, "--repo") or _option_value(argv, "--root") or "."
    output = _option_value(argv, "--output")
    apply_files = "--apply" in argv
    dry_run = "--dry-run" in argv or not apply_files
    payload = apply_migration_pr_payload(
        root,
        mode=_option_value(argv, "--mode") or "hybrid",
        adapter=_option_value(argv, "--adapter") or "hybrid",
        dry_run=dry_run,
        include_ci_template="--ci-template" in argv,
        include_badge="--badge" in argv,
    )
    if output:
        write_json_file(output, payload)
        print(output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
