from .core import *


DEFAULT_PROVISIONING_ADAPTER = "rcm"

PROVISIONING_ADAPTERS = {
    "rcm": {
        "summary": "Current rcm-based dotfile and module provisioning",
        "status": "available",
    },
    "home-manager": {
        "summary": "Nix package manager plus Home Manager user provisioning",
        "status": "available",
    },
    "nix-darwin": {
        "summary": "macOS provisioning through nix-darwin",
        "status": "available",
    },
    "nixos": {
        "summary": "Full NixOS host provisioning",
        "status": "available",
    },
    "hybrid": {
        "summary": "Nix-first provisioning with rcm fallback",
        "status": "available",
    },
}


def supported_provisioning_adapters():
    return tuple(PROVISIONING_ADAPTERS.keys())


def _blueprint_config_paths():
    return (
        os.path.join(smu_home_dir, "smu.toml"),
        os.path.join(smu_home_dir, "dotfiles", "smu.toml"),
        os.path.join(smu_home_dir, ".smu.toml"),
        os.path.join(smu_home_dir, "dotfiles", ".smu.toml"),
    )


def blueprint_config_path():
    for path in _blueprint_config_paths():
        if os.path.exists(path):
            return path
    return None


def _manifest_section_value(manifest, section, key):
    value = manifest.get(section, {})
    if isinstance(value, dict):
        return value.get(key)
    return None


def configured_provisioning_adapter():
    path = blueprint_config_path()
    if not path:
        return DEFAULT_PROVISIONING_ADAPTER

    manifest = smu_contract.read_manifest(path)
    adapter = _manifest_section_value(manifest, "provisioning", "adapter")
    if not adapter:
        return DEFAULT_PROVISIONING_ADAPTER
    if adapter not in PROVISIONING_ADAPTERS:
        die(f"Unsupported provisioning adapter '{adapter}' in {path}.")
    return adapter


def blueprint_config():
    path = blueprint_config_path()
    return smu_contract.read_manifest(path) if path else {}


def _profile_section(manifest, profile):
    profile = profile or "default"
    for section_name in ("profile", "profiles"):
        section = manifest.get(section_name, {})
        if isinstance(section, dict):
            profile_section = section.get(profile, {})
            if isinstance(profile_section, dict):
                return profile_section
    return {}


def blueprint_profile_modules(profile=None):
    section = _profile_section(blueprint_config(), profile)
    modules = section.get("modules", [])
    if isinstance(modules, str):
        return tuple(item.strip() for item in modules.split(",") if item.strip())
    if isinstance(modules, list):
        return tuple(item for item in modules if isinstance(item, str) and item)
    return ()


def provisioning_adapter_status(adapter_id):
    adapter = PROVISIONING_ADAPTERS.get(adapter_id)
    if not adapter:
        die(f"Unsupported provisioning adapter '{adapter_id}'.")
    return adapter["status"]


def require_available_provisioning_adapter(adapter_id=None):
    adapter_id = adapter_id or configured_provisioning_adapter()
    status = provisioning_adapter_status(adapter_id)
    if status != "available":
        die(f"Provisioning adapter '{adapter_id}' is {status}.")
    return adapter_id


def require_rcm_provisioning_adapter(adapter_id=None):
    adapter_id = adapter_id or configured_provisioning_adapter()
    if adapter_id != DEFAULT_PROVISIONING_ADAPTER:
        die(f"Provisioning adapter '{adapter_id}' cannot run rcm shell-module provisioning.")
    return require_available_provisioning_adapter(adapter_id)


def provisioning_adapter_host_supported(adapter_id):
    if adapter_id == DEFAULT_PROVISIONING_ADAPTER:
        return True
    if adapter_id in NIX_IMPORT_ADAPTERS:
        return nix_adapter_host_supported(adapter_id)
    if adapter_id == "hybrid":
        return provisioning_adapter_host_supported(configured_hybrid_nix_adapter())
    return False


def configured_hybrid_nix_adapter():
    manifest = blueprint_config()
    adapter = _manifest_section_value(manifest, "provisioning", "nix_adapter")
    if adapter and adapter not in NIX_IMPORT_ADAPTERS:
        die(f"Unsupported hybrid nix_adapter '{adapter}'.")
    return adapter or "home-manager"


def list_provisioning_adapters(json_output=False):
    current = configured_provisioning_adapter()
    entries = []
    for adapter_id, adapter in PROVISIONING_ADAPTERS.items():
        entries.append({
            "id": adapter_id,
            "summary": adapter["summary"],
            "status": adapter["status"],
            "current": adapter_id == current,
        })

    if json_output:
        print(json.dumps({"current": current, "adapters": entries}, indent=2, sort_keys=True))
        return

    for entry in entries:
        marker = "*" if entry["current"] else " "
        print(f"{marker} {entry['id']}\t{entry['status']}\t{entry['summary']}")


