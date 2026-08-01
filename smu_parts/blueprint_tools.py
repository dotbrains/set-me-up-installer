from .core import *
from .blueprint_providers import (
    blueprint_provider_matrix,
    print_blueprint_provider_matrix,
    print_blueprint_provider_recommendation,
    validate_blueprint_recommendation_config,
    write_blueprint_recommendation_config,
)


BLUEPRINT_MODES = ("rcm", "nix", "hybrid")
BLUEPRINT_MODE_ADAPTERS = {
    "rcm": "rcm",
    "nix": "home-manager",
    "hybrid": "hybrid",
}
BLUEPRINT_NIX_ADAPTERS = ("home-manager", "nix-darwin", "nixos")


def _blueprint_mode_config(mode):
    if mode not in BLUEPRINT_MODES:
        die(f"Unsupported blueprint mode '{mode}'.")
    adapter = BLUEPRINT_MODE_ADAPTERS[mode]
    lines = [
        "[provisioning]",
        f'mode = "{mode}"',
        f'adapter = "{adapter}"',
    ]
    if mode == "hybrid":
        lines.extend([
            'nix_adapter = "home-manager"',
            "allow_rcm_fallback = true",
        ])
    lines.extend([
        "",
        "[profile.default]",
        'modules = ["example"]',
        "",
    ])
    return "\n".join(lines)


