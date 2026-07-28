from .core import *


state_dir = os.path.join(config_dir, "state")
state_ledger_path = os.path.join(state_dir, "ledger.json")


def _utc_timestamp():
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def _read_json_file(path, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        warn(f"Could not read '{path}': {e}")
        return fallback


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
            print(f"{item['change']}\tmodule\t{item['module']}\t{item['state']}{detail}")
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
    elif operation == "materialize_adapters":
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
