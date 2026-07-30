from .core import *


NIX_IMPORT_ADAPTERS = ("home-manager", "nix-darwin", "nixos")
NIX_APPLY_ACTIONS = ("switch", "build", "test")


def nix_import_state_path(adapter_id):
    return os.path.join(adapter_state_path, adapter_id)


def nix_import_plan(adapter_id, modules=None, profile=None):
    if adapter_id not in NIX_IMPORT_ADAPTERS:
        die(f"Provisioning adapter '{adapter_id}' does not support Nix import planning.")
    modules = tuple(modules or blueprint_profile_modules(profile))
    entries = []
    missing = []
    for module in modules:
        resolution = resolve_module_provisioning_adapter(module, adapter_id)
        if resolution["state"] == "ready":
            entries.append({"module": module, "path": resolution["implementation_path"]})
        else:
            missing.append(resolution)
    return {
        "adapter": adapter_id,
        "profile": profile or "default",
        "modules": list(modules),
        "imports": entries,
        "missing": missing,
    }


def _nix_path(path):
    return path.replace(" ", "\\ ")


def render_nix_import_module(plan):
    lines = ["{ ... }:", "", "{", "  imports = ["]
    for entry in plan["imports"]:
        lines.append(f"    {_nix_path(entry['path'])}")
    lines.extend(["  ];", "}"])
    return "\n".join(lines) + "\n"


def nix_import_artifact_path(adapter_id, profile=None):
    return os.path.join(nix_import_state_path(adapter_id), f"{profile or 'default'}.nix")


def nix_adapter_host_supported(adapter_id):
    if adapter_id == "home-manager":
        return True
    if adapter_id == "nix-darwin":
        return macOS
    if adapter_id == "nixos":
        return linux and os.path.exists("/etc/NIXOS")
    return False


def _warn_missing_nix_imports(plan):
    for entry in plan["missing"]:
        available = ",".join(entry["available_adapters"]) or "<none>"
        warn(f"{entry['module']}: {entry['state']} for {plan['adapter']} (available: {available})")


def print_nix_import_plan(adapter_id, modules=None, json_output=False, profile=None):
    plan = nix_import_plan(adapter_id, modules, profile=profile)
    if json_output:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    print(render_nix_import_module(plan), end="")
    if plan["missing"]:
        print()
        _warn_missing_nix_imports(plan)
    return 0


