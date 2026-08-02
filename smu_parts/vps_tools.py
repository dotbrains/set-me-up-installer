from .core import *


VPS_TARGETS = {
    "ubuntu": {
        "platform": "ubuntu",
        "prerequisites": ["bash", "curl", "git", "ca-certificates"],
        "install": "sudo apt-get update && sudo apt-get install -y bash curl git ca-certificates",
        "adapter": "home-manager",
    },
    "debian": {
        "platform": "debian",
        "prerequisites": ["bash", "curl", "git", "ca-certificates"],
        "install": "sudo apt-get update && sudo apt-get install -y bash curl git ca-certificates",
        "adapter": "home-manager",
    },
    "arch": {
        "platform": "arch",
        "prerequisites": ["bash", "curl", "git", "ca-certificates"],
        "install": "sudo pacman -Sy --needed bash curl git ca-certificates",
        "adapter": "home-manager",
    },
    "nixos": {
        "platform": "nixos",
        "prerequisites": ["bash", "curl", "git", "nix"],
        "install": "nix-shell -p bash curl git",
        "adapter": "nixos",
    },
}


def _dotfiles_install_shim_path(root):
    return os.path.join(root, "dotfiles", "modules", "install.sh")


def _read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read()


def _write_if_needed(path, content, force=False):
    if os.path.exists(path) and not force:
        return {"path": path, "changed": False, "reason": "exists"}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return {"path": path, "changed": True, "reason": "written"}


def _shell_shim_content(blueprint, branch, scope):
    return "\n".join([
        "#!/bin/bash",
        "",
        f'export SMU_BLUEPRINT=${{SMU_BLUEPRINT:-"{blueprint}"}}',
        f'export SMU_BLUEPRINT_BRANCH=${{SMU_BLUEPRINT_BRANCH:-"{branch}"}}',
        f'export SMU_SUBMODULE_SCOPE=${{SMU_SUBMODULE_SCOPE:-"{scope}"}}',
        'export SMU_IGNORED_PATHS="${SMU_IGNORED_PATHS:-""}"',
        "",
        'bash <(curl -s -L https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh) "$@"',
        "",
    ])


def _smu_toml_content(mode):
    return _blueprint_mode_config(mode).replace('modules = ["example"]', 'modules = ["base"]')


def _compat_workflow_content(adapter):
    return "\n".join([
        "name: set-me-up",
        "",
        "on:",
        "  pull_request:",
        "  push:",
        "    branches: [main]",
        "",
        "jobs:",
        "  contract:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        "      - uses: actions/setup-python@v7.0.0",
        "        with:",
        "          python-version: '3.x'",
        "      - name: Validate set-me-up surface",
        "        run: |",
        "          python3 set-me-up-installer/smu.py blueprint dotfiles-contract --repo . --json",
        f"          python3 set-me-up-installer/smu.py provisioning-adapter preflight --adapter {adapter} --profile default --json",
        "",
    ])


def dotfiles_compatibility_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dotbrains.github.io/set-me-up/schemas/dotfiles-compatibility.schema.json",
        "title": "set-me-up dotfiles compatibility contract",
        "type": "object",
        "required": ["contract", "valid", "checks", "readiness"],
        "properties": {
            "contract": {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"const": "dotfiles-compatibility"},
                    "version": {"type": "integer", "minimum": 1},
                },
            },
            "path": {"type": "string"},
            "valid": {"type": "boolean"},
            "mode": {"type": ["string", "null"]},
            "adapter": {"type": ["string", "null"]},
            "readiness": {"type": "object"},
            "checks": {"type": "array", "items": {"type": "object"}},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": True,
    }


