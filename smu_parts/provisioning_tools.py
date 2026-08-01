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
    adapter_id = adapter_id or configured_profile_provisioning_adapter(profile)
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
            "ready_percent": round((ready / len(rows)) * 100, 2) if rows else 0,
        }
    nix_ready = sum(1 for row in rows if resolve_module_provisioning_adapter(row["name"], "home-manager")["state"] == "ready")
    return {
        "modules": len(rows),
        "coverage": coverage,
        "nix_ready": {
            "adapter": "home-manager",
            "ready": nix_ready,
            "total": len(rows),
            "percent": round((nix_ready / len(rows)) * 100, 2) if rows else 0,
        },
    }


def provisioning_adapter_parity(source_adapter="rcm", target_adapter="home-manager", modules=None, profile=None):
    modules = list(modules or blueprint_profile_modules(profile))
    if not modules:
        modules = [row["name"] for row in module_provisioning_adapter_report(show_all=True)]
    rows = []
    summary = {"ready": 0, "source_only": 0, "target_only": 0, "missing": 0}
    for module in modules:
        source = resolve_module_provisioning_adapter(module, source_adapter)
        target = resolve_module_provisioning_adapter(module, target_adapter)
        if source["state"] == "ready" and target["state"] == "ready":
            state = "ready"
        elif source["state"] == "ready":
            state = "source-only"
        elif target["state"] == "ready":
            state = "target-only"
        else:
            state = "missing"
        summary[state.replace("-", "_")] += 1
        rows.append({"module": module, "state": state, "source": source, "target": target})
    return {
        "profile": profile or "default",
        "source_adapter": source_adapter,
        "target_adapter": target_adapter,
        "summary": summary,
        "modules": rows,
    }


def _current_platform_ids():
    values = []
    if linux:
        values.append("linux")
    if debian:
        values.extend(("debian", "ubuntu"))
    if arch:
        values.append("arch")
    if macOS:
        values.append("macos")
    if linux and os.path.exists("/etc/NIXOS"):
        values.append("nixos")
    return tuple(values)


def _adapter_policy_errors(manifest_path, adapter_id, config):
    errors = []
    platforms = config.get("platforms", [])
    if platforms and not isinstance(platforms, list):
        errors.append(f"{manifest_path}: adapter '{adapter_id}' platforms must be an array")
    for platform in platforms if isinstance(platforms, list) else ():
        if platform not in ("macos", "debian", "ubuntu", "arch", "linux", "nixos"):
            errors.append(f"{manifest_path}: adapter '{adapter_id}' unsupported platform '{platform}'")
    for field in ("requires_root", "secrets", "reboot_required"):
        if field in config and not isinstance(config[field], bool):
            errors.append(f"{manifest_path}: adapter '{adapter_id}' {field} must be boolean")
    for field in ("requires", "services"):
        value = config.get(field, [])
        if value and not isinstance(value, list):
            errors.append(f"{manifest_path}: adapter '{adapter_id}' {field} must be an array")
    return errors


def _platform_policy_violation(resolution):
    implementation = resolution.get("implementation") or {}
    platforms = implementation.get("platforms") or []
    if not platforms:
        return None
    current = _current_platform_ids()
    if any(platform in current for platform in platforms):
        return None
    return f"{resolution['module']}: adapter {resolution['adapter']} supports platforms {', '.join(platforms)}, current host is {', '.join(current) or 'unknown'}"


def print_provisioning_adapter_parity(source_adapter="rcm", target_adapter="home-manager", modules=None, profile=None, json_output=False):
    payload = provisioning_adapter_parity(source_adapter, target_adapter, modules, profile)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("module\tstate\tsource\ttarget")
        for row in payload["modules"]:
            print(f"{row['module']}\t{row['state']}\t{row['source']['state']}\t{row['target']['state']}")
    return 0


def write_provisioning_adapter_docs(output_path=None):
    output_path = output_path or os.path.join(adapter_state_path, "provisioning-adapter-coverage.md")
    payload = provisioning_adapter_coverage()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write("# Provisioning Adapter Coverage\n\n")
        f.write("| Adapter | Ready | Fallback | Missing | Total | Ready % |\n")
        f.write("| --- | ---: | ---: | ---: | ---: | ---: |\n")
        for adapter_id, row in payload["coverage"].items():
            f.write(f"| `{adapter_id}` | {row['ready']} | {row['fallback']} | {row['missing']} | {row['total']} | {row['ready_percent']} |\n")
    print(output_path)
    return 0