def _write_nix_import_artifact(plan, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(render_nix_import_module(plan))


def write_nix_import_plan(adapter_id, modules=None, profile=None, json_output=False):
    plan = nix_import_plan(adapter_id, modules, profile=profile)
    output_path = nix_import_artifact_path(adapter_id, plan["profile"])
    _write_nix_import_artifact(plan, output_path)
    payload = dict(plan)
    payload["path"] = output_path
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(output_path)
    if plan["missing"]:
        _warn_missing_nix_imports(plan)
    return 0


def _require_nix_apply_command(adapter_id):
    if adapter_id == "home-manager":
        binary = "home-manager"
    elif adapter_id == "nix-darwin":
        if not nix_adapter_host_supported(adapter_id):
            die("Provisioning adapter 'nix-darwin' can only apply on macOS hosts.")
        binary = "darwin-rebuild"
    elif adapter_id == "nixos":
        if not nix_adapter_host_supported(adapter_id):
            die("Provisioning adapter 'nixos' can only apply on NixOS hosts.")
        binary = "nixos-rebuild"
    else:
        die(f"Provisioning adapter '{adapter_id}' cannot apply Nix imports.")
    if subprocess.call(f"command -v {binary} >/dev/null 2>&1", shell=True) != 0:
        die(f"'{binary}' is not installed or is not on PATH.")


def nix_apply_command(adapter_id, artifact):
    _require_nix_apply_command(adapter_id)
    return nix_action_command(adapter_id, artifact, "switch")


def nix_action_command(adapter_id, artifact, action):
    if action not in NIX_APPLY_ACTIONS:
        die(f"Nix apply action '{action}' is not supported.")
    if adapter_id == "home-manager":
        return ["home-manager", action, "-f", artifact]
    if adapter_id == "nix-darwin":
        return ["darwin-rebuild", action, "-I", f"darwin-config={artifact}"]
    if adapter_id == "nixos":
        return ["sudo", "nixos-rebuild", action, "-I", f"nixos-config={artifact}"]
    die(f"Provisioning adapter '{adapter_id}' cannot apply Nix imports.")


def apply_nix_import_adapter(adapter_id, modules=None, profile=None, json_output=False, dry_run=False, action="switch"):
    plan = nix_import_plan(adapter_id, modules, profile=profile)
    if plan["missing"]:
        _warn_missing_nix_imports(plan)
        return 1

    artifact = nix_import_artifact_path(adapter_id, plan["profile"])
    if not dry_run:
        _require_nix_apply_command(adapter_id)
    command = nix_action_command(adapter_id, artifact, action)
    _write_nix_import_artifact(plan, artifact)
    if json_output or dry_run:
        print(json.dumps({
            "adapter": adapter_id,
            "action": action,
            "dry_run": dry_run,
            "profile": plan["profile"],
            "modules": plan["modules"],
            "path": artifact,
            "command": command,
        }, indent=2, sort_keys=True))
    if dry_run:
        return 0
    return subprocess.run(command).returncode


def render_nix_flake(plan, output_name=None):
    output_name = output_name or plan["profile"]
    import_path = nix_import_artifact_path(plan["adapter"], plan["profile"])
    attr_name = json.dumps(output_name)
    lines = [
        "{",
        '  description = "set-me-up generated provisioning adapter flake";',
        "",
        "  outputs = { self, nixpkgs, ... }: {",
    ]
    if plan["adapter"] == "home-manager":
        lines.append(f"    homeConfigurations.{attr_name} = import {_nix_path(import_path)};")
    elif plan["adapter"] == "nix-darwin":
        lines.append(f"    darwinConfigurations.{attr_name} = import {_nix_path(import_path)};")
    elif plan["adapter"] == "nixos":
        lines.append(f"    nixosConfigurations.{attr_name} = import {_nix_path(import_path)};")
    lines.extend(["  };", "}"])
    return "\n".join(lines) + "\n"


def write_nix_flake(adapter_id, modules=None, profile=None, output_name=None, json_output=False):
    plan = nix_import_plan(adapter_id, modules, profile=profile)
    if plan["missing"]:
        _warn_missing_nix_imports(plan)
        return 1
    _write_nix_import_artifact(plan, nix_import_artifact_path(adapter_id, plan["profile"]))
    output_path = os.path.join(nix_import_state_path(adapter_id), "flake.nix")
    with open(output_path, "w") as f:
        f.write(render_nix_flake(plan, output_name=output_name))
    if json_output:
        print(json.dumps({"adapter": adapter_id, "path": output_path, "profile": plan["profile"]}, indent=2, sort_keys=True))
    else:
        print(output_path)
    return 0


def home_manager_import_plan(modules=None, profile=None):
    return nix_import_plan("home-manager", modules, profile=profile)


def print_home_manager_import_plan(modules=None, json_output=False, profile=None):
    return print_nix_import_plan("home-manager", modules, json_output=json_output, profile=profile)


def render_home_manager_import_module(plan):
    return render_nix_import_module(plan)


def home_manager_import_artifact_path(profile=None):
    return nix_import_artifact_path("home-manager", profile)


def write_home_manager_import_plan(modules=None, profile=None, json_output=False):
    return write_nix_import_plan("home-manager", modules, profile=profile, json_output=json_output)


def apply_home_manager_modules(modules=None, profile=None, json_output=False):
    return apply_nix_import_adapter("home-manager", modules, profile=profile, json_output=json_output)


__all__ = [name for name in globals() if not name.startswith("__")]
