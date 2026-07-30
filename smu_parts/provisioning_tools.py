from .core import *


def hybrid_fallback_allowed():
    manifest = blueprint_config()
    value = _manifest_section_value(manifest, "provisioning", "allow_rcm_fallback")
    return value is not False


def hybrid_module_plan(modules=None, profile=None, nix_adapter=None, strict=False):
    nix_adapter = nix_adapter or configured_hybrid_nix_adapter()
    strict = strict or not hybrid_fallback_allowed()
    modules = tuple(modules or blueprint_profile_modules(profile))
    nix_modules = []
    rcm_modules = []
    missing = []
    for module in modules:
        resolution = resolve_module_provisioning_adapter(module, nix_adapter)
        if resolution["state"] == "ready":
            nix_modules.append(module)
            continue
        fallback = resolve_module_provisioning_adapter(module, DEFAULT_PROVISIONING_ADAPTER)
        if not strict and fallback["state"] == "ready":
            rcm_modules.append(module)
        else:
            missing.append(resolution)
    return {
        "adapter": "hybrid",
        "nix_adapter": nix_adapter,
        "strict": strict,
        "profile": profile or "default",
        "modules": list(modules),
        "nix_modules": nix_modules,
        "rcm_modules": rcm_modules,
        "missing": missing,
    }


def apply_hybrid_modules(modules=None, profile=None, json_output=False, strict=False, dry_run=False, action="switch"):
    from .module_lifecycle import provision_modules_batch

    plan = hybrid_module_plan(modules, profile=profile, strict=strict)
    if json_output or dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
    if dry_run:
        return 0 if not plan["missing"] else 1
    if plan["missing"]:
        for entry in plan["missing"]:
            available = ",".join(entry["available_adapters"]) or "<none>"
            warn(f"{entry['module']}: no hybrid path (available: {available})")
        return 1
    if plan["nix_modules"]:
        result = apply_nix_import_adapter(
            plan["nix_adapter"],
            plan["nix_modules"],
            profile=profile,
            json_output=json_output,
            action=action,
        )
        if result != 0:
            return result
    if plan["rcm_modules"]:
        provision_modules_batch(plan["rcm_modules"])
    return 0


def provisioning_adapter_audit(adapter_id=None, profile=None, modules=None, json_output=False, strict=False):
    adapter_id = adapter_id or configured_provisioning_adapter()
    modules = list(modules or blueprint_profile_modules(profile))
    if not modules:
        modules = [row["name"] for row in module_provisioning_adapter_report(show_all=True)]
    rows = []
    for module in modules:
        resolution = resolve_module_provisioning_adapter(module, adapter_id)
        rows.append(resolution)
    summary = {
        "ready": sum(1 for row in rows if row["state"] == "ready"),
        "fallback": sum(1 for row in rows if row["state"] == "fallback"),
        "missing": sum(1 for row in rows if row["state"] in ("missing-adapter", "missing-module")),
    }
    payload = {
        "adapter": adapter_id,
        "profile": profile or "default",
        "strict": strict,
        "summary": summary,
        "modules": rows,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"adapter\t{adapter_id}")
        print(f"profile\t{payload['profile']}")
        print(f"ready\t{summary['ready']}")
        print(f"fallback\t{summary['fallback']}")
        print(f"missing\t{summary['missing']}")
        for row in rows:
            available = ",".join(row["available_adapters"]) or "<none>"
            print(f"{row['state']}\t{row['module']}\t{row['resolved_adapter'] or '-'}\t{available}")
    if strict and summary["missing"]:
        return 1
    return 0


def provisioning_adapter_coverage():
    rows = module_provisioning_adapter_report(show_all=True)
    adapters = list(supported_provisioning_adapters())
    coverage = {}
    for adapter_id in adapters:
        ready = 0
        fallback = 0
        missing = 0
        for row in rows:
            module = row["name"]
            resolution = resolve_module_provisioning_adapter(module, adapter_id)
            if resolution["state"] == "ready":
                ready += 1
            elif resolution["state"] == "fallback":
                fallback += 1
            else:
                missing += 1
        coverage[adapter_id] = {
            "ready": ready,
            "fallback": fallback,
            "missing": missing,
            "total": len(rows),
        }
    return {"modules": len(rows), "coverage": coverage}


def print_provisioning_adapter_coverage(json_output=False):
    payload = provisioning_adapter_coverage()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("adapter\tready\tfallback\tmissing\ttotal")
        for adapter_id, row in payload["coverage"].items():
            print(f"{adapter_id}\t{row['ready']}\t{row['fallback']}\t{row['missing']}\t{row['total']}")
    return 0