def blueprint_init(mode="rcm", output_path=None, force=False, json_output=False):
    output_path = output_path or os.path.join(smu_home_dir, "smu.toml")
    if os.path.exists(output_path) and not force:
        die(f"Blueprint config already exists: {output_path}. Use --force to overwrite.")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    content = _blueprint_mode_config(mode)
    with open(output_path, "w") as f:
        f.write(content)
    payload = {
        "mode": mode,
        "adapter": BLUEPRINT_MODE_ADAPTERS[mode],
        "path": output_path,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(output_path)
    return 0


def _blueprint_mode_errors(manifest, path=None):
    errors = []
    provisioning = manifest.get("provisioning", {})
    if not isinstance(provisioning, dict):
        return ["[provisioning] must be a table"]
    mode = provisioning.get("mode")
    adapter = provisioning.get("adapter")
    nix_adapter = provisioning.get("nix_adapter")
    if not mode:
        errors.append("[provisioning].mode is required")
    elif mode not in BLUEPRINT_MODES:
        errors.append(f"unsupported provisioning mode '{mode}'")
    if not adapter:
        errors.append("[provisioning].adapter is required")
    elif adapter not in supported_provisioning_adapters():
        errors.append(f"unsupported provisioning adapter '{adapter}'")
    if mode == "rcm" and adapter and adapter != "rcm":
        errors.append("mode 'rcm' requires adapter 'rcm'")
    if mode == "nix" and adapter and adapter not in BLUEPRINT_NIX_ADAPTERS:
        errors.append("mode 'nix' requires adapter 'home-manager', 'nix-darwin', or 'nixos'")
    if mode == "hybrid" and adapter and adapter != "hybrid":
        errors.append("mode 'hybrid' requires adapter 'hybrid'")
    if mode == "hybrid" and nix_adapter and nix_adapter not in BLUEPRINT_NIX_ADAPTERS:
        errors.append("hybrid nix_adapter must be 'home-manager', 'nix-darwin', or 'nixos'")
    for section_name in ("profile", "profiles"):
        profiles = manifest.get(section_name, {})
        if not isinstance(profiles, dict):
            continue
        for profile_name, profile_config in profiles.items():
            if not isinstance(profile_config, dict):
                continue
            profile_adapter = profile_config.get("adapter")
            if profile_adapter and profile_adapter not in supported_provisioning_adapters():
                errors.append(f"profile {profile_name} uses unsupported adapter '{profile_adapter}'")
            if mode == "rcm" and profile_adapter and profile_adapter != "rcm":
                errors.append(f"profile {profile_name} cannot override rcm mode with '{profile_adapter}'")
    if path:
        return [f"{path}: {error}" for error in errors]
    return errors


def blueprint_doctor(json_output=False, strict=False):
    path = blueprint_config_path()
    manifest = blueprint_config()
    errors = []
    if not path:
        errors.append("no blueprint config found")
    else:
        errors.extend(_blueprint_mode_errors(manifest, path=path))
    provisioning = manifest.get("provisioning", {}) if isinstance(manifest, dict) else {}
    mode = provisioning.get("mode") if isinstance(provisioning, dict) else None
    adapter = provisioning.get("adapter") if isinstance(provisioning, dict) else None
    payload = {
        "path": path,
        "mode": mode,
        "adapter": adapter,
        "valid": not errors,
        "errors": errors,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if errors:
            for error in errors:
                print(f"{COL_RED}FAIL{COL_RESET} {error}")
        else:
            print(f"{COL_GREEN}OK{COL_RESET}   blueprint {mode} mode uses {adapter}")
    return 1 if errors and strict else 0


def blueprint_mode_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://dotbrains.github.io/set-me-up/schemas/blueprint.schema.json",
        "title": "set-me-up blueprint configuration",
        "type": "object",
        "properties": {
            "provisioning": {
                "type": "object",
                "required": ["mode", "adapter"],
                "properties": {
                    "mode": {"type": "string", "enum": list(BLUEPRINT_MODES)},
                    "adapter": {"type": "string", "enum": list(supported_provisioning_adapters())},
                    "nix_adapter": {"type": "string", "enum": list(NIX_IMPORT_ADAPTERS)},
                    "allow_rcm_fallback": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            "profile": {"type": "object"},
            "profiles": {"type": "object"},
        },
        "additionalProperties": True,
    }


def blueprint_migrate(source_mode="rcm", target_mode="nix", output_path=None, force=False, json_output=False):
    if source_mode != "rcm":
        die("Blueprint migration currently supports --from rcm.")
    if target_mode not in ("nix", "hybrid"):
        die("Blueprint migration currently supports --to nix or --to hybrid.")
    path = output_path or blueprint_config_path() or os.path.join(smu_home_dir, "smu.toml")
    if os.path.exists(path) and not force:
        die(f"Blueprint config already exists: {path}. Use --force to overwrite.")
    result = blueprint_init(mode=target_mode, output_path=path, force=True, json_output=False)
    if result != 0:
        return result
    report = rcm_to_nix_migration_report(target_adapter="home-manager")
    payload = {
        "from": source_mode,
        "to": target_mode,
        "path": path,
        "report": report,
        "next_commands": [
            "smu blueprint doctor --strict",
            "smu nix doctor --profile default --json",
            "smu nix migrate compare --profile default --json",
        ],
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(path)
        print("next\tsmu blueprint doctor --strict")
        print("next\tsmu nix migrate compare --profile default --json")
    return 0


def write_blueprint_schema(output_path=None, check=False):
    output_path = output_path or os.path.join(installer_root, "schemas", "blueprint.schema.json")
    expected = json.dumps(blueprint_mode_schema(), indent=2, sort_keys=True) + "\n"
    if check:
        if not os.path.exists(output_path):
            print(f"{COL_RED}FAIL{COL_RESET} missing blueprint schema: {output_path}")
            return 1
        with open(output_path) as f:
            current = f.read()
        if current != expected:
            print(f"{COL_RED}FAIL{COL_RESET} stale blueprint schema: {output_path}")
            return 1
        print(f"{COL_GREEN}OK{COL_RESET}   blueprint schema {output_path}")
        return 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(expected)
    print(output_path)
    return 0


def _migration_status(source, target):
    if source["state"] == "ready" and target["state"] == "ready":
        return "ported"
    if source["state"] == "ready" and target["state"] == "fallback":
        return "partial"
    if source["state"] == "ready" and target["state"] == "missing-adapter":
        return "kept-rcm"
    if source["state"] == "ready":
        return "blocked"
    if target["state"] == "ready":
        return "ported"
    return "blocked"


def rcm_to_nix_migration_report(modules=None, profile=None, target_adapter="home-manager"):
    modules = list(modules or blueprint_profile_modules(profile))
    if not modules:
        modules = [row["name"] for row in module_provisioning_adapter_report(show_all=True)]
    rows = []
    summary = {"ported": 0, "partial": 0, "blocked": 0, "kept_rcm": 0}
    for module in modules:
        source = resolve_module_provisioning_adapter(module, "rcm")
        target = resolve_module_provisioning_adapter(module, target_adapter)
        status = _migration_status(source, target)
        summary[status.replace("-", "_")] += 1
        rows.append({
            "module": module,
            "status": status,
            "source": source,
            "target": target,
        })
    return {
        "profile": profile or "default",
        "source_adapter": "rcm",
        "target_adapter": target_adapter,
        "summary": summary,
        "files": rows,
    }


def print_rcm_to_nix_migration_report(modules=None, profile=None, target_adapter="home-manager", json_output=False):
    payload = rcm_to_nix_migration_report(modules=modules, profile=profile, target_adapter=target_adapter)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("module\tstatus\trcm\tnix")
        for row in payload["files"]:
            print(f"{row['module']}\t{row['status']}\t{row['source']['state']}\t{row['target']['state']}")
    return 0


def provisioning_compatibility_matrix():
    rows = []
    for row in module_provisioning_adapter_report(show_all=True):
        module = row["name"]
        entry = {"module": module, "bucket": row["bucket"]}
        for adapter_id in supported_provisioning_adapters():
            resolution = resolve_module_provisioning_adapter(module, adapter_id)
            entry[adapter_id] = resolution["state"]
        rows.append(entry)
    return {"adapters": list(supported_provisioning_adapters()), "modules": rows}


def print_provisioning_compatibility_matrix(json_output=False):
    payload = provisioning_compatibility_matrix()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("module\tbucket\t" + "\t".join(payload["adapters"]))
        for row in payload["modules"]:
            values = [row["module"], row["bucket"]]
            values.extend(row[adapter_id] for adapter_id in payload["adapters"])
            print("\t".join(values))
    return 0


def render_blueprint_compatibility_docs():
    payload = provisioning_compatibility_matrix()
    lines = [
        "# Blueprint Provisioning Compatibility",
        "",
        "| Module | Bucket | " + " | ".join(f"`{adapter_id}`" for adapter_id in payload["adapters"]) + " |",
        "| --- | --- | " + " | ".join("---" for _adapter_id in payload["adapters"]) + " |",
    ]
    for row in payload["modules"]:
        values = [f"`{row['module']}`", row["bucket"]]
        values.extend(f"`{row[adapter_id]}`" for adapter_id in payload["adapters"])
        lines.append("| " + " | ".join(values) + " |")
    lines.append("")
    return "\n".join(lines)


def write_blueprint_compatibility_docs(output_path=None, check=False):
    output_path = output_path or os.path.join(adapter_state_path, "blueprint-compatibility.md")
    expected = render_blueprint_compatibility_docs()
    if check:
        if not os.path.exists(output_path):
            print(f"{COL_RED}FAIL{COL_RESET} missing blueprint compatibility docs: {output_path}")
            return 1
        with open(output_path) as f:
            current = f.read()
        if current != expected:
            print(f"{COL_RED}FAIL{COL_RESET} stale blueprint compatibility docs: {output_path}")
            return 1
        print(f"{COL_GREEN}OK{COL_RESET}   blueprint compatibility docs {output_path}")
        return 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(expected)
    print(output_path)
    return 0


def _blueprint_ci_config_paths(root):
    paths = [os.path.join(root, "smu.toml")]
    profiles_dir = os.path.join(root, "profiles")
    if os.path.isdir(profiles_dir):
        for filename in sorted(os.listdir(profiles_dir)):
            if filename.endswith(".toml"):
                paths.append(os.path.join(profiles_dir, filename))
    for base, dirs, files in os.walk(os.path.join(root, "examples")):
        if ".git" in base.split(os.sep):
            dirs[:] = []
            continue
        if "smu.toml" in files:
            paths.append(os.path.join(base, "smu.toml"))
    return paths


def _blueprint_ci_check(name, path, ok, message):
    return {
        "name": name,
        "path": path,
        "ok": ok,
        "message": message,
    }


def blueprint_ci_contract(root=None, json_output=False, check_docs=False):
    root = os.path.abspath(root or smu_home_dir)
    checks = []
    errors = []
    summary = {
        "configs": 0,
        "provider_examples": 0,
        "workflow_examples": 0,
        "workflow_preflight": 0,
        "readiness_docs": 0,
    }
    if not os.path.isdir(root):
        errors.append(f"{root}: blueprint path does not exist")
    else:
        for path in _blueprint_ci_config_paths(root):
            summary["configs"] += 1
            rel = os.path.relpath(path, root)
            manifest = smu_contract.read_manifest(path)
            path_errors = _blueprint_mode_errors(manifest)
            provisioning = manifest.get("provisioning", {})
            mode = provisioning.get("mode") if isinstance(provisioning, dict) else None
            adapter = provisioning.get("adapter") if isinstance(provisioning, dict) else None
            checks.append(_blueprint_ci_check(
                "mode-adapter",
                rel,
                not path_errors,
                f"{mode or '<missing>'}/{adapter or '<missing>'}",
            ))
            errors.extend(f"{rel}: {error}" for error in path_errors)
        for workflow in ("rcm.yml", "nix.yml", "hybrid.yml"):
            rel = os.path.join("examples", "github-actions", workflow)
            path = os.path.join(root, rel)
            exists = os.path.exists(path)
            checks.append(_blueprint_ci_check("github-actions-example", rel, exists, "present" if exists else "missing"))
            if not exists:
                errors.append(f"{rel}: missing")
                continue
            summary["workflow_examples"] += 1
            with open(path) as f:
                workflow_text = f.read()
            has_preflight = "provisioning-adapter preflight" in workflow_text
            message = "preflight" if has_preflight else "missing preflight"
            checks.append(_blueprint_ci_check("github-actions-preflight", rel, has_preflight, message))
            if has_preflight:
                summary["workflow_preflight"] += 1
            else:
                errors.append(f"{rel}: missing preflight")
        provider_matrix = blueprint_provider_matrix(root)
        for provider in provider_matrix["providers"]:
            message = (
                f"{provider['mode'] or '<missing>'}/"
                f"{provider['adapter'] or '<missing>'}"
            )
            checks.append(_blueprint_ci_check("provider-example", provider["path"], provider["valid"], message))
            if provider["valid"]:
                summary["provider_examples"] += 1
        errors.extend(provider_matrix["errors"])
        if check_docs:
            rel = "PROVISIONING-COMPATIBILITY.md"
            doc_path = os.path.join(root, rel)
            exists = os.path.exists(doc_path)
            current = ""
            if exists:
                with open(doc_path) as f:
                    current = f.read()
            doc_ok = exists and "examples/providers/debian-vps" in current and "examples/github-actions/nix.yml" in current
            checks.append(_blueprint_ci_check("readiness-doc", rel, doc_ok, "present" if doc_ok else "missing or stale"))
            if doc_ok:
                summary["readiness_docs"] += 1
            if not doc_ok:
                errors.append(f"{rel}: missing or stale")
    payload = {
        "path": root,
        "valid": not errors,
        "errors": errors,
        "readiness": {
            "preflight": "passed" if not errors else "failed",
            "summary": summary,
        },
        "checks": checks,
    }
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in checks:
            label = f"{COL_GREEN}OK{COL_RESET}" if check["ok"] else f"{COL_RED}FAIL{COL_RESET}"
            print(f"{label} {check['name']}\t{check['path']}\t{check['message']}")
        if not errors:
            print(f"{COL_GREEN}OK{COL_RESET}   blueprint CI contract")
    return 0 if not errors else 1

def handle_blueprint_command(argv):
    command = argv[0] if argv else "schema"
    args = argv[1:]
    json_output = "--json" in args
    force = "--force" in args
    check = "--check" in args
    output_path = _option_value(args, "--output")
    if command == "init":
        mode = _option_value(args, "--mode") or "rcm"
        return blueprint_init(mode=mode, output_path=output_path, force=force, json_output=json_output)
    if command == "doctor":
        return blueprint_doctor(json_output=json_output, strict="--strict" in args)
    if command == "migrate":
        source_mode = _option_value(args, "--from") or "rcm"
        target_mode = _option_value(args, "--to") or "nix"
        return blueprint_migrate(
            source_mode=source_mode,
            target_mode=target_mode,
            output_path=output_path,
            force=force,
            json_output=json_output,
        )
    if command == "migrate-dotfiles":
        return migrate_dotfiles_command(args, force=force, json_output=json_output)
    if command == "schema":
        return write_blueprint_schema(output_path=output_path, check=check)
    if command == "ci":
        root = _option_value(args, "--path") or _option_value(args, "--root") or smu_home_dir
        return blueprint_ci_contract(root=root, json_output=json_output, check_docs=check or "--check-docs" in args)
    if command == "providers":
        root = _option_value(args, "--path") or _option_value(args, "--root") or smu_home_dir
        return print_blueprint_provider_matrix(root=root, json_output=json_output)
    if command == "recommend":
        root = _option_value(args, "--path") or _option_value(args, "--root") or smu_home_dir
        target = _option_value(args, "--target") or (args[0] if args else None)
        if "--validate" in args:
            return validate_blueprint_recommendation_config(
                target=target,
                root=root,
                input_path=output_path,
                json_output=json_output,
            )
        if "--write" in args or "--dry-run" in args:
            return write_blueprint_recommendation_config(
                target=target,
                root=root,
                output_path=output_path,
                force=force,
                dry_run="--dry-run" in args,
                json_output=json_output,
            )
        return print_blueprint_provider_recommendation(target=target, root=root, json_output=json_output)
    if command == "compatibility":
        if check or output_path:
            return write_blueprint_compatibility_docs(output_path=output_path, check=check)
        return print_provisioning_compatibility_matrix(json_output=json_output)
    if command == "dotfiles-contract":
        return dotfiles_contract_command(args, check=check, output_path=output_path, json_output=json_output)
    die("Usage: smu blueprint [init|doctor|migrate|migrate-dotfiles|schema|ci|providers|recommend|compatibility|dotfiles-contract]")

__all__ = [name for name in globals() if not name.startswith("__")]
