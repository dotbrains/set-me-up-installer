from ..core import *


def nix_profile_doctor(profile=None, adapter_id="home-manager", json_output=False, strict=False):
    modules = list(blueprint_profile_modules(profile))
    audit_rows = [resolve_module_provisioning_adapter(module, adapter_id) for module in modules]
    policy_errors = []
    for row in audit_rows:
        violation = _platform_policy_violation(row)
        if violation:
            policy_errors.append(violation)
    flake_path = os.path.join(smu_home_dir, "flake.nix")
    bootstrap = nix_bootstrap_status()
    diagnostics = []
    if not bootstrap.get("nix"):
        diagnostics.append("nix is not installed")
    adapter_binary = {
        "home-manager": "home-manager",
        "nix-darwin": "darwin-rebuild",
        "nixos": "nixos-rebuild",
    }.get(adapter_id)
    if adapter_binary and not bootstrap.get(adapter_binary):
        diagnostics.append(f"{adapter_binary} is not installed or is not on PATH")
    payload = {
        "adapter": adapter_id,
        "profile": profile or "default",
        "host_supported": provisioning_adapter_host_supported(adapter_id),
        "binaries": bootstrap,
        "flake": {"path": flake_path, "present": os.path.exists(flake_path)},
        "profile_path": nix_import_artifact_path(adapter_id, profile),
        "diagnostics": diagnostics,
        "modules": audit_rows,
        "policy_errors": policy_errors,
        "summary": {
            "ready": sum(1 for row in audit_rows if row["state"] == "ready"),
            "missing": sum(1 for row in audit_rows if row["state"] != "ready"),
        },
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"adapter\t{adapter_id}")
        print(f"profile\t{payload['profile']}")
        print(f"host_supported\t{str(payload['host_supported']).lower()}")
        print(f"flake\t{str(payload['flake']['present']).lower()}\t{payload['flake']['path']}")
        print(f"ready\t{payload['summary']['ready']}")
        print(f"missing\t{payload['summary']['missing']}")
        for diagnostic in diagnostics:
            print(f"{COL_YELLOW}WARN{COL_RESET} {diagnostic}")
        for error in policy_errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
    if strict and (policy_errors or payload["summary"]["missing"] or not payload["host_supported"]):
        return 1
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