def validate_blueprint_profile(profile=None, adapter_id=None, json_output=False, strict=False):
    adapter_id = adapter_id or configured_provisioning_adapter()
    modules = list(blueprint_profile_modules(profile))
    errors = []
    rows = []
    if not modules:
        errors.append(f"profile {profile or 'default'} has no modules")
    for module in modules:
        resolution = resolve_module_provisioning_adapter(module, adapter_id)
        rows.append(resolution)
        if resolution["state"] == "missing-module":
            errors.append(f"{module}: missing module")
        elif strict and resolution["state"] != "ready":
            errors.append(f"{module}: missing strict adapter coverage for {adapter_id}")
    payload = {
        "adapter": adapter_id,
        "profile": profile or "default",
        "strict": strict,
        "errors": errors,
        "modules": rows,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        if not errors:
            print(f"{COL_GREEN}OK{COL_RESET}   profile {payload['profile']} for {adapter_id}")
    return 1 if errors else 0


def write_migration_checklist(adapter_id=None, profile=None, modules=None, output_path=None):
    adapter_id = adapter_id or configured_provisioning_adapter()
    output_path = output_path or os.path.join(adapter_state_path, f"{adapter_id}-migration.md")
    modules = list(modules or blueprint_profile_modules(profile))
    audit = []
    for module in modules:
        audit.append(resolve_module_provisioning_adapter(module, adapter_id))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(f"# {adapter_id} migration checklist\n\n")
        f.write(f"Profile: `{profile or 'default'}`\n\n")
        for row in audit:
            checked = "x" if row["state"] == "ready" else " "
            f.write(f"- [{checked}] `{row['module']}`: {row['state']}\n")
            if row["state"] != "ready":
                f.write(f"  - Scaffold: `smu provisioning-adapter scaffold --adapter {adapter_id} -m {row['module']}`\n")
    print(output_path)
    return 0


def nix_bootstrap_status():
    return {
        "nix": subprocess.call("command -v nix >/dev/null 2>&1", shell=True) == 0,
        "home-manager": subprocess.call("command -v home-manager >/dev/null 2>&1", shell=True) == 0,
        "darwin-rebuild": subprocess.call("command -v darwin-rebuild >/dev/null 2>&1", shell=True) == 0,
        "nixos-rebuild": subprocess.call("command -v nixos-rebuild >/dev/null 2>&1", shell=True) == 0,
    }


def print_nix_bootstrap_status(json_output=False):
    payload = nix_bootstrap_status()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, present in payload.items():
            state = "present" if present else "missing"
            print(f"{name}\t{state}")
    return 0


def validate_module_manifests(json_output=False):
    errors = []
    rows = []
    for bucket, modules in discover_modules().items():
        for name, _kind in modules:
            module_dir = os.path.join(module_path, bucket, name)
            manifest_path = module_manifest_path_for_dir(module_dir)
            if not manifest_path:
                continue
            manifest = read_module_manifest_for_dir(module_dir)
            adapters = manifest.get("adapters", {})
            if not isinstance(adapters, dict):
                errors.append(f"{manifest_path}: adapters must be a table")
                continue
            for adapter_id, config in adapters.items():
                if adapter_id not in PROVISIONING_ADAPTERS:
                    errors.append(f"{manifest_path}: unsupported adapter '{adapter_id}'")
                    continue
                if not isinstance(config, dict):
                    errors.append(f"{manifest_path}: adapter '{adapter_id}' must be a table")
                    continue
                rel_path = config.get("path", ".")
                target = module_dir if rel_path == "." else os.path.join(module_dir, rel_path)
                exists = os.path.exists(target)
                rows.append({"module": name, "adapter": adapter_id, "path": target, "exists": exists})
                if not exists:
                    errors.append(f"{manifest_path}: adapter '{adapter_id}' path missing: {rel_path}")
    if json_output:
        print(json.dumps({"errors": errors, "modules": rows}, indent=2, sort_keys=True))
    else:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        if not errors:
            print(f"{COL_GREEN}OK{COL_RESET}   module provisioning manifests")
    return 1 if errors else 0


def _nix_adapter_template(adapter_id):
    if adapter_id == "home-manager":
        return "{ pkgs, ... }:\n\n{\n  home.packages = [ ];\n}\n"
    return "{ pkgs, ... }:\n\n{\n  environment.systemPackages = [ ];\n}\n"


def scaffold_module_adapter(module_name, adapter_id):
    adapter_ids = NIX_IMPORT_ADAPTERS if adapter_id == "all" else (adapter_id,)
    if any(item not in NIX_IMPORT_ADAPTERS for item in adapter_ids):
        die("Scaffold currently supports home-manager, nix-darwin, and nixos.")
    path = get_module_path(module_name)
    if not path:
        die(f"Unknown module '{module_name}'.")
    module_dir = os.path.dirname(path)
    manifest_path = os.path.join(module_dir, MODULE_MANIFEST)
    if not os.path.exists(manifest_path):
        with open(manifest_path, "w") as f:
            f.write(f'id = "{module_name}"\n')
    manifest = read_module_manifest_for_dir(module_dir)
    existing = manifest.get("adapters", {}) if isinstance(manifest.get("adapters", {}), dict) else {}
    created = []
    with open(manifest_path, "a") as f:
        for item in adapter_ids:
            adapter_file = os.path.join(module_dir, f"{item}.nix")
            if item not in existing:
                f.write(f'\n[adapters.{item}]\npath = "{item}.nix"\n')
            if not os.path.exists(adapter_file):
                with open(adapter_file, "w") as adapter_handle:
                    adapter_handle.write(_nix_adapter_template(item))
            created.append(adapter_file)
    for path in created:
        print(path)
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