def check_provisioning_adapter_docs(output_path=None):
    output_path = output_path or os.path.join(adapter_state_path, "provisioning-adapter-coverage.md")
    if not os.path.exists(output_path):
        print(f"{COL_RED}FAIL{COL_RESET} missing generated adapter docs: {output_path}")
        return 1
    payload = provisioning_adapter_coverage()
    expected = io.StringIO()
    expected.write("# Provisioning Adapter Coverage\n\n")
    expected.write("| Adapter | Ready | Fallback | Missing | Total | Ready % |\n")
    expected.write("| --- | ---: | ---: | ---: | ---: | ---: |\n")
    for adapter_id, row in payload["coverage"].items():
        expected.write(f"| `{adapter_id}` | {row['ready']} | {row['fallback']} | {row['missing']} | {row['total']} | {row['ready_percent']} |\n")
    with open(output_path) as f:
        current = f.read()
    if current != expected.getvalue():
        print(f"{COL_RED}FAIL{COL_RESET} generated adapter docs are stale: {output_path}")
        return 1
    print(f"{COL_GREEN}OK{COL_RESET}   generated adapter docs {output_path}")
    return 0


def nix_profile_doctor(profile=None, adapter_id="home-manager", json_output=False, strict=False):
    modules = list(blueprint_profile_modules(profile))
    audit_rows = [resolve_module_provisioning_adapter(module, adapter_id) for module in modules]
    policy_errors = []
    for row in audit_rows:
        violation = _platform_policy_violation(row)
        if violation:
            policy_errors.append(violation)
    payload = {
        "adapter": adapter_id,
        "profile": profile or "default",
        "host_supported": provisioning_adapter_host_supported(adapter_id),
        "binaries": nix_bootstrap_status(),
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
        print(f"ready\t{payload['summary']['ready']}")
        print(f"missing\t{payload['summary']['missing']}")
        for error in policy_errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
    if strict and (policy_errors or payload["summary"]["missing"] or not payload["host_supported"]):
        return 1
    return 0


def print_provisioning_adapter_coverage(json_output=False):
    payload = provisioning_adapter_coverage()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("adapter\tready\tfallback\tmissing\ttotal\tready_percent")
        for adapter_id, row in payload["coverage"].items():
            print(f"{adapter_id}\t{row['ready']}\t{row['fallback']}\t{row['missing']}\t{row['total']}\t{row['ready_percent']}")
    return 0


def validate_blueprint_profile(profile=None, adapter_id=None, json_output=False, strict=False):
    adapter_id = adapter_id or configured_profile_provisioning_adapter(profile)
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
        violation = _platform_policy_violation(resolution)
        if strict and violation:
            errors.append(violation)
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
    adapter_id = adapter_id or configured_profile_provisioning_adapter(profile)
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


def write_migration_state(adapter_id=None, profile=None, modules=None, output_path=None, status="pending"):
    adapter_id = adapter_id or configured_profile_provisioning_adapter(profile)
    output_path = output_path or os.path.join(adapter_state_path, f"{adapter_id}-migration-state.json")
    rows = []
    for module in list(modules or blueprint_profile_modules(profile)):
        resolution = resolve_module_provisioning_adapter(module, adapter_id)
        rows.append({
            "module": module,
            "adapter_state": resolution["state"],
            "review_status": "accepted" if resolution["state"] == "ready" else status,
        })
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"adapter": adapter_id, "profile": profile or "default", "modules": rows}, f, indent=2, sort_keys=True)
        f.write("\n")
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
            if not manifest.get("id"):
                errors.append(f"{manifest_path}: missing id")
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
                if "path" not in config:
                    errors.append(f"{manifest_path}: adapter '{adapter_id}' missing path")
                    continue
                errors.extend(_adapter_policy_errors(manifest_path, adapter_id, config))
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


def generate_home_manager_adapter(module_name, output_path=None):
    path = get_module_path(module_name)
    if not path:
        die(f"Unknown module '{module_name}'.")
    module_dir = os.path.dirname(path)
    output_path = output_path or os.path.join(module_dir, "home-manager.nix")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write("{ ... }:\n\n")
        f.write("{\n")
        f.write(f'  xdg.configFile."{module_name}".source = ./.;\n')
        f.write("}\n")
    manifest_path = os.path.join(module_dir, MODULE_MANIFEST)
    manifest = read_module_manifest_for_dir(module_dir) if os.path.exists(manifest_path) else {}
    adapters = manifest.get("adapters", {}) if isinstance(manifest.get("adapters", {}), dict) else {}
    if "home-manager" not in adapters:
        with open(manifest_path, "a") as f:
            if not manifest:
                f.write(f'id = "{module_name}"\n')
            f.write('\n[adapters.home-manager]\npath = "home-manager.nix"\n')
    print(output_path)
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