def dotfiles_compatibility_contract(root=None):
    root = os.path.abspath(root or smu_home_dir)
    checks = []
    errors = []
    shim_path = _dotfiles_install_shim_path(root)
    shim = _read_text(shim_path)
    config_path = os.path.join(root, "smu.toml")
    manifest = smu_contract.read_manifest(config_path) if os.path.exists(config_path) else {}
    mode_errors = _blueprint_mode_errors(manifest, path="smu.toml") if manifest else ["smu.toml: missing"]
    provisioning = manifest.get("provisioning", {}) if isinstance(manifest, dict) else {}
    mode = provisioning.get("mode") if isinstance(provisioning, dict) else None
    adapter = provisioning.get("adapter") if isinstance(provisioning, dict) else None
    readiness = {
        "install_shim": bool(shim),
        "smu_blueprint": "SMU_BLUEPRINT" in shim,
        "platform_scope": "SMU_SUBMODULE_SCOPE" in shim and "platform" in shim,
        "root_config": os.path.exists(config_path),
        "rcm_ready": mode == "rcm" and adapter == "rcm",
        "nix_ready": mode == "nix" and adapter in BLUEPRINT_NIX_ADAPTERS,
        "hybrid_ready": mode == "hybrid" and adapter == "hybrid",
        "vps_ready": adapter in ("home-manager", "nixos", "hybrid") and "SMU_SUBMODULE_SCOPE" in shim,
        "ci_contract": False,
    }
    workflows_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(workflows_dir):
        for filename in os.listdir(workflows_dir):
            if not filename.endswith((".yml", ".yaml")):
                continue
            workflow_text = _read_text(os.path.join(workflows_dir, filename))
            if "dotfiles-contract" in workflow_text or "provisioning-adapter preflight" in workflow_text:
                readiness["ci_contract"] = True
                break
    required = {
        "install-shim": readiness["install_shim"],
        "smu-blueprint": readiness["smu_blueprint"],
        "platform-scope": readiness["platform_scope"],
        "root-smu-toml": readiness["root_config"] and not mode_errors,
        "ci-contract": readiness["ci_contract"],
    }
    for name, ok in required.items():
        checks.append({"name": name, "ok": ok})
        if not ok:
            errors.append(f"{name}: missing or invalid")
    errors.extend(mode_errors)
    return {
        "contract": {"name": "dotfiles-compatibility", "version": 1},
        "path": root,
        "valid": not errors,
        "mode": mode,
        "adapter": adapter,
        "readiness": readiness,
        "checks": checks,
        "errors": errors,
    }