def doctor_provisioning_adapter(json_output=False):
    current = configured_provisioning_adapter()
    status = provisioning_adapter_status(current)
    path = blueprint_config_path()
    payload = {
        "adapter": current,
        "status": status,
        "config": path,
        "host_supported": provisioning_adapter_host_supported(current),
    }
    payload["can_apply"] = status == "available" and payload["host_supported"]

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["can_apply"] else 1

    print(f"adapter\t{current}")
    print(f"status\t{status}")
    print(f"config\t{path or '<default>'}")
    print(f"host_supported\t{str(payload['host_supported']).lower()}")
    return 0 if payload["can_apply"] else 1


def module_provisioning_adapter_report(search=None, show_all=False):
    buckets = discover_modules()
    current = _current_os_bucket()
    report = []
    for bucket, modules in buckets.items():
        if not show_all and current and bucket not in (current, "universal"):
            continue
        for name, kind in modules:
            if search and search.lower() not in name.lower():
                continue
            module_dir = os.path.join(module_path, bucket, name)
            adapter_ids = module_adapter_ids(module_dir)
            if not adapter_ids and kind in LEGACY_MODULE_MARKERS:
                adapter_ids = (DEFAULT_PROVISIONING_ADAPTER,)
            report.append({
                "bucket": bucket,
                "name": name,
                "kind": kind,
                "adapters": list(adapter_ids),
            })
    return report


def list_module_provisioning_adapters(json_output=False, search=None, show_all=False):
    rows = module_provisioning_adapter_report(search=search, show_all=show_all)
    if json_output:
        print(json.dumps({"modules": rows}, indent=2, sort_keys=True))
        return
    if not rows:
        warn("No modules found.")
        return
    for row in rows:
        adapters = ",".join(row["adapters"]) if row["adapters"] else "<none>"
        print(f"{row['bucket']}\t{row['name']}\t{row['kind']}\t{adapters}")


def _module_dir_from_path(path):
    return os.path.dirname(path) if path else None

def module_provisioning_implementations(module_name):
    path = get_module_path(module_name)
    if not path:
        return {}
    module_dir = _module_dir_from_path(path)
    implementations = dict(module_manifest_adapters(module_dir))
    if not implementations and os.path.basename(path) != MODULE_MANIFEST:
        implementations[DEFAULT_PROVISIONING_ADAPTER] = {"path": "."}
    return implementations


def module_provisioning_implementation_path(module_name, implementation):
    path = get_module_path(module_name)
    if not path or not implementation:
        return None
    module_dir = _module_dir_from_path(path)
    implementation_path = implementation.get("path", ".")
    if implementation_path == ".":
        return module_dir
    return os.path.normpath(os.path.join(module_dir, implementation_path))


def resolve_module_provisioning_adapter(module_name, adapter_id=None):
    adapter_id = adapter_id or configured_provisioning_adapter()
    if adapter_id not in PROVISIONING_ADAPTERS:
        die(f"Unsupported provisioning adapter '{adapter_id}'.")

    implementations = module_provisioning_implementations(module_name)
    if not implementations:
        return {
            "module": module_name,
            "adapter": adapter_id,
            "resolved_adapter": None,
            "state": "missing-module",
            "available_adapters": [],
            "implementation": None,
        }

    if adapter_id in implementations:
        implementation = implementations[adapter_id]
        return {
            "module": module_name,
            "adapter": adapter_id,
            "resolved_adapter": adapter_id,
            "state": "ready",
            "available_adapters": sorted(implementations.keys()),
            "implementation": implementation,
            "implementation_path": module_provisioning_implementation_path(module_name, implementation),
        }

    if adapter_id == "hybrid" and DEFAULT_PROVISIONING_ADAPTER in implementations:
        implementation = implementations[DEFAULT_PROVISIONING_ADAPTER]
        return {
            "module": module_name,
            "adapter": adapter_id,
            "resolved_adapter": DEFAULT_PROVISIONING_ADAPTER,
            "state": "fallback",
            "available_adapters": sorted(implementations.keys()),
            "implementation": implementation,
            "implementation_path": module_provisioning_implementation_path(module_name, implementation),
        }

    return {
        "module": module_name,
        "adapter": adapter_id,
        "resolved_adapter": None,
        "state": "missing-adapter",
        "available_adapters": sorted(implementations.keys()),
        "implementation": None,
        "implementation_path": None,
    }


def apply_provisioning_adapter_modules(adapter_id=None, modules=None, profile=None, json_output=False):
    from .module_lifecycle import provision_modules_batch

    adapter_id = require_available_provisioning_adapter(adapter_id)
    if adapter_id == DEFAULT_PROVISIONING_ADAPTER:
        provision_modules_batch(modules or blueprint_profile_modules(profile))
        return 0
    if adapter_id in NIX_IMPORT_ADAPTERS:
        return apply_nix_import_adapter(adapter_id, modules, profile=profile, json_output=json_output)
    if adapter_id == "hybrid":
        return apply_hybrid_modules(modules, profile=profile, json_output=json_output)
    die(f"Provisioning adapter '{adapter_id}' cannot apply modules yet.")


