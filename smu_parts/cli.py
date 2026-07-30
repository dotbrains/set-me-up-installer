from .adapters import *
from .catalog_packs import *
from .catalog_registry import *
from .core import *
from .doctors_and_system import *
from .module_discovery import *
from .module_lifecycle import *
from .profile_commands import *
from .state import *
from .client_update import *


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        command_args = sys.argv[2:]
        if command in ("help", "--help"):
            raise SystemExit(print_help_topic(command_args))
        if command in ("init", "bootstrap"):
            raise SystemExit(bootstrap(command_args))
        if command == "completion":
            raise SystemExit(completion_command(command_args))
        if command == "contract":
            raise SystemExit(contract_command(command_args))
        if command == "state":
            if command_args and command_args[0] == "prune":
                raise SystemExit(state_prune(command_args[1:]))
            die("Usage: smu state prune [--dry-run] [--json]")
        if command == "profile":
            handle_profile_command(command_args)
            return
        if command == "theme":
            handle_theme_command(command_args)
            return
        if command == "prompt":
            handle_prompt_command(command_args)
            return
        if command == "preset":
            handle_preset_command(command_args)
            return
        if command == "catalog":
            if command_args and command_args[0] == "trust":
                raise SystemExit(catalog_trust_command(command_args[1:], json_output="--json" in command_args))
            handle_catalog_command(command_args)
            return
        if command == "adapter":
            handle_adapter_command(command_args)
            return
        if command == "doctor":
            if "--json" in command_args:
                raise SystemExit(print_doctor_json())
            raise SystemExit(doctor())
        if command == "status":
            json_output = "--json" in command_args
            verbose = "--verbose" in command_args or "-V" in command_args
            show_all = "--all" in command_args
            search = _option_value(command_args, "--search")
            if json_output:
                print_status_json(search=search, show_all=show_all, verbose=verbose)
            else:
                status_modules(search=search, show_all=show_all, verbose=verbose)
            return
        if command == "diff":
            modules = [arg for arg in command_args if not arg.startswith("--")]
            plan = module_change_plan(modules) if modules else []
            plan.extend(adapter_change_plan(materializable_adapters()))
            print_diff_plan(plan)
            return
        if command == "rollback":
            dry_run = "--dry-run" in command_args
            if "--json" in command_args:
                raise SystemExit(print_rollback_preview(json_output=True))
            raise SystemExit(0 if rollback_last_state_event(dry_run=dry_run) else 1)
        if command == "update":
            dry_run = "--dry-run" in command_args
            json_output = "--json" in command_args
            validate = "--validate" in command_args
            self_update_requested = "--self" in command_args
            yes = "--yes" in command_args or "-y" in command_args
            ref = _option_value(command_args, "--ref")
            require_signed = "--require-signed" in command_args
            if "schedule" in command_args:
                actions = [arg for arg in command_args if arg in ("install", "remove", "status")]
                raise SystemExit(update_schedule(actions[0] if actions else "status", json_output=json_output))
            if "baseline" in command_args or "--baseline" in command_args:
                raise SystemExit(client_update_baseline(json_output=json_output))
            if "manifest" in command_args:
                raise SystemExit(update_manifest_command(command_args, json_output=json_output))
            if "preflight" in command_args or "--preflight" in command_args:
                raise SystemExit(print_client_update_preflight(json_output=json_output, ref=ref))
            if "policy" in command_args or "--policy" in command_args:
                raise SystemExit(print_update_policy(command_args, json_output=json_output))
            if "doctor" in command_args or "--doctor" in command_args:
                raise SystemExit(print_update_policy_doctor(json_output=json_output))
            if "--check" in command_args or "--report" in command_args:
                print_client_update_status(json_output=json_output, ref=ref, send_report="--report" in command_args)
                return
            if "--rollback" in command_args:
                if "--repos" in command_args:
                    print(json.dumps({"repositories": rollback_client_update_repositories()}, indent=2, sort_keys=True))
                    return
                raise SystemExit(0 if rollback_last_state_event(dry_run=dry_run) else 1)
            raise SystemExit(client_update(
                dry_run=dry_run,
                json_output=json_output,
                validate=validate,
                self_update_requested=self_update_requested,
                ref=ref,
                yes=yes,
                require_signed=require_signed,
            ))

    parser = argparse.ArgumentParser(description="set-me-up installer")
    parser.add_argument("-v", "--version", action="version", version="set-me-up 1.0.0")
    parser.add_argument("-du", "--debian-update", action="store_true", help="Update Debian-based system")
    parser.add_argument("-mu", "--macos-update", action="store_true", help="Update MacOS system")
    parser.add_argument("-au", "--arch-update", action="store_true", help="Update Arch-based system")
    parser.add_argument("-b", "--base", action="store_true", help="Run base module")
    parser.add_argument("-nb", "--no-base", action="store_true", help="Do not run base module")
    parser.add_argument("-su", "--self-update", action="store_true", help="Update set-me-up")
    parser.add_argument("-us", "--update-submodules", action="store_true", help="Update set-me-up submodules")
    parser.add_argument("-p", "--provision", action="store_true", help="Provision given modules")
    parser.add_argument("-m", "--modules", nargs='*', default=[], help="Modules to provision")
    parser.add_argument("--lsrc", action="store_true", help="List files that will be symlinked via 'rcm' into your home directory")
    parser.add_argument("--rcup", action="store_true", help="Symlink files via 'rcm' into your home directory")
    parser.add_argument("--rcdn", action="store_true", help="Remove files that were symlinked via 'rcup")
    parser.add_argument("-cbd", "--create-boot-disk", action="store_true", help="Creates a MacOS boot disk")
    parser.add_argument("-l", "--list-modules", action="store_true", help="List available modules grouped by OS bucket")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactively pick modules with fzf (SPACE to toggle, ENTER to run)")
    parser.add_argument("-st", "--status", action="store_true", help="Show installed/missing status for visible modules")
    parser.add_argument("--status-json", action="store_true", help="Print machine-readable status as JSON")
    parser.add_argument("--diff", action="store_true", help="Print planned module and adapter changes")
    parser.add_argument("--client-update", action="store_true", help="Update smu-managed config")
    parser.add_argument("--client-update-self", action="store_true", help="With --client-update, reinstall smu before refreshing config")
    parser.add_argument("--client-update-ref", help="With --client-update, checkout a branch, tag, or commit before refreshing config")
    parser.add_argument("--client-update-require-signed", action="store_true", help="With --client-update, require signed checked-out commits")
    parser.add_argument("-u", "--uninstall", action="store_true", help="Uninstall the given modules")
    parser.add_argument("-iu", "--uninstall-interactive", action="store_true", help="Pick modules to uninstall via fzf")
    parser.add_argument("--dry-run", action="store_true", help="With --uninstall: print the plan, do nothing")
    parser.add_argument("-y", "--yes", action="store_true", help="With --uninstall: skip the confirmation prompt")
    parser.add_argument("-V", "--verbose", action="store_true", help="With --status: show per-entry detail")
    parser.add_argument("--search", metavar="QUERY", help="Filter --list-modules / --status / --interactive by substring (case-insensitive)")
    parser.add_argument("--all", action="store_true", help="With --list-modules / --status / --interactive, include modules for other OS buckets")
    parser.add_argument("--theme", choices=supported_themes(), help="Save the selected set-me-up theme before provisioning")
    parser.add_argument("--prompt", choices=supported_prompts(), help="Save the selected set-me-up prompt profile before provisioning")
    parser.add_argument("--preset", choices=supported_presets(), help="Save the selected set-me-up preset before provisioning")

    args = parser.parse_args()

    if args.preset:
        set_preset(args.preset)
    if args.theme:
        set_profile_value("SMU_THEME", args.theme, supported_themes())
    if args.prompt:
        set_profile_value("SMU_PROMPT", args.prompt, supported_prompts())

    # --------------------------------------------------------------------------------------

    # Check if 'rcm' is installed, because it is required for this script to work.
    # 'rcm' is a dotfile management tool that is used to symlink files into the home directory.
    # see: https://github.com/thoughtbot/rcm
    rcm = subprocess.call("command -v rcup &> /dev/null", shell=True) == 0

    command = ""

    if args.lsrc:
        command = "lsrc"
    elif args.rcup:
        command = "rcup"
    elif args.rcdn:
        command = "rcdn"

    # If 'rcm' is not installed, and the user is trying to run 'rcup', 'rcdn', or 'lsrc',
    if not rcm and (args.lsrc or args.rcup or args.rcdn):
        die(f"'rcm' is not installed. Please run the '{BOLD}base{NORMAL}' module prior to executing '{command}'.")

    # --------------------------------------------------------------------------------------

    if args.list_modules:
        list_modules(search=args.search, show_all=args.all)
        return

    if args.status_json:
        print_status_json(search=args.search, show_all=args.all, verbose=args.verbose)
        return

    if args.status:
        status_modules(search=args.search, show_all=args.all, verbose=args.verbose)
        return

    if args.diff:
        plan = []
        if args.modules:
            plan.extend(module_change_plan(args.modules))
        plan.extend(adapter_change_plan(materializable_adapters()))
        print_diff_plan(plan)
        return

    if args.client_update:
        raise SystemExit(client_update(
            validate=True,
            self_update_requested=args.client_update_self,
            ref=args.client_update_ref,
            yes=args.yes,
            require_signed=args.client_update_require_signed,
        ))

    if args.uninstall_interactive:
        modules = interactive_select_modules(search=args.search, show_all=args.all)
        if not modules:
            return
        uninstall_modules_batch(modules, dry_run=args.dry_run, no_confirm=args.yes)
        return

    if args.uninstall:
        modules = list(args.modules)
        if not modules:
            die("--uninstall requires -m <module> [<module> ...] (or use --uninstall-interactive).")
        uninstall_modules_batch(modules, dry_run=args.dry_run, no_confirm=args.yes)
        return

    if args.lsrc:
        list_symlinks()
    elif args.rcup:
        symlink()
    elif args.rcdn:
        remove_symlinks()
    elif args.debian_update:
        if not debian:
            die("This module is only supported on Debian-based systems.")

        update()
    elif args.macos_update:
        if not macOS:
            die("This module is only supported on MacOS.")

        update()
    elif args.arch_update:
        if not arch:
            die("This module is only supported on Arch-based systems.")

        update()
    elif args.create_boot_disk:
        if not macOS:
            die("This module is only supported on MacOS.")

        create_boot_disk()
    elif args.self_update:
        self_update()
    elif args.update_submodules:
        update_submodules()
    elif args.base:
        provision_module("base")
    elif args.provision:
        modules = list(args.modules)

        # If the 'base' module is not in the module list, add it to the beginning.
        if args.base and "base" not in modules:
            modules.insert(0, "base")

        # If 'no-base' is specified, remove the 'base' module from the module list.
        if args.no_base and "base" in modules:
            modules.remove("base")

        provision_modules_batch(modules)
    elif args.interactive:
        modules = interactive_select_modules(search=args.search, show_all=args.all)
        if not modules:
            return

        if args.base and "base" not in modules:
            modules.insert(0, "base")
        if args.no_base and "base" in modules:
            modules.remove("base")

        provision_modules_batch(modules)
    elif args.modules:
        # Handle the case where modules are specified without --provision
        print("Modules specified, but --provision flag is not set.", file=sys.stderr)
    else:
        # If no modules are specified, show help
        parser.print_help()


__all__ = [name for name in globals() if not name.startswith("__")]
