from .adapters import *
from .core import *
from .doctors_and_system import *
from .module_discovery import *
from .profile_commands import *
from .state import *


def client_update_repositories():
    return [
        {"name": "smu_home", "path": smu_home_dir},
        {"name": "installer", "path": installer_root},
    ]


def client_update_repository_status():
    repositories = []
    for repo in client_update_repositories():
        repositories.append({
            **repo,
            "head": git_head(repo["path"]),
            "signature": git_head_signature(repo["path"]),
            **git_upstream_sync(repo["path"]),
        })
    return repositories


def client_update_status(ref=None):
    repositories = client_update_repository_status()
    drift = config_drift_report()
    return {
        "update_lock_path": update_lock_path,
        "last_update": read_update_lock(),
        "ref": ref,
        "theme": current_theme(),
        "prompt": current_prompt(),
        "preset": current_preset(),
        "repositories": repositories,
        "updates_available": any(repo["status"] == "behind" for repo in repositories),
        "config_drift": drift,
    }


def checkout_client_update_ref(ref):
    if not ref:
        return []
    results = []
    for repo in client_update_repositories():
        before = git_head(repo["path"])
        try:
            subprocess.run(["git", "-C", repo["path"], "fetch", "--quiet", "origin"], check=False)
            subprocess.run(["git", "-C", repo["path"], "checkout", ref], check=True)
            status = "checked-out"
        except (subprocess.CalledProcessError, OSError):
            status = "failed"
        results.append({
            **repo,
            "before": before,
            "after": git_head(repo["path"]),
            "ref": ref,
            "status": status,
        })
    return results


def print_client_update_status(json_output=False, ref=None):
    status = client_update_status(ref=ref)
    if json_output:
        print(json.dumps(status, indent=2, sort_keys=True))
        return
    for repo in status["repositories"]:
        print(f"{repo['status']}\t{repo['name']}\t{repo.get('branch') or '-'}\tbehind={repo['behind']}\tahead={repo['ahead']}")
    for item in status["config_drift"]["items"]:
        print(f"drift\t{item['status']}\t{item['path']}")


def client_update_plan(validate=False, self_update_requested=False, ref=None, require_signed=False):
    actions = [
        "update-submodules",
        "resolve-profile",
        "materialize-adapters",
        "write-update-lock",
    ]
    if self_update_requested:
        actions.insert(0, "self-update")
    if ref:
        actions.insert(0, "checkout-ref")
    if require_signed:
        actions.insert(1 if ref else 0, "verify-signature")
    if validate:
        actions.append("doctor")
    return {
        "actions": actions,
        "theme": current_theme(),
        "prompt": current_prompt(),
        "preset": current_preset(),
        "smu_home": smu_home_dir,
        "ref": ref,
        "require_signed": require_signed,
    }


def client_update_snapshots():
    return [
        {"kind": "generated-config", "before": file_snapshot(path)}
        for path in generated_config_paths()
    ]


def collapse_materialize_event():
    event = last_state_event()
    if event and event.get("operation") == "materialize_adapters":
        pop_last_state_event()
        return event.get("items", [])
    return []


def client_update(dry_run=False, json_output=False, validate=False, self_update_requested=False, ref=None, yes=False, require_signed=False):
    before = client_update_repository_status()
    drift = config_drift_report()
    plan = client_update_plan(
        validate=validate,
        self_update_requested=self_update_requested,
        ref=ref,
        require_signed=require_signed,
    )
    report = {
        "dry_run": dry_run,
        "self_update": self_update_requested,
        "validate": validate,
        "yes": yes,
        "before": before,
        "config_drift": drift,
        **plan,
    }
    if dry_run:
        if json_output:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            for action_name in plan["actions"]:
                print(f"plan\t{action_name}")
        return 0

    snapshots = client_update_snapshots()
    report["ref_results"] = checkout_client_update_ref(ref)
    if any(result["status"] == "failed" for result in report["ref_results"]):
        report["exit_code"] = 1
        write_update_lock(report)
        if json_output:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    signature_failures = []
    if require_signed:
        signature_failures = [
            repo for repo in client_update_repository_status()
            if repo["signature"] != "verified"
        ]
    if signature_failures:
        report["signature_failures"] = signature_failures
        report["exit_code"] = 1
        write_update_lock(report)
        if json_output:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    if self_update_requested:
        self_update()
    update_submodules()
    write_resolved_profile()
    materialize_adapters(plan["theme"], plan["prompt"], dry_run=False)
    snapshots.extend({"kind": "adapter", **item} for item in collapse_materialize_event())
    exit_code = doctor() if validate else 0
    report["after"] = client_update_repository_status()
    report["repositories"] = report["after"]
    report["generated_config"] = generated_config_fingerprints()
    report["exit_code"] = exit_code
    write_update_lock(report)
    record_state_event("client_update", snapshots)

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


__all__ = [name for name in globals() if not name.startswith("__")]
