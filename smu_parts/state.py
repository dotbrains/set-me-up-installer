from .core import *


state_dir = os.path.join(config_dir, "state")
state_ledger_path = os.path.join(state_dir, "ledger.json")


def _utc_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _read_json_file(path, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        warn(f"Could not read '{path}': {e}")
        return fallback


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp_path, path)


def git_head(path):
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def git_branch(path):
    try:
        result = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def git_upstream_sync(path):
    branch = git_branch(path)
    if not branch:
        return {"branch": None, "status": "detached", "ahead": 0, "behind": 0}
    try:
        subprocess.run(["git", "-C", path, "fetch", "--quiet", "origin"], check=False)
        result = subprocess.run(
            ["git", "-C", path, "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"],
            check=True,
            capture_output=True,
            text=True,
        )
        ahead, behind = (int(value) for value in result.stdout.split())
    except (subprocess.CalledProcessError, OSError, ValueError):
        return {"branch": branch, "status": "unknown", "ahead": 0, "behind": 0}
    if ahead and behind:
        status = "diverged"
    elif ahead:
        status = "ahead"
    elif behind:
        status = "behind"
    else:
        status = "current"
    return {"branch": branch, "status": status, "ahead": ahead, "behind": behind}


def git_head_signature(path):
    try:
        subprocess.run(
            ["git", "-C", path, "verify-commit", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return "verified"
    except subprocess.CalledProcessError:
        return "unverified"
    except OSError:
        return "unknown"


def file_sha256(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generated_config_paths():
    paths = [resolved_profile_path, adapter_manifest_json_path, adapter_manifest_env_path]
    for entry in _read_adapter_manifest():
        target = entry.get("target")
        if target:
            paths.append(target)
    return sorted(set(paths))


def generated_config_fingerprints():
    return [
        {
            "path": path,
            "exists": os.path.lexists(path),
            "sha256": file_sha256(path),
        }
        for path in generated_config_paths()
    ]


def config_drift_report():
    last = read_update_lock()
    expected = {
        item["path"]: item
        for item in last.get("generated_config", [])
        if item.get("path")
    }
    current = generated_config_fingerprints()
    drift = []
    current_paths = {item["path"] for item in current}
    for item in current:
        previous = expected.get(item["path"])
        if not previous:
            drift.append({**item, "status": "untracked"})
        elif previous.get("sha256") != item.get("sha256") or previous.get("exists") != item.get("exists"):
            drift.append({**item, "status": "changed", "expected": previous})
    for path, previous in expected.items():
        if path not in current_paths:
            drift.append({"path": path, "exists": False, "sha256": None, "status": "missing", "expected": previous})
    return {"drifted": bool(drift), "items": drift}


def read_update_lock():
    data = _read_json_file(update_lock_path, {})
    return data if isinstance(data, dict) else {}


def default_update_policy():
    return {
        "ref": None,
        "require_signed": False,
        "validate": False,
        "auto_apply": False,
        "schedule": None,
        "report_url": None,
        "min_interval_seconds": 0,
        "backoff_seconds": 0,
        "history_limit": 20,
        "channel": "stable",
        "channels": {"stable": None},
        "manifest_url": None,
        "manifest_sha256": None,
    }


def update_policy_schema():
    return {
        "ref": ("optional-string", None),
        "require_signed": ("bool", False),
        "validate": ("bool", False),
        "auto_apply": ("bool", False),
        "schedule": ("optional-string", None),
        "report_url": ("optional-https-url", None),
        "min_interval_seconds": ("nonnegative-int", 0),
        "backoff_seconds": ("nonnegative-int", 0),
        "history_limit": ("positive-int", 20),
        "channel": ("string", "stable"),
        "channels": ("string-map", {"stable": None}),
        "manifest_url": ("optional-https-url", None),
        "manifest_sha256": ("optional-sha256", None),
    }


def read_raw_update_policy():
    data = _read_json_file(update_policy_path, {})
    return data if isinstance(data, dict) else {}


def validate_update_policy(policy=None):
    raw = read_raw_update_policy() if policy is None else dict(policy)
    schema = update_policy_schema()
    errors = []
    for key in sorted(set(raw) - set(schema)):
        errors.append({"field": key, "message": "unknown policy field"})
    for key, (kind, _) in schema.items():
        value = raw.get(key, default_update_policy()[key])
        if kind == "bool" and not isinstance(value, bool):
            errors.append({"field": key, "message": "must be a boolean"})
        elif kind == "optional-string" and value is not None and not isinstance(value, str):
            errors.append({"field": key, "message": "must be a string or null"})
        elif kind == "string" and not isinstance(value, str):
            errors.append({"field": key, "message": "must be a string"})
        elif kind == "string-map":
            if not isinstance(value, dict) or not all(isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in value.items()):
                errors.append({"field": key, "message": "must map strings to strings or null"})
        elif kind == "optional-https-url":
            if value is not None and not isinstance(value, str):
                errors.append({"field": key, "message": "must be an HTTPS URL or null"})
            elif value and not value.startswith("https://"):
                errors.append({"field": key, "message": "must use https://"})
        elif kind == "optional-sha256" and value is not None and not (
            isinstance(value, str) and re.match(r"^[0-9a-f]{64}$", value)
        ):
            errors.append({"field": key, "message": "must be a 64-character lowercase sha256 or null"})
        elif kind == "nonnegative-int" and (not isinstance(value, int) or value < 0):
            errors.append({"field": key, "message": "must be an integer >= 0"})
        elif kind == "positive-int" and (not isinstance(value, int) or value < 1):
            errors.append({"field": key, "message": "must be an integer >= 1"})
    return errors


def read_update_policy():
    policy = default_update_policy()
    data = read_raw_update_policy()
    if isinstance(data, dict):
        for key in policy:
            if key in data:
                policy[key] = data[key]
    return policy


def write_update_policy(policy):
    merged = default_update_policy()
    merged.update({key: policy[key] for key in merged if key in policy})
    errors = validate_update_policy(merged)
    if errors:
        die("; ".join(f"{error['field']}: {error['message']}" for error in errors))
    write_json_file(update_policy_path, merged)
    return merged


def read_update_history():
    data = _read_json_file(update_history_path, [])
    return data if isinstance(data, list) else []


def append_update_history(report):
    entry = {
        "updated_at": report.get("updated_at") or _utc_timestamp(),
        "theme": report.get("theme"),
        "prompt": report.get("prompt"),
        "preset": report.get("preset"),
        "ref": report.get("ref"),
        "self_update": report.get("self_update", False),
        "validate": report.get("validate", False),
        "exit_code": report.get("exit_code", 0),
        "actions": report.get("actions", []),
        "repositories": report.get("repositories", []),
        "report_delivery": report.get("report_delivery"),
    }
    history = read_update_history()
    history.append(entry)
    limit = read_update_policy().get("history_limit", 20)
    write_json_file(update_history_path, history[-limit:])
    return entry


def update_rate_limit_status(policy=None):
    policy = policy or read_update_policy()
    interval = policy.get("min_interval_seconds", 0)
    backoff = policy.get("backoff_seconds", 0)
    if not interval and not backoff:
        return {"status": "ready", "wait_seconds": 0}
    history = read_update_history()
    last = history[-1] if history else None
    if not last:
        return {"status": "ready", "wait_seconds": 0}
    last_at = last.get("updated_at")
    try:
        updated_at = datetime.datetime.fromisoformat(last_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return {"status": "unknown", "wait_seconds": 0}
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
    window = backoff if last.get("exit_code", 0) else interval
    elapsed = (datetime.datetime.now(datetime.timezone.utc) - updated_at).total_seconds()
    wait_seconds = max(0, int(window - elapsed))
    return {"status": "waiting" if wait_seconds else "ready", "wait_seconds": wait_seconds}


def write_update_lock(report):
    updated_at = _utc_timestamp()
    lock = {
        "updated_at": updated_at,
        "smu_home": smu_home_dir,
        "installer_root": installer_root,
        "theme": report.get("theme"),
        "prompt": report.get("prompt"),
        "preset": report.get("preset"),
        "ref": report.get("ref"),
        "self_update": report.get("self_update", False),
        "validate": report.get("validate", False),
        "exit_code": report.get("exit_code", 0),
        "repositories": report.get("repositories", []),
        "actions": report.get("actions", []),
        "generated_config": report.get("generated_config", []),
    }
    write_json_file(update_lock_path, lock)
    append_update_history({**report, **lock})
    return lock


def read_state_ledger():
    data = _read_json_file(state_ledger_path, [])
    return data if isinstance(data, list) else []


def write_state_ledger(entries):
    os.makedirs(state_dir, exist_ok=True)
    tmp_path = f"{state_ledger_path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(entries, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp_path, state_ledger_path)


def record_state_event(operation, items):
    entry = {
        "id": _utc_timestamp(),
        "operation": operation,
        "items": items,
    }
    entries = read_state_ledger()
    entries.append(entry)
    write_state_ledger(entries)
    return entry


def last_state_event():
    entries = read_state_ledger()
    return entries[-1] if entries else None


def pop_last_state_event():
    entries = read_state_ledger()
    if not entries:
        return None
    event = entries.pop()
    write_state_ledger(entries)
    return event


def file_snapshot(path):
    if not os.path.lexists(path):
        return {"exists": False, "path": path}
    snapshot = {"exists": True, "path": path}
    if os.path.islink(path):
        snapshot["type"] = "symlink"
        snapshot["link_target"] = os.readlink(path)
        return snapshot
    if os.path.isfile(path):
        snapshot["type"] = "file"
        with open(path, "rb") as f:
            snapshot["content_hex"] = f.read().hex()
        return snapshot
    snapshot["type"] = "other"
    return snapshot


def restore_file_snapshot(snapshot):
    path = snapshot["path"]
    if os.path.lexists(path):
        if os.path.isdir(path) and not os.path.islink(path):
            die(f"Cannot rollback directory target: {path}")
        os.unlink(path)
    if not snapshot.get("exists"):
        return
    if snapshot.get("type") == "symlink":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(snapshot["link_target"], path)
        return
    if snapshot.get("type") == "file":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(bytes.fromhex(snapshot.get("content_hex", "")))
        return
    die(f"Cannot rollback non-file target: {path}")


def adapter_change_plan(entries):
    plan = []
    for entry in entries:
        target = entry["target"]
        if os.path.islink(target):
            state = "replace-symlink"
        elif os.path.exists(target):
            state = "overwrite-file"
        else:
            state = "create"
        planned = dict(entry)
        planned["change"] = state
        plan.append(planned)
    return plan


def module_change_plan(modules):
    plan = []
    for module in modules:
        state, detail = module_status(module)
        plan.append({
            "module": module,
            "state": state,
            "detail": detail,
            "change": "install" if state != "installed" else "verify",
        })
    return plan


def print_diff_plan(plan):
    for item in plan:
        if "module" in item:
            detail = f"\t{item['detail']}" if item.get("detail") else ""
            adapter = item.get("resolved_adapter") or item.get("provisioning_adapter")
            adapter_state = item.get("adapter_state")
            adapter_detail = ""
            if adapter:
                adapter_detail = f"\tadapter={adapter}"
            if adapter_state and adapter_state != "ready":
                adapter_detail = f"{adapter_detail}\tadapter_state={adapter_state}"
            print(f"{item['change']}\tmodule\t{item['module']}\t{item['state']}{adapter_detail}{detail}")
        else:
            print(f"{item['change']}\tadapter\t{item['mode']}\t{item['source']}\t{item['target']}")


def status_report(search=None, show_all=False, verbose=False):
    modules = module_status_report(search=search, show_all=show_all, verbose=verbose)
    adapters = []
    for entry in _read_adapter_manifest():
        item = dict(entry)
        item["exists"] = os.path.exists(entry.get("target", ""))
        adapters.append(item)
    return {
        "modules": modules,
        "adapters": adapters,
        "ledger": {
            "path": state_ledger_path,
            "entries": len(read_state_ledger()),
            "last": last_state_event(),
        },
        "updates": {
            "path": update_lock_path,
            "last": read_update_lock(),
            "policy_path": update_policy_path,
            "policy": read_update_policy(),
            "policy_errors": validate_update_policy(),
            "history_path": update_history_path,
            "history_entries": len(read_update_history()),
            "config_drift": config_drift_report(),
        },
    }


def print_status_json(search=None, show_all=False, verbose=False):
    print(json.dumps(status_report(search, show_all, verbose), indent=2, sort_keys=True))


def rollback_last_state_event(dry_run=False):
    event = last_state_event()
    if not event:
        warn("No state events to rollback.")
        return False
    if dry_run:
        print(json.dumps(event, indent=2, sort_keys=True))
        return True
    operation = event.get("operation")
    items = event.get("items", [])
    if operation == "provision_modules":
        for item in reversed(items):
            uninstall_module(item["module"], dry_run=False)
    elif operation in ("materialize_adapters", "client_update"):
        for item in reversed(items):
            restore_file_snapshot(item["before"])
    elif operation == "uninstall_modules":
        die("Rollback for uninstall events is not automatic.")
    else:
        die(f"Unknown rollback operation: {operation}")
    pop_last_state_event()
    success(f"Rolled back {operation}")
    return True


__all__ = [name for name in globals() if not name.startswith("__")]
