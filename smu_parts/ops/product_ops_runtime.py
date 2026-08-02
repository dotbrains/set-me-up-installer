from ..core import *

LOCKFILE_NAME = "smu.lock"


def inventory_payload(argv):
    path = _option_value(argv, "--inventory")
    data = _json_file(path, {}) if path else {}
    hosts = data.get("hosts") or [{"id": "localhost", "host": "localhost", "user": os.getenv("USER", "user")}]
    groups = data.get("groups", {"default": [host["id"] for host in hosts]})
    for host in hosts:
        host.setdefault("labels", [])
        host.setdefault("profile", _option_value(argv, "--profile") or "vps")
        host.setdefault("adapter", _option_value(argv, "--provisioning-adapter") or configured_profile_provisioning_adapter(None))
        host.setdefault("policy", {})
    return {"schema_version": 1, "source": path, "groups": groups, "hosts": hosts, "count": len(hosts)}


def inventory_command(argv):
    payload = inventory_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for host in payload["hosts"]:
            print(f"{host['id']}\t{host['user']}@{host['host']}\t{host['profile']}\t{host['adapter']}")
    return 0


def host_facts_payload(argv=None):
    argv = argv or []
    os_release = {}
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            for line in f:
                key, value = _parse_profile_line(line)
                if key:
                    os_release[key] = value
    packages = _package_manager_state()
    facts = {
        "os": {"system": platform.system(), "release": platform.release(), "id": os_release.get("ID")},
        "package_managers": packages,
        "shell": os.getenv("SHELL") or shutil.which("bash"),
        "sudo": bool(shutil.which("sudo")),
        "nix": bool(shutil.which("nix")),
        "home_manager": bool(shutil.which("home-manager")),
        "rcm": bool(shutil.which("rcup")),
        "disk": shutil.disk_usage(os.path.expanduser("~"))._asdict(),
        "memory": {"available": None},
        "ssh_user": os.getenv("USER", "user"),
        "cloud": {"provider": os.getenv("SMU_CLOUD_PROVIDER"), "region": os.getenv("SMU_CLOUD_REGION")},
    }
    return {"schema_version": 1, "facts": facts}


def facts_command(argv):
    payload = host_facts_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        facts = payload["facts"]
        print(f"os\t{facts['os']['system']}")
        print(f"user\t{facts['ssh_user']}")
    return 0


def plan_diff_payload(argv):
    from_path = _option_value(argv, "--from")
    to_path = _option_value(argv, "--to")
    before = _json_file(from_path, {}) if from_path else {}
    after = _json_file(to_path, {}) if to_path else universal_plan_payload(["--machine", "vps"])
    changes = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes.append({"path": key, "before": before.get(key), "after": after.get(key)})
    return {"from": from_path or "empty", "to": to_path or "current", "changes": changes, "changed": bool(changes)}


def plan_diff_command(argv):
    payload = plan_diff_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for change in payload["changes"]:
            print(f"change\t{change['path']}")
    return 0


def approval_payload(argv):
    policy = policy_payload(argv)
    requires = {
        "sudo": bool(policy["policy"].get("sudo")),
        "network": bool(policy["policy"].get("network")),
        "destructive_writes": "--destructive" in argv,
    }
    ci = os.getenv("CI", "").lower() == "true"
    dry_run = "--dry-run" in argv or "--plan" in argv
    errors = []
    if ci and not dry_run:
        errors.append("CI may only run dry-run apply plans")
    for key, required in requires.items():
        if required and f"--approve-{key.replace('_', '-')}" not in argv and "--yes" not in argv:
            errors.append(f"{key} requires approval")
    return {"policy": policy, "requires": requires, "ci": ci, "dry_run": dry_run, "errors": errors, "ok": not errors}


def approval_command(argv):
    payload = approval_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ok\t{payload['ok']}")
    return 0 if payload["ok"] else 1


def state_timeline_payload(limit=50):
    events = []
    for event in read_state_ledger()[-limit:]:
        events.append({"source": "ledger", "operation": event.get("operation"), "timestamp": event.get("timestamp"), "event": event})
    update_history = _read_json_file(update_history_path, [])
    for event in update_history[-limit:]:
        events.append({"source": "update", "operation": "update", "timestamp": event.get("timestamp"), "event": event})
    events.append({"source": "drift", "operation": "drift-doctor", "timestamp": None, "event": drift_payload(smu_home_dir)})
    events.sort(key=lambda item: item.get("timestamp") or "9999")
    return {"schema_version": 1, "events": events[-limit:], "count": min(len(events), limit)}


