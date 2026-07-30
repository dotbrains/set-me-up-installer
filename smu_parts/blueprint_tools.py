from .core import *


BLUEPRINT_MODES = ("rcm", "nix", "hybrid")
BLUEPRINT_MODE_ADAPTERS = {
    "rcm": "rcm",
    "nix": "home-manager",
    "hybrid": "hybrid",
}


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
    if command == "schema":
        return write_blueprint_schema(output_path=output_path, check=check)
    if command == "compatibility":
        return print_provisioning_compatibility_matrix(json_output=json_output)
    die("Usage: smu blueprint [init --mode rcm|nix|hybrid|schema|compatibility] [--json]")


__all__ = [name for name in globals() if not name.startswith("__")]
