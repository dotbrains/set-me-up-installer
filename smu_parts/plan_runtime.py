from .core import *


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


def universal_plan(argv):
    json_output = "--json" in argv
    strict = "--strict" in argv
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
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"blueprint\t{payload['blueprint']['repository'] or '-'}\t{payload['blueprint']['branch'] or '-'}")
        print(f"submodules\t{payload['blueprint']['submodule_scope']}")
        print(f"adapter\t{adapter}")
        for item in module_plan:
            print(f"{item['change']}\tmodule\t{item['module']}\t{item['state']}")
        print(f"secrets\t{len(payload['secrets']['findings'])}")
        print(f"rollback\t{payload['rollback']['coverage']}")
    failed = strict and bool(payload["secrets"]["findings"] or payload["dotfiles"]["conflicted"])
    return 1 if failed else 0


__all__ = [name for name in globals() if not name.startswith("__")]