def provisioning_module_change_plan(modules, adapter_id=None):
    adapter_id = adapter_id or configured_provisioning_adapter()
    plan = []
    for module in modules:
        state, detail = module_status(module)
        resolution = resolve_module_provisioning_adapter(module, adapter_id)
        plan.append({
            "module": module,
            "state": state,
            "detail": detail,
            "change": "install" if state != "installed" else "verify",
            "provisioning_adapter": adapter_id,
            "resolved_adapter": resolution["resolved_adapter"],
            "adapter_state": resolution["state"],
            "available_adapters": resolution["available_adapters"],
        })
    return plan


def handle_provisioning_adapter_command(argv):
    json_output = "--json" in argv
    show_all = "--all" in argv
    search = None
    profile = None
    action_name = "switch"
    dry_run = False
    args = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--json", "--all"):
            index += 1
            continue
        if arg == "--dry-run":
            dry_run = True
            args.append(arg)
            index += 1
            continue
        if arg == "--action":
            if index + 1 >= len(argv):
                die("Usage: smu provisioning-adapter apply --action [build|test|switch]")
            action_name = argv[index + 1]
            args.extend((arg, action_name))
            index += 2
            continue
        if arg == "--search":
            if index + 1 >= len(argv):
                die("Usage: smu provisioning-adapter modules [--json] [--all] [--search query]")
            search = argv[index + 1]
            index += 2
            continue
        if arg in ("-m", "--modules"):
            args.append(arg)
            index += 1
            while index < len(argv) and not argv[index].startswith("-"):
                args.append(argv[index])
                index += 1
            continue
        if arg == "--adapter":
            if index + 1 >= len(argv):
                die("Usage: smu provisioning-adapter plan --adapter home-manager -m module [module ...]")
            args.extend((arg, argv[index + 1]))
            index += 2
            continue
        if arg == "--profile":
            if index + 1 >= len(argv):
                die("Usage: smu provisioning-adapter plan --profile name")
            profile = argv[index + 1]
            args.extend((arg, profile))
            index += 2
            continue
        args.append(arg)
        index += 1
    command = args[0] if args else "list"

    if command == "list":
        list_provisioning_adapters(json_output=json_output)
        return 0
    if command == "doctor":
        return doctor_provisioning_adapter(json_output=json_output)
    if command == "modules":
        list_module_provisioning_adapters(json_output=json_output, search=search, show_all=show_all)
        return 0
    if command in ("validate", "audit"):
        return validate_module_manifests(json_output=json_output)
    if command == "scaffold":
        adapter_id = "home-manager"
        modules = []
        idx = 1
        while idx < len(args):
            if args[idx] == "--adapter":
                adapter_id = args[idx + 1]
                idx += 2
                continue
            if args[idx] in ("-m", "--modules"):
                while idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    modules.append(args[idx + 1])
                    idx += 1
                break
            idx += 1
        if len(modules) != 1:
            die("Usage: smu provisioning-adapter scaffold --adapter <nix-adapter> -m <module>")
        return scaffold_module_adapter(modules[0], adapter_id)
    if command == "plan":
        adapter_id = "home-manager"
        modules = []
        write_output = "write" in args
        flake_output = "flake" in args
        idx = 1
        while idx < len(args):
            if args[idx] in ("write", "flake"):
                idx += 1
                continue
            if args[idx] == "--adapter":
                adapter_id = args[idx + 1]
                idx += 2
                continue
            if args[idx] in ("-m", "--modules"):
                while idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    modules.append(args[idx + 1])
                    idx += 1
                break
            idx += 1
        if adapter_id not in NIX_IMPORT_ADAPTERS:
            die(f"Provisioning adapter '{adapter_id}' does not support Nix import planning.")
        if not modules:
            modules = list(blueprint_profile_modules(profile))
        if not modules:
            die("Usage: smu provisioning-adapter plan --adapter <nix-adapter> [-m module ...|--profile name] [--json]")
        if flake_output:
            return write_nix_flake(adapter_id, modules, profile=profile, json_output=json_output)
        if write_output:
            return write_nix_import_plan(adapter_id, modules, profile=profile, json_output=json_output)
        return print_nix_import_plan(adapter_id, modules, json_output=json_output, profile=profile)
    if command == "apply":
        adapter_id = configured_provisioning_adapter()
        modules = []
        idx = 1
        while idx < len(args):
            if args[idx] == "--adapter":
                adapter_id = args[idx + 1]
                idx += 2
                continue
            if args[idx] in ("-m", "--modules"):
                while idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    modules.append(args[idx + 1])
                    idx += 1
                break
            idx += 1
        if not modules:
            modules = list(blueprint_profile_modules(profile))
        if not modules:
            die("Usage: smu provisioning-adapter apply --adapter <adapter> [-m module ...|--profile name] [--json]")
        if adapter_id in NIX_IMPORT_ADAPTERS:
            return apply_nix_import_adapter(
                adapter_id,
                modules,
                profile=profile,
                json_output=json_output,
                dry_run=dry_run,
                action=action_name,
            )
        return apply_provisioning_adapter_modules(adapter_id, modules, profile=profile, json_output=json_output)

    die("Usage: smu provisioning-adapter [list|doctor|modules|validate|audit|scaffold|plan|apply] [--json]")


__all__ = [name for name in globals() if not name.startswith("__")]
