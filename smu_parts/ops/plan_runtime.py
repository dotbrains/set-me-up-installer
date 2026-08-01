from ..core import *


def _plan_modules(argv):
    skip_next = False
    modules = []
    valued = {"--machine", "--profile", "--provisioning-adapter"}
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in valued:
            skip_next = True
            continue
        if arg.startswith("--"):
            continue
        modules.append(arg)
    return modules


def universal_plan_payload(argv=None):
    argv = list(argv or [])
    machine = _option_value(argv, "--machine") or _option_value(argv, "--profile")
    adapter = _option_value(argv, "--provisioning-adapter")
    submodule_scope = os.getenv("SMU_SUBMODULE_SCOPE", "all")
    modules = _plan_modules(argv)
    if machine:
        profile = machine_profile(machine)
        modules = modules or list(profile["modules"])
        adapter = adapter or profile["adapter"]
        submodule_scope = profile["submodule_scope"]
    modules = modules or list(blueprint_profile_modules(None))
    adapter = adapter or configured_profile_provisioning_adapter(None)
    module_plan = provisioning_module_change_plan(modules, adapter_id=adapter)
    payload = {
        "blueprint": {
            "repository": os.getenv("SMU_BLUEPRINT"),
            "branch": os.getenv("SMU_BLUEPRINT_BRANCH"),
            "path": smu_home_dir,
            "submodule_scope": submodule_scope,
        },
        "machine_profile": machine_profile(machine) if machine else None,
        "provisioning": {
            "adapter": adapter,
            "modules": modules,
            "plan": module_plan,
        },
        "packages": [
            {"module": item["module"], "state": item["state"], "change": item.get("change")}
            for item in module_change_plan(modules)
        ],
        "dotfiles": adapter_conflict_report(),
        "secrets": secrets_scan(smu_home_dir),
        "trust": trust_report(modules),
        "rollback": rollback_doctor_payload(),
    }
    return payload


def _print_plan_table(payload):
    print("section\titem\tstatus\tdetail")
    blueprint = payload["blueprint"]
    print(f"blueprint\trepository\tplanned\t{blueprint['repository'] or '-'}")
    print(f"blueprint\tbranch\tplanned\t{blueprint['branch'] or '-'}")
    print(f"blueprint\tsubmodules\tplanned\t{blueprint['submodule_scope']}")
    profile = payload.get("machine_profile") or {}
    print(f"profile\tmachine\tplanned\t{profile.get('id', '-')}")
    print(f"provisioning\tadapter\tplanned\t{payload['provisioning']['adapter']}")
    for item in payload["provisioning"]["plan"]:
        print(f"module\t{item['module']}\t{item['state']}\t{item['change']}")
    for item in payload["packages"]:
        print(f"package\t{item['module']}\t{item['state']}\t{item.get('change') or '-'}")
    dotfiles = payload["dotfiles"]
    print(f"dotfiles\tconflicts\t{'risk' if dotfiles['conflicted'] else 'ok'}\t{len(dotfiles['items'])}")
    secrets = payload["secrets"]
    print(f"secrets\tfindings\t{'risk' if secrets['findings'] else 'ok'}\t{len(secrets['findings'])}")
    trust = payload["trust"]
    print(f"trust\twarnings\t{'risk' if trust['warnings'] else 'ok'}\t{len(trust['warnings'])}")
    rollback = payload["rollback"]
    print(f"rollback\tcoverage\t{rollback['coverage']}\t{rollback.get('total_events', 0)} event(s)")


def universal_plan(argv):
    json_output = "--json" in argv
    strict = "--strict" in argv
    payload = universal_plan_payload(argv)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_plan_table(payload)
    failed = strict and bool(payload["secrets"]["findings"] or payload["dotfiles"]["conflicted"])
    return 1 if failed else 0


__all__ = [name for name in globals() if not name.startswith("__")]
