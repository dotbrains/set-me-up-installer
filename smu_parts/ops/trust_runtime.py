from ..core import *


TRUST_DEFAULTS = {
    "trust": "unspecified",
    "network": None,
    "requires_sudo": None,
    "writes": [],
    "rollback": "unknown",
}


def module_trust_manifest(module_name):
    path = get_module_path(module_name)
    if not path:
        return {**TRUST_DEFAULTS, "module": module_name, "state": "missing-module"}
    module_dir = os.path.dirname(path)
    manifest = read_module_manifest_for_dir(module_dir)
    trust = {**TRUST_DEFAULTS}
    for key in TRUST_DEFAULTS:
        if key in manifest:
            trust[key] = manifest[key]
    if trust["network"] is None:
        trust["network"] = os.path.basename(path) in ("packages", "brewfile") or path.endswith(".sh")
    if trust["requires_sudo"] is None:
        trust["requires_sudo"] = os.path.basename(path) == "packages"
    trust.update({"module": module_name, "path": path, "state": "ok"})
    return trust


def module_trust_errors(module_name):
    trust = module_trust_manifest(module_name)
    errors = []
    if trust["state"] != "ok":
        return [f"{module_name}: missing module"]
    if trust["trust"] not in ("first-party", "third-party", "local", "unspecified"):
        errors.append(f"{module_name}: trust must be first-party, third-party, local, or unspecified")
    if not isinstance(trust["network"], bool):
        errors.append(f"{module_name}: network must be boolean")
    if not isinstance(trust["requires_sudo"], bool):
        errors.append(f"{module_name}: requires_sudo must be boolean")
    if not isinstance(trust["writes"], list):
        errors.append(f"{module_name}: writes must be an array")
    if trust["rollback"] not in ("full", "partial", "manual", "none", "unknown"):
        errors.append(f"{module_name}: rollback must be full, partial, manual, none, or unknown")
    return errors


def trust_report(modules=None):
    modules = list(modules or [row["name"] for row in module_status_report(show_all=True)])
    rows = [module_trust_manifest(module) for module in modules]
    warnings = []
    for row in rows:
        if row.get("trust") == "unspecified":
            warnings.append(f"{row['module']}: trust metadata is unspecified")
        if row.get("rollback") in ("manual", "none", "unknown"):
            warnings.append(f"{row['module']}: rollback coverage is {row.get('rollback')}")
    return {"modules": rows, "warnings": warnings}


def trust_enforcement_payload(modules=None, profile=None, allow_sudo=False, allow_network=False, allow_unknown=False):
    if modules is None and profile:
        modules = list(blueprint_profile_modules(profile))
    rows = trust_report(modules)["modules"]
    violations = []
    for row in rows:
        module = row["module"]
        if row.get("state") != "ok":
            violations.append(f"{module}: module is missing")
        if row.get("trust") == "unspecified" and not allow_unknown:
            violations.append(f"{module}: trust metadata is unspecified")
        if row.get("network") and not allow_network:
            violations.append(f"{module}: network access requires --allow-network")
        if row.get("requires_sudo") and not allow_sudo:
            violations.append(f"{module}: sudo requires --allow-sudo")
        if row.get("rollback") in ("manual", "none", "unknown") and not allow_unknown:
            violations.append(f"{module}: rollback coverage is {row.get('rollback')}")
    return {
        "enforced": True,
        "profile": profile or "default",
        "ok": not violations,
        "modules": rows,
        "violations": violations,
    }


def trust_command(argv):
    json_output = "--json" in argv
    enforce = bool(argv and argv[0] == "enforce")
    profile = _option_value(argv, "--profile")
    modules = [arg for arg in argv if not arg.startswith("--") and arg not in ("doctor", "enforce")]
    if enforce:
        payload = trust_enforcement_payload(
            modules or None,
            profile=profile,
            allow_sudo="--allow-sudo" in argv,
            allow_network="--allow-network" in argv,
            allow_unknown="--allow-unknown" in argv,
        )
        if json_output:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for violation in payload["violations"]:
                print(f"FAIL\t{violation}")
            if payload["ok"]:
                print("OK\ttrust enforcement passed")
        return 0 if payload["ok"] else 1
    payload = trust_report(modules or None)
    payload["errors"] = [error for module in payload["modules"] for error in module_trust_errors(module["module"])]
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for row in payload["modules"]:
            print(f"{row['module']}\t{row['trust']}\tnetwork={str(row['network']).lower()}\tsudo={str(row['requires_sudo']).lower()}\trollback={row['rollback']}")
        for warning in payload["warnings"]:
            warn(warning)
    return 1 if payload["errors"] else 0


__all__ = [name for name in globals() if not name.startswith("__")]
