from ..core import *


def rollback_guarantee_for_event(event):
    if not event:
        return {"coverage": "none", "automatic": False, "manual": []}
    operation = event.get("operation")
    if operation in ("materialize_adapters", "client_update"):
        return {"coverage": "full", "automatic": True, "manual": []}
    if operation == "provision_modules":
        return {
            "coverage": "partial",
            "automatic": True,
            "manual": ["Package manager side effects depend on module uninstall support."],
        }
    if operation == "uninstall_modules":
        return {"coverage": "manual", "automatic": False, "manual": ["Uninstall events are not automatically reversible."]}
    return {"coverage": "unknown", "automatic": False, "manual": [f"Unknown operation: {operation}"]}


def rollback_doctor_payload(limit=20):
    events = read_state_ledger()
    rows = []
    for event in events[-limit:]:
        rows.append({
            "id": event.get("id"),
            "operation": event.get("operation"),
            "items": len(event.get("items", [])),
            **rollback_guarantee_for_event(event),
        })
    coverage = "none"
    if rows:
        if all(row["coverage"] == "full" for row in rows):
            coverage = "full"
        elif any(row["automatic"] for row in rows):
            coverage = "partial"
        else:
            coverage = "manual"
    return {"path": state_ledger_path, "events": rows, "coverage": coverage, "total_events": len(events)}


def print_rollback_doctor(json_output=False):
    payload = rollback_doctor_payload()
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"coverage\t{payload['coverage']}")
        for row in payload["events"]:
            print(f"{row['id']}\t{row['operation']}\t{row['coverage']}\titems={row['items']}")
    return 0


def rollback_state_event(event_id=None, dry_run=False):
    event = state_event(event_id)
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
    pop_state_event(event_id)
    success(f"Rolled back {operation}")
    return True


def rollback_last_state_event(dry_run=False):
    return rollback_state_event(dry_run=dry_run)


__all__ = [name for name in globals() if not name.startswith("__")]