def print_dotfiles_compatibility_contract(root=None, json_output=False, strict=False):
    payload = dotfiles_compatibility_contract(root=root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            label = f"{COL_GREEN}OK{COL_RESET}" if check["ok"] else f"{COL_RED}FAIL{COL_RESET}"
            print(f"{label} {check['name']}")
    return 1 if strict and not payload["valid"] else 0


def write_dotfiles_compatibility_contract(output_path=None, check=False):
    output_path = output_path or os.path.join(contracts_path, "dotfiles-compatibility.example.json")
    example = {
        "contract": {"name": "dotfiles-compatibility", "version": 1},
        "path": "/path/to/dotfiles",
        "valid": True,
        "mode": "hybrid",
        "adapter": "hybrid",
        "readiness": {
            "install_shim": True,
            "smu_blueprint": True,
            "platform_scope": True,
            "root_config": True,
            "rcm_ready": False,
            "nix_ready": False,
            "hybrid_ready": True,
            "vps_ready": True,
            "ci_contract": True,
        },
        "checks": [
            {"name": "install-shim", "ok": True},
            {"name": "smu-blueprint", "ok": True},
            {"name": "platform-scope", "ok": True},
            {"name": "root-smu-toml", "ok": True},
            {"name": "ci-contract", "ok": True},
        ],
        "errors": [],
    }
    expected = json.dumps(example, indent=2, sort_keys=True) + "\n"
    if check:
        if not os.path.exists(output_path):
            print(f"{COL_RED}FAIL{COL_RESET} missing dotfiles compatibility contract: {output_path}")
            return 1
        if _read_text(output_path) != expected:
            print(f"{COL_RED}FAIL{COL_RESET} stale dotfiles compatibility contract: {output_path}")
            return 1
        print(f"{COL_GREEN}OK{COL_RESET}   dotfiles compatibility contract {output_path}")
        return 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(expected)
    schema_path = os.path.join(os.path.dirname(output_path), "schemas", "dotfiles-compatibility.schema.json")
    os.makedirs(os.path.dirname(schema_path), exist_ok=True)
    with open(schema_path, "w") as f:
        json.dump(dotfiles_compatibility_schema(), f, indent=2, sort_keys=True)
        f.write("\n")
    print(output_path)
    return 0


def migrate_dotfiles_repo(root, mode="hybrid", blueprint=None, branch="main", scope="platform", force=False, json_output=False, dry_run=False):
    if not root:
        die("Usage: smu blueprint migrate-dotfiles --repo <path> [--mode rcm|nix|hybrid]")
    root = os.path.abspath(root)
    blueprint = blueprint or os.getenv("SMU_BLUEPRINT") or os.path.basename(root)
    adapter = BLUEPRINT_MODE_ADAPTERS.get(mode)
    if not adapter:
        die(f"Unsupported blueprint mode '{mode}'.")
    planned = [
        {"path": _dotfiles_install_shim_path(root), "content": _shell_shim_content(blueprint, branch, scope)},
        {"path": os.path.join(root, "smu.toml"), "content": _smu_toml_content(mode)},
        {"path": os.path.join(root, ".github", "workflows", "set-me-up.yml"), "content": _compat_workflow_content(adapter if adapter != "hybrid" else "home-manager")},
    ]
    results = []
    for item in planned:
        if dry_run:
            results.append({"path": item["path"], "changed": not os.path.exists(item["path"]), "reason": "dry-run"})
        else:
            results.append(_write_if_needed(item["path"], item["content"], force=force))
            if item["path"].endswith("install.sh"):
                os.chmod(item["path"], 0o755)
    payload = {
        "repo": root,
        "mode": mode,
        "adapter": adapter,
        "files": results,
        "next_commands": [
            f"smu blueprint dotfiles-contract --repo {root} --json",
            "smu provisioning-adapter preflight --adapter home-manager --profile default --json",
        ],
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for result in results:
            state = "write" if result["changed"] else "skip"
            print(f"{state}\t{result['path']}")
    return 0


def migrate_dotfiles_command(args, force=False, json_output=False):
    return migrate_dotfiles_repo(
        _option_value(args, "--repo") or _option_value(args, "--path"),
        mode=_option_value(args, "--mode") or "hybrid",
        blueprint=_option_value(args, "--blueprint"),
        branch=_option_value(args, "--branch") or "main",
        scope=_option_value(args, "--scope") or "platform",
        force=force,
        json_output=json_output,
        dry_run="--dry-run" in args,
    )


def dotfiles_contract_command(args, check=False, output_path=None, json_output=False):
    root = _option_value(args, "--repo") or _option_value(args, "--path") or _option_value(args, "--root") or smu_home_dir
    if check or output_path:
        return write_dotfiles_compatibility_contract(output_path=output_path, check=check)
    return print_dotfiles_compatibility_contract(root=root, json_output=json_output, strict="--strict" in args)


def vps_plan(target="ubuntu", mode="hybrid", repo=None, json_output=False):
    target = target or "ubuntu"
    if target not in VPS_TARGETS:
        die(f"Unsupported VPS target '{target}'.")
    adapter = VPS_TARGETS[target]["adapter"] if mode == "nix" else BLUEPRINT_MODE_ADAPTERS.get(mode, "hybrid")
    install_url = "https://raw.githubusercontent.com/${SMU_BLUEPRINT}/main/dotfiles/modules/install.sh"
    commands = {
        "prerequisites": VPS_TARGETS[target]["install"],
        "plan": f'SMU_SUBMODULE_SCOPE=platform bash <(curl -s -L "{install_url}") --plan',
        "install": f'SMU_SUBMODULE_SCOPE=platform bash <(curl -s -L "{install_url}")',
        "preflight": f"smu provisioning-adapter preflight --adapter {adapter if adapter != 'hybrid' else 'home-manager'} --profile default --json",
        "apply": f"smu provisioning-adapter apply --adapter {adapter if adapter != 'hybrid' else 'home-manager'} --profile default",
        "rollback": "smu rollback --dry-run && smu rollback",
        "update": "smu update --all --validate",
    }
    payload = {
        "target": target,
        "mode": mode,
        "adapter": adapter,
        "repo": repo,
        "platform_scope": "platform",
        "prerequisites": VPS_TARGETS[target]["prerequisites"],
        "commands": commands,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, command in commands.items():
            print(f"{name}\t{command}")
    return 0


def handle_vps_command(argv):
    command = argv[0] if argv else "doctor"
    args = argv[1:]
    target = _option_value(args, "--target") or "ubuntu"
    mode = _option_value(args, "--mode") or "hybrid"
    repo = _option_value(args, "--repo") or _option_value(args, "--path")
    json_output = "--json" in args
    if command == "init":
        if repo:
            return migrate_dotfiles_repo(repo, mode=mode, force="--force" in args, json_output=json_output, dry_run="--dry-run" in args)
        return vps_plan(target=target, mode=mode, json_output=json_output)
    if command == "doctor":
        if repo:
            return print_dotfiles_compatibility_contract(root=repo, json_output=json_output, strict="--strict" in args)
        return vps_plan(target=target, mode=mode, json_output=json_output)
    die("Usage: smu vps [init|doctor] [--target ubuntu|debian|arch|nixos] [--mode rcm|nix|hybrid] [--repo path] [--json]")


__all__ = [name for name in globals() if not name.startswith("__")]
