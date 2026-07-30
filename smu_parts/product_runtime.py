from .update_runtime import *


def adapter_conflict_report(theme=None, prompt=None):
    conflicts = []
    for entry in materializable_adapters(theme, prompt):
        target = entry["target"]
        if not os.path.lexists(target):
            continue
        snapshot = file_snapshot(target)
        source_hash = file_sha256(entry["source"])
        target_hash = file_sha256(target)
        if snapshot.get("type") == "symlink" and snapshot.get("link_target") == entry["source"]:
            status = "managed"
        elif source_hash and target_hash and source_hash == target_hash:
            status = "same-content"
        else:
            status = "conflict"
        conflicts.append({**entry, "status": status, "target_sha256": target_hash, "source_sha256": source_hash})
    return {"conflicted": any(item["status"] == "conflict" for item in conflicts), "items": conflicts}


def rollback_preview():
    event = last_state_event()
    return {
        "event": event,
        "changes": [
            {"path": item.get("before", {}).get("path"), "restore": item.get("before", {}).get("exists", False)}
            for item in (event or {}).get("items", [])
        ],
    }


def print_rollback_preview(json_output=False):
    preview = rollback_preview()
    if json_output:
        print(json.dumps(preview, indent=2, sort_keys=True))
    else:
        for item in preview["changes"]:
            print(f"restore\t{item['restore']}\t{item['path']}")
    return 0 if preview["event"] else 1


def health_report():
    preset = current_preset()
    theme = current_theme()
    prompt = current_prompt()
    return {
        "preset": {"id": preset, "valid": preset in supported_presets()},
        "theme": {"id": theme, "valid": theme in supported_themes()},
        "prompt": {"id": prompt, "valid": prompt in supported_prompts()},
        "catalogs": {
            "path": catalogs_path,
            "errors": catalog_health_errors(),
            "trust": read_catalog_trust(),
        },
        "adapters": adapter_conflict_report(theme, prompt),
        "status": status_report(),
        "updates": client_update_preflight(),
    }


def print_doctor_json():
    report = health_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    failed = (
        not report["preset"]["valid"]
        or not report["theme"]["valid"]
        or not report["prompt"]["valid"]
        or bool(report["catalogs"]["errors"])
        or report["adapters"]["conflicted"]
        or report["updates"]["preflight"] == "failed"
    )
    return 1 if failed else 0


def catalog_health_errors():
    errors = []
    errors.extend(_catalog_registry_errors())
    errors.extend(_catalog_registry_lock_errors())
    return errors


def read_catalog_trust():
    data = _read_json_file(catalog_trust_path, {"trusted_publishers": {}, "trusted_registries": {}})
    return data if isinstance(data, dict) else {"trusted_publishers": {}, "trusted_registries": {}}


def write_catalog_trust(data):
    trust = read_catalog_trust()
    for key in ("trusted_publishers", "trusted_registries"):
        if key in data:
            trust[key] = data[key]
    write_json_file(catalog_trust_path, trust)
    return trust


def catalog_trust_command(argv, json_output=False):
    trust = read_catalog_trust()
    command = argv[0] if argv else "status"
    if command == "publisher":
        if len(argv) < 2:
            die("Usage: smu catalog trust publisher <id>")
        trust.setdefault("trusted_publishers", {})[argv[1]] = {"trusted_at": _utc_timestamp()}
        write_catalog_trust(trust)
    elif command == "registry":
        if len(argv) < 2:
            die("Usage: smu catalog trust registry <name>")
        trust.setdefault("trusted_registries", {})[argv[1]] = {"trusted_at": _utc_timestamp()}
        write_catalog_trust(trust)
    elif command != "status":
        die("Usage: smu catalog trust [status|publisher <id>|registry <name>]")
    payload = {"path": catalog_trust_path, "trust": read_catalog_trust()}
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"trusted_publishers\t{len(payload['trust'].get('trusted_publishers', {}))}")
        print(f"trusted_registries\t{len(payload['trust'].get('trusted_registries', {}))}")
    return 0


def bootstrap_plan(argv):
    preset = _option_value(argv, "--preset") or current_preset()
    theme = _option_value(argv, "--theme") or current_theme()
    prompt = _option_value(argv, "--prompt") or current_prompt()
    return {
        "actions": ["set-profile", "write-resolved-profile", "materialize-adapters", "baseline"],
        "preset": preset,
        "theme": theme,
        "prompt": prompt,
        "adapter_conflicts": adapter_conflict_report(theme, prompt),
    }


def bootstrap(argv):
    json_output = "--json" in argv
    dry_run = "--dry-run" in argv
    plan = bootstrap_plan(argv)
    if dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True) if json_output else "\n".join(plan["actions"]))
        return 0
    if plan["adapter_conflicts"]["conflicted"] and "--force" not in argv:
        print(json.dumps(plan, indent=2, sort_keys=True) if json_output else "adapter conflicts detected")
        return 1
    output = io.StringIO()
    sink = contextlib.redirect_stdout(output) if json_output else contextlib.nullcontext()
    with sink:
        set_preset(plan["preset"])
        set_profile_value("SMU_THEME", plan["theme"], supported_themes())
        set_profile_value("SMU_PROMPT", plan["prompt"], supported_prompts())
        write_resolved_profile()
        materialize_adapters(plan["theme"], plan["prompt"], dry_run=False, force="--force" in argv)
        write_update_lock({
            "baseline": True,
            "actions": plan["actions"],
            "theme": plan["theme"],
            "prompt": plan["prompt"],
            "preset": plan["preset"],
            "exit_code": 0,
            "repositories": client_update_repository_status(),
            "generated_config": generated_config_fingerprints(),
        })
    if json_output:
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