def state_timeline_command(argv):
    payload = state_timeline_payload(int(_option_value(argv, "--limit") or "50"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for event in payload["events"]:
            print(f"{event['source']}\t{event['operation']}")
    return 0


def blueprint_lock_payload(argv=None):
    argv = argv or []
    root = os.path.abspath(os.path.expanduser(_option_value(argv, "--root") or smu_home_dir))
    payload = {
        "schema_version": 1,
        "blueprint": {"root": root, "head": _git_head(root)},
        "adapter": configured_profile_provisioning_adapter(None),
        "modules": list(machine_profile(_option_value(argv, "--profile") or "vps")["modules"]),
        "registry": blueprint_registry_payload(),
        "packages": _package_manager_state(),
        "artifacts": config_drift_report().get("items", []),
    }
    return payload


def lock_command(argv):
    payload = blueprint_lock_payload(argv)
    output = _option_value(argv, "--output")
    if output:
        _write_json_artifact(output, payload)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"lock\t{output or LOCKFILE_NAME}")
    return 0


def bootstrap_bundle_payload(argv):
    output = _option_value(argv, "--output") or "smu-bootstrap-bundle.tar"
    profile = _option_value(argv, "--profile") or "vps"
    with tempfile.TemporaryDirectory() as tempdir:
        files = {
            "install.sh": "#!/usr/bin/env bash\nset -euo pipefail\npython3 smu.py \"$@\"\n",
            "blueprint-registry.json": json.dumps(blueprint_registry_payload(), indent=2) + "\n",
            "plan.json": json.dumps(universal_plan_payload(["--machine", profile]), indent=2) + "\n",
            "smu.lock": json.dumps(blueprint_lock_payload(["--profile", profile]), indent=2) + "\n",
        }
        for name, content in files.items():
            with open(os.path.join(tempdir, name), "w") as f:
                f.write(content)
        with zipfile.ZipFile(output, "w") as archive:
            for name in sorted(files):
                archive.write(os.path.join(tempdir, name), name)
    with open(output, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return {"output": os.path.abspath(output), "profile": profile, "files": sorted(files), "sha256": digest}


def bootstrap_bundle_command(argv):
    payload = bootstrap_bundle_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"bundle\t{payload['output']}")
    return 0


def policy_explain_payload(argv):
    payload = policy_payload(argv)
    explanations = []
    adapter = _option_value(argv, "--provisioning-adapter")
    if adapter:
        allowed = adapter in payload["policy"].get("adapters", [])
        explanations.append({"subject": f"adapter:{adapter}", "allowed": allowed, "reason": "listed in policy adapters" if allowed else "not listed in policy adapters"})
    explanations.append({"subject": "network", "allowed": bool(payload["policy"].get("network")), "reason": "policy network setting"})
    explanations.append({"subject": "sudo", "allowed": bool(payload["policy"].get("sudo")), "reason": "policy sudo setting"})
    return {**payload, "explanations": explanations}


def policy_explain_command(argv):
    payload = policy_explain_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in payload["explanations"]:
            print(f"{item['subject']}\t{item['allowed']}\t{item['reason']}")
    return 0 if payload["ok"] else 1


def golden_examples_payload():
    examples = [
        {"id": "ubuntu-vps-rcm", "target": "Ubuntu VPS", "mode": "rcm", "adapter": "rcm", "commands": ["smu blueprint init --mode rcm", "smu fleet plan --profile vps --json"]},
        {"id": "ubuntu-vps-home-manager", "target": "Ubuntu VPS", "mode": "nix", "adapter": "home-manager", "commands": ["smu blueprint init --mode nix", "smu nix switch --dry-run --json"]},
        {"id": "arch-workstation", "target": "Arch workstation", "mode": "nix", "adapter": "home-manager", "commands": ["smu facts collect --json", "smu plan --machine workstation --json"]},
        {"id": "macos-nix-darwin", "target": "macOS", "mode": "nix", "adapter": "nix-darwin", "commands": ["smu provisioning-adapter preflight --adapter nix-darwin --json"]},
        {"id": "hybrid-migration", "target": "Migration", "mode": "hybrid", "adapter": "hybrid", "commands": ["smu blueprint migrate --mode hybrid --json"]},
    ]
    return {"schema_version": 1, "examples": examples, "count": len(examples)}


def golden_examples_command(argv):
    payload = golden_examples_payload()
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for example in payload["examples"]:
            print(f"{example['id']}\t{example['adapter']}")
    return 0


def release_provenance_payload(argv):
    package = release_package_payload(_option_value(argv, "--version"), _option_value(argv, "--channel"))
    return {
        **package,
        "provenance": {
            "installer_sha": _git_head(installer_root),
            "blueprint_sha": _git_head(smu_home_dir),
            "workflow_run_url": os.getenv("GITHUB_SERVER_URL", "") + "/" + os.getenv("GITHUB_REPOSITORY", "") + "/actions/runs/" + os.getenv("GITHUB_RUN_ID", ""),
            "candidate_branch": "candidate",
            "root_readiness_run": os.getenv("SMU_ROOT_READINESS_RUN"),
            "contract_schemas": list(smu_contract.JSON_SCHEMA_CONTRACTS),
        },
    }


def provenance_command(argv):
    payload = release_provenance_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"installer_sha\t{payload['provenance']['installer_sha']}")
    return 0


def _git_head(path):
    try:
        return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


__all__ = [name for name in globals() if not name.startswith("__")]
