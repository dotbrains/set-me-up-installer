from .core import *


def _parse_provisioning_args(argv):
    parsed = {
        "args": [],
        "json_output": "--json" in argv,
        "show_all": "--all" in argv,
        "search": None,
        "profile": None,
        "action": "switch",
        "dry_run": False,
        "strict": False,
        "check": False,
        "output": None,
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--json", "--all"):
            index += 1
            continue
        if arg in ("--dry-run", "--strict"):
            parsed["dry_run" if arg == "--dry-run" else "strict"] = True
            parsed["args"].append(arg)
            index += 1
            continue
        if arg == "--check":
            parsed["check"] = True
            parsed["args"].append(arg)
            index += 1
            continue
        if arg in ("--action", "--search", "--adapter", "--profile", "--output"):
            if index + 1 >= len(argv):
                die(f"Usage: smu provisioning-adapter {arg} <value>")
            value = argv[index + 1]
            if arg == "--action":
                parsed["action"] = value
            elif arg == "--search":
                parsed["search"] = value
            elif arg == "--profile":
                parsed["profile"] = value
            elif arg == "--output":
                parsed["output"] = value
            parsed["args"].extend((arg, value))
            index += 2
            continue
        if arg in ("-m", "--modules"):
            parsed["args"].append(arg)
            index += 1
            while index < len(argv) and not argv[index].startswith("-"):
                parsed["args"].append(argv[index])
                index += 1
            continue
        parsed["args"].append(arg)
        index += 1
    return parsed


def _adapter_arg(args, default):
    for index, arg in enumerate(args):
        if arg == "--adapter" and index + 1 < len(args):
            return args[index + 1]
    return default


def _module_args(args):
    modules = []
    for index, arg in enumerate(args):
        if arg in ("-m", "--modules"):
            cursor = index + 1
            while cursor < len(args) and not args[cursor].startswith("-"):
                modules.append(args[cursor])
                cursor += 1
            break
    return modules


def handle_provisioning_adapter_command(argv):
    parsed = _parse_provisioning_args(argv)
    args = parsed["args"]
    command = args[0] if args else "list"

    if command == "list":
        list_provisioning_adapters(json_output=parsed["json_output"])
        return 0
    if command == "doctor":
        return doctor_provisioning_adapter(json_output=parsed["json_output"])
    if command == "modules":
        list_module_provisioning_adapters(
            json_output=parsed["json_output"],
            search=parsed["search"],
            show_all=parsed["show_all"],
        )
        return 0
    if command == "coverage":
        return print_provisioning_adapter_coverage(json_output=parsed["json_output"])
    if command == "parity":
        return print_provisioning_adapter_parity(
            source_adapter=_adapter_arg(args, "rcm"),
            target_adapter=_adapter_arg(args, "home-manager"),
            modules=_module_args(args),
            profile=parsed["profile"],
            json_output=parsed["json_output"],
        )
    if command == "docs":
        if parsed["check"]:
            return check_provisioning_adapter_docs(output_path=parsed["output"])
        return write_provisioning_adapter_docs(output_path=parsed["output"])
    if command == "validate":
        return validate_module_manifests(json_output=parsed["json_output"])
    if command == "profile":
        action = args[1] if len(args) > 1 else "validate"
        if action != "validate":
            die("Usage: smu provisioning-adapter profile validate [--adapter adapter] [--profile name] [--strict] [--json]")
        return validate_blueprint_profile(
            profile=parsed["profile"],
            adapter_id=_adapter_arg(args, configured_provisioning_adapter()),
            json_output=parsed["json_output"],
            strict=parsed["strict"],
        )
    if command == "audit":
        return provisioning_adapter_audit(
            adapter_id=_adapter_arg(args, configured_provisioning_adapter()),
            profile=parsed["profile"],
            modules=_module_args(args),
            json_output=parsed["json_output"],
            strict=parsed["strict"],
        )
    if command == "bootstrap":
        return print_nix_bootstrap_status(json_output=parsed["json_output"])
    if command == "migrate":
        if "compare" in args:
            return print_rcm_to_nix_migration_report(
                modules=_module_args(args),
                profile=parsed["profile"],
                target_adapter=_adapter_arg(args, "home-manager"),
                json_output=parsed["json_output"],
            )
        if "state" in args:
            return write_migration_state(
                adapter_id=_adapter_arg(args, configured_profile_provisioning_adapter(parsed["profile"])),
                profile=parsed["profile"],
                modules=_module_args(args),
                output_path=parsed["output"],
            )
        return write_migration_checklist(
            adapter_id=_adapter_arg(args, configured_profile_provisioning_adapter(parsed["profile"])),
            profile=parsed["profile"],
            modules=_module_args(args),
            output_path=parsed["output"],
        )
    if command == "scaffold":
        modules = _module_args(args)
        if len(modules) != 1:
            die("Usage: smu provisioning-adapter scaffold --adapter <nix-adapter|all> -m <module>")
        return scaffold_module_adapter(modules[0], _adapter_arg(args, "home-manager"))
    if command == "generate":
        modules = _module_args(args)
        if len(modules) != 1:
            die("Usage: smu provisioning-adapter generate --adapter home-manager -m <module> [--output path]")
        adapter_id = _adapter_arg(args, "home-manager")
        if adapter_id != "home-manager":
            die("Generate currently supports the home-manager adapter.")
        return generate_home_manager_adapter(modules[0], parsed["output"])
    if command == "plan":
        adapter_id = _adapter_arg(args, "home-manager")
        modules = _module_args(args) or list(blueprint_profile_modules(parsed["profile"]))
        if adapter_id not in NIX_IMPORT_ADAPTERS:
            die(f"Provisioning adapter '{adapter_id}' does not support Nix import planning.")
        if not modules:
            die("Usage: smu provisioning-adapter plan --adapter <nix-adapter> [-m module ...|--profile name] [--json]")
        if "flake" in args:
            return write_nix_flake(adapter_id, modules, profile=parsed["profile"], json_output=parsed["json_output"])
        if "write" in args:
            return write_nix_import_plan(adapter_id, modules, profile=parsed["profile"], json_output=parsed["json_output"])
        return print_nix_import_plan(adapter_id, modules, json_output=parsed["json_output"], profile=parsed["profile"])
    if command == "apply":
        adapter_id = _adapter_arg(args, configured_profile_provisioning_adapter(parsed["profile"]))
        modules = _module_args(args) or list(blueprint_profile_modules(parsed["profile"]))
        if not modules:
            die("Usage: smu provisioning-adapter apply --adapter <adapter> [-m module ...|--profile name] [--json]")
        return apply_provisioning_adapter_modules(
            adapter_id,
            modules,
            profile=parsed["profile"],
            json_output=parsed["json_output"],
            strict=parsed["strict"],
            dry_run=parsed["dry_run"],
            action=parsed["action"],
        )

    die("Usage: smu provisioning-adapter [list|doctor|modules|coverage|parity|docs|validate|profile|audit|bootstrap|migrate|scaffold|plan|apply] [--json]")


def handle_nix_command(argv):
    command = argv[0] if argv else "doctor"
    command_args = argv[1:]
    aliases = {
        "doctor": ["audit", "--adapter", "home-manager"],
        "init": ["plan", "flake", "--adapter", "home-manager"],
        "audit": ["audit", "--adapter", "home-manager"],
        "coverage": ["coverage"],
        "bootstrap": ["bootstrap"],
        "plan": ["plan", "--adapter", "home-manager"],
        "apply": ["apply", "--adapter", "home-manager"],
        "switch": ["apply", "--adapter", "home-manager", "--action", "switch"],
        "migrate": ["migrate", "--adapter", "home-manager"],
        "generate-adapter": ["generate", "--adapter", "home-manager"],
        "parity": ["parity"],
    }
    if command == "doctor":
        parsed = _parse_provisioning_args(command_args)
        return nix_profile_doctor(
            profile=parsed["profile"],
            adapter_id="home-manager",
            json_output=parsed["json_output"],
            strict=parsed["strict"],
        )
    if command not in aliases:
        die("Usage: smu nix [doctor|init|audit|coverage|bootstrap|plan|apply|switch|migrate|generate-adapter|parity]")
    return handle_provisioning_adapter_command(aliases[command] + command_args)


__all__ = [name for name in globals() if not name.startswith("__")]
