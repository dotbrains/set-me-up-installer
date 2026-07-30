from .adapters import *
from .core import *
from .doctors_and_system import *
from .module_discovery import *
from .profile_commands import *
from .state import *


def client_update_repositories():
    return [
        {"name": "blueprint", "path": smu_home_dir},
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
    policy = read_update_policy()
    repositories = client_update_repository_status()
    drift = config_drift_report()
    return {
        "update_lock_path": update_lock_path,
        "update_policy_path": update_policy_path,
        "update_history_path": update_history_path,
        "last_update": read_update_lock(),
        "history": read_update_history()[-5:],
        "client": client_identity(),
        "policy": policy,
        "policy_errors": validate_update_policy(),
        "rate_limit": update_rate_limit_status(policy),
        "ref": ref,
        "theme": current_theme(),
        "prompt": current_prompt(),
        "preset": current_preset(),
        "repositories": repositories,
        "updates_available": any(repo["status"] == "behind" for repo in repositories),
        "config_drift": drift,
    }


def print_client_update_payload(payload, json_output=False):
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        if isinstance(value, (str, int, bool)) or value is None:
            print(f"{key}\t{value}")


def client_update_baseline(json_output=False):
    report = {
        "baseline": True,
        "actions": ["baseline"],
        "theme": current_theme(),
        "prompt": current_prompt(),
        "preset": current_preset(),
        "ref": read_update_policy().get("ref"),
        "self_update": False,
        "validate": False,
        "exit_code": 0,
        "repositories": client_update_repository_status(),
        "generated_config": generated_config_fingerprints(),
    }
    lock = write_update_lock(report)
    payload = {"update_lock": lock, "config_drift": config_drift_report()}
    print_client_update_payload(payload, json_output=json_output)
    return 0


def _clearable_option(argv, name):
    value = _option_value(argv, name)
    if value is None:
        return None, False
    return None if value in ("", "none", "null") else value, True


def _int_option(argv, name):
    value = _option_value(argv, name)
    if value is None:
        return None, False
    try:
        return int(value), True
    except ValueError:
        die(f"{name} must be an integer.")


def update_policy_from_args(argv):
    policy = read_update_policy()
    ref, has_ref = _clearable_option(argv, "--set-ref")
    schedule, has_schedule = _clearable_option(argv, "--schedule")
    report_url, has_report_url = _clearable_option(argv, "--report-url")
    min_interval, has_min_interval = _int_option(argv, "--min-interval-seconds")
    backoff, has_backoff = _int_option(argv, "--backoff-seconds")
    history_limit, has_history_limit = _int_option(argv, "--history-limit")
    channel, has_channel = _clearable_option(argv, "--channel")
    manifest_url, has_manifest_url = _clearable_option(argv, "--manifest-url")
    manifest_sha256, has_manifest_sha256 = _clearable_option(argv, "--manifest-sha256")
    changed = False
    if has_ref:
        policy["ref"] = ref
        changed = True
    if has_schedule:
        policy["schedule"] = schedule
        changed = True
    if has_report_url:
        policy["report_url"] = report_url
        changed = True
    if has_min_interval:
        policy["min_interval_seconds"] = min_interval
        changed = True
    if has_backoff:
        policy["backoff_seconds"] = backoff
        changed = True
    if has_history_limit:
        policy["history_limit"] = history_limit
        changed = True
    if has_channel:
        policy["channel"] = channel or "stable"
        changed = True
    if has_manifest_url:
        policy["manifest_url"] = manifest_url
        changed = True
    if has_manifest_sha256:
        policy["manifest_sha256"] = manifest_sha256
        changed = True
    flag_pairs = (
        ("--require-signed", "--no-require-signed", "require_signed"),
        ("--auto-apply", "--no-auto-apply", "auto_apply"),
        ("--validate", "--no-validate", "validate"),
    )
    for enabled, disabled, key in flag_pairs:
        if enabled in argv:
            policy[key] = True
            changed = True
        if disabled in argv:
            policy[key] = False
            changed = True
    if changed:
        write_update_policy(policy)
    return policy


def print_update_policy(argv, json_output=False):
    policy = update_policy_from_args(argv)
    payload = {"path": update_policy_path, "policy": policy}
    print_client_update_payload(payload, json_output=json_output)
    return 0


def update_policy_doctor():
    policy = read_update_policy()
    report = client_update_status(ref=policy.get("ref"))
    policy_errors = validate_update_policy()
    checks = []
    checks.append({"name": "policy", "status": "present" if os.path.exists(update_policy_path) else "default"})
    checks.append({"name": "policy_schema", "status": "failed" if policy_errors else "passed", "errors": policy_errors})
    checks.append({"name": "lockfile", "status": "present" if os.path.exists(update_lock_path) else "missing"})
    checks.append({"name": "config_drift", "status": "failed" if report["config_drift"]["drifted"] else "passed"})
    checks.append({"name": "schedule", "status": "configured" if policy.get("schedule") else "manual"})
    checks.append({"name": "rate_limit", **report["rate_limit"]})
    checks.append({"name": "report_hook", "status": "configured" if policy.get("report_url") else "disabled"})
    if policy.get("require_signed"):
        unsigned = [repo for repo in report["repositories"] if repo["signature"] != "verified"]
        checks.append({"name": "signatures", "status": "failed" if unsigned else "passed", "repositories": unsigned})
    return {"policy": policy, "report": report, "checks": checks}


def print_update_policy_doctor(json_output=False):
    payload = update_policy_doctor()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            print(f"{check['status']}\t{check['name']}")
    return 1 if any(check["status"] == "failed" for check in payload["checks"]) else 0


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


def post_update_report(payload, policy=None):
    policy = policy or read_update_policy()
    report_url = policy.get("report_url")
    if not report_url:
        return {"status": "disabled"}
    try:
        request = urllib.request.Request(
            report_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"status": "sent", "code": response.status}
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
        return {"status": "failed", "error": str(e)}


def print_client_update_status(json_output=False, ref=None, send_report=False):
    status = client_update_status(ref=ref)
    if send_report:
        status["report_delivery"] = post_update_report(status, status["policy"])
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
    policy = read_update_policy()
    channel_ref, channel = update_channel_ref(policy)
    ref = ref if ref is not None else channel_ref
    validate = validate or bool(policy.get("validate"))
    require_signed = require_signed or bool(policy.get("require_signed"))
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
        "client": client_identity(),
        "channel": channel,
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
        report["report_delivery"] = post_update_report(report, policy)
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
        report["report_delivery"] = post_update_report(report, policy)
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
    report["repositories"] = [
        {**after, "before": before_item.get("head")}
        for after, before_item in zip(report["after"], before)
    ]
    report["generated_config"] = generated_config_fingerprints()
    report["exit_code"] = exit_code
    report["report_delivery"] = post_update_report(report, policy)
    write_update_lock(report)
    record_state_event("client_update", snapshots)

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


__all__ = [name for name in globals() if not name.startswith("__")]
