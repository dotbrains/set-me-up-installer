from .core import *


def _preflight_module_errors(rows):
    errors = []
    for row in rows:
        if row["state"] in ("missing-adapter", "missing-module"):
            available = ",".join(row["available_adapters"]) or "<none>"
            errors.append(f"{row['module']}: {row['state']} for {row['adapter']} (available: {available})")
    return errors


def _preflight_rcm_plan(modules, profile, adapter_id):
    rows = [resolve_module_provisioning_adapter(module, adapter_id) for module in modules]
    return {
        "kind": "rcm",
        "modules": rows,
        "artifacts": [],
        "commands": [["smu", "--provision", "--provisioning-adapter", adapter_id, "-m", *modules]],
        "errors": _preflight_module_errors(rows),
    }


def _preflight_nix_plan(modules, profile, adapter_id, action):
    plan = nix_import_plan(adapter_id, modules, profile=profile)
    artifact = nix_import_artifact_path(adapter_id, plan["profile"])
    return {
        "kind": "nix",
        "modules": plan["imports"],
        "missing": plan["missing"],
        "artifacts": [artifact],
        "commands": [nix_action_command(adapter_id, artifact, action)],
        "errors": _preflight_module_errors(plan["missing"]),
    }


def _preflight_hybrid_plan(modules, profile, strict, action):
    plan = hybrid_module_plan(modules, profile=profile, strict=strict)
    commands = []
    artifacts = []
    if plan["nix_modules"]:
        artifact = nix_import_artifact_path(plan["nix_adapter"], plan["profile"])
        artifacts.append(artifact)
        commands.append(nix_action_command(plan["nix_adapter"], artifact, action))
    if plan["rcm_modules"]:
        commands.append(["smu", "--provision", "--provisioning-adapter", "rcm", "-m", *plan["rcm_modules"]])
    return {
        "kind": "hybrid",
        "nix_adapter": plan["nix_adapter"],
        "nix_modules": plan["nix_modules"],
        "rcm_modules": plan["rcm_modules"],
        "missing": plan["missing"],
        "artifacts": artifacts,
        "commands": commands,
        "errors": _preflight_module_errors(plan["missing"]),
    }


def provisioning_adapter_preflight(
    adapter_id=None,
    profile=None,
    modules=None,
    json_output=False,
    strict=False,
    action="switch",
):
    adapter_id = adapter_id or configured_profile_provisioning_adapter(profile)
    modules = list(modules or blueprint_profile_modules(profile))
    errors = []
    if adapter_id not in PROVISIONING_ADAPTERS:
        errors.append(f"unsupported provisioning adapter '{adapter_id}'")
        capability = {}
    else:
        capability = PROVISIONING_ADAPTERS[adapter_id]
    if not modules:
        errors.append("no modules selected")
    host_supported = adapter_id in PROVISIONING_ADAPTERS and provisioning_adapter_host_supported(adapter_id)
    if adapter_id in PROVISIONING_ADAPTERS and not host_supported:
        errors.append(f"adapter '{adapter_id}' is not supported on this host")

    plan = {"kind": "none", "artifacts": [], "commands": [], "errors": []}
    if adapter_id in PROVISIONING_ADAPTERS and modules:
        if adapter_id == DEFAULT_PROVISIONING_ADAPTER:
            plan = _preflight_rcm_plan(modules, profile, adapter_id)
        elif adapter_id in NIX_IMPORT_ADAPTERS:
            plan = _preflight_nix_plan(modules, profile, adapter_id, action)
        elif adapter_id == "hybrid":
            plan = _preflight_hybrid_plan(modules, profile, strict, action)
        else:
            plan["errors"].append(f"adapter '{adapter_id}' cannot apply modules")
    errors.extend(plan["errors"])
    payload = {
        "adapter": adapter_id,
        "action": action,
        "profile": profile or "default",
        "strict": strict,
        "modules": modules,
        "capability": capability,
        "host_supported": host_supported,
        "can_apply": not errors,
        "preflight": "passed" if not errors else "failed",
        "plan": plan,
        "errors": errors,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['preflight']}\tpreflight")
        print(f"adapter\t{adapter_id}")
        print(f"profile\t{payload['profile']}")
        for command in plan["commands"]:
            print(f"command\t{' '.join(command)}")
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
    return 0 if payload["can_apply"] else 1


__all__ = [name for name in globals() if not name.startswith("__")]
