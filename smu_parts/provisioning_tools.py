from .core import *


def hybrid_module_plan(modules=None, profile=None, nix_adapter=None):
    nix_adapter = nix_adapter or configured_hybrid_nix_adapter()
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
        if fallback["state"] == "ready":
            rcm_modules.append(module)
        else:
            missing.append(resolution)
    return {
        "adapter": "hybrid",
        "nix_adapter": nix_adapter,
        "profile": profile or "default",
        "modules": list(modules),
        "nix_modules": nix_modules,
        "rcm_modules": rcm_modules,
        "missing": missing,
    }


def apply_hybrid_modules(modules=None, profile=None, json_output=False):
    from .module_lifecycle import provision_modules_batch

    plan = hybrid_module_plan(modules, profile=profile)
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
        )
        if result != 0:
            return result
    if plan["rcm_modules"]:
        provision_modules_batch(plan["rcm_modules"])
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


def scaffold_module_adapter(module_name, adapter_id):
    if adapter_id not in NIX_IMPORT_ADAPTERS:
        die("Scaffold currently supports home-manager, nix-darwin, and nixos.")
    path = get_module_path(module_name)
    if not path:
        die(f"Unknown module '{module_name}'.")
    module_dir = os.path.dirname(path)
    manifest_path = os.path.join(module_dir, MODULE_MANIFEST)
    adapter_file = os.path.join(module_dir, f"{adapter_id}.nix")
    if not os.path.exists(manifest_path):
        with open(manifest_path, "w") as f:
            f.write(f'id = "{module_name}"\n')
    with open(manifest_path, "a") as f:
        f.write(f'\n[adapters.{adapter_id}]\npath = "{adapter_id}.nix"\n')
    if not os.path.exists(adapter_file):
        with open(adapter_file, "w") as f:
            f.write("{ pkgs, ... }:\n\n{\n  home.packages = [ ];\n}\n")
    print(adapter_file)
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
