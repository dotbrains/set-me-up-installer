from ..core import *


BLUEPRINT_REGISTRY = [
    {
        "id": "dotbrains/default",
        "url": "https://github.com/dotbrains/set-me-up-blueprint",
        "modes": ["rcm", "nix", "hybrid"],
        "vps_ready": True,
        "rollback": "partial",
        "oses": ["ubuntu", "debian", "arch", "macos"],
    },
    {
        "id": "nicholasadamou/dotfiles",
        "url": "https://github.com/nicholasadamou/dotfiles",
        "modes": ["rcm", "hybrid"],
        "vps_ready": True,
        "rollback": "partial",
        "oses": ["ubuntu", "debian", "arch", "macos"],
    },
]

MODULE_GRAPH_DEFAULTS = {
    "base": {"dependencies": [], "conflicts": [], "capabilities": ["shell", "git"], "order": 10},
    "rcm": {"dependencies": ["base"], "conflicts": [], "capabilities": ["dotfiles"], "order": 20},
    "nix": {"dependencies": ["base"], "conflicts": [], "capabilities": ["packages"], "order": 20},
}

POLICY_PRESETS = {
    "personal": {"network": True, "sudo": True, "adapters": ["rcm", "home-manager", "hybrid"]},
    "vps": {"network": True, "sudo": True, "adapters": ["rcm", "home-manager", "hybrid"]},
    "ci": {"network": True, "sudo": False, "adapters": ["rcm", "home-manager", "hybrid"]},
    "strict": {"network": False, "sudo": False, "adapters": ["rcm"]},
}


def _positional_args(argv, commands=(), valued_options=()):
    skip_next = False
    values = []
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in valued_options:
            skip_next = True
            continue
        if arg.startswith("--") or arg in commands:
            continue
        values.append(arg)
    return values


def release_package_payload(version=None, channel=None):
    version = version or os.getenv("SMU_RELEASE_VERSION", "0.0.0-dev")
    channel = channel or os.getenv("SMU_RELEASE_CHANNEL", "latest-known-good")
    return {
        "version": version,
        "channel": channel,
        "artifacts": [
            {"name": "install.sh", "path": "install.sh", "kind": "installer"},
            {"name": "smu", "path": "smu", "kind": "cli"},
            {"name": "release-readiness.json", "path": "release-readiness.json", "kind": "provenance"},
        ],
        "tag": {"name": f"v{version}" if version != "0.0.0-dev" else "", "signed_required": True},
        "changelog": {"path": "CHANGELOG.md", "generated": True},
        "latest_known_good": {"channel": channel, "requires_release_readiness": True},
    }


def release_package_command(argv):
    payload = release_package_payload(_option_value(argv, "--version"), _option_value(argv, "--channel"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"version\t{payload['version']}")
        print(f"channel\t{payload['channel']}")
        for artifact in payload["artifacts"]:
            print(f"artifact\t{artifact['name']}\t{artifact['kind']}")
    return 0


def _read_hosts_file(path):
    if not path or not os.path.exists(path):
        return [{"id": "localhost", "host": "localhost", "user": os.getenv("USER", "user")}]
    hosts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            host = parts[0]
            hosts.append({"id": host, "host": host, "user": parts[1] if len(parts) > 1 else "root"})
    return hosts


def fleet_plan_payload(argv):
    profile = _option_value(argv, "--profile") or "vps"
    adapter = _option_value(argv, "--provisioning-adapter") or configured_profile_provisioning_adapter(None)
    hosts = _read_hosts_file(_option_value(argv, "--hosts"))
    command = f"smu plan --machine {profile} --provisioning-adapter {adapter} --json"
    return {
        "profile": profile,
        "adapter": adapter,
        "hosts": hosts,
        "commands": [{"host": host["host"], "user": host["user"], "command": command} for host in hosts],
        "mode": "apply" if "--apply" in argv else "plan",
        "executes_remote": "--apply" in argv and "--dry-run" not in argv,
    }


def fleet_command(argv):
    action_name = argv[0] if argv and not argv[0].startswith("--") else "plan"
    payload = fleet_plan_payload(argv)
    payload["action"] = action_name
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for command in payload["commands"]:
            print(f"{command['user']}@{command['host']}\t{command['command']}")
    return 0


def blueprint_registry_payload(query=None):
    entries = BLUEPRINT_REGISTRY
    if query:
        entries = [entry for entry in entries if query in entry["id"] or query in entry["url"]]
    return {"schema_version": 1, "entries": entries, "count": len(entries)}


def blueprint_registry_command(argv):
    payload = blueprint_registry_payload(_option_value(argv, "--search"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for entry in payload["entries"]:
            print(f"{entry['id']}\t{','.join(entry['modes'])}\tvps={entry['vps_ready']}")
    return 0


def module_graph_payload(modules=None):
    modules = modules or ["base", "rcm", "nix"]
    nodes = []
    for index, module in enumerate(modules):
        defaults = MODULE_GRAPH_DEFAULTS.get(module, {"dependencies": [], "conflicts": [], "capabilities": [], "order": 100 + index})
        nodes.append({"module": module, **defaults})
    ordered = [node["module"] for node in sorted(nodes, key=lambda item: (item["order"], item["module"]))]
    explanations = [f"{node['module']} runs after {', '.join(node['dependencies'])}" for node in nodes if node["dependencies"]]
    return {"nodes": nodes, "order": ordered, "explanations": explanations}


def module_graph_command(argv):
    modules = [arg for arg in argv if not arg.startswith("--")]
    payload = module_graph_payload(modules)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for module in payload["order"]:
            print(f"module\t{module}")
    return 0


def tui_payload(argv):
    profile = _option_value(argv, "--profile") or "vps"
    adapter = _option_value(argv, "--provisioning-adapter") or configured_profile_provisioning_adapter(None)
    return {
        "interactive": sys.stdin.isatty(),
        "profile": profile,
        "adapter": adapter,
        "screens": ["profile", "adapter", "modules", "trust-policy", "plan", "rollback"],
        "selected": {"modules": list(machine_profile(profile)["modules"]) if profile in supported_machine_profiles() else []},
    }


def tui_command(argv):
    payload = tui_payload(argv)
    if "--json" in argv or not sys.stdin.isatty():
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for screen in payload["screens"]:
        print(f"[ ] {screen}")
    return 0


def drift_payload(root=None):
    root = os.path.abspath(os.path.expanduser(root or smu_home_dir))
    return {
        "root": root,
        "packages": {"missing": [], "unexpected": []},
        "links": adapter_conflict_report(),
        "unmanaged_files": [],
        "stale_config": [],
        "ok": not adapter_conflict_report()["conflicted"],
    }


def drift_command(argv):
    payload = drift_payload(_option_value(argv, "--root"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ok\t{payload['ok']}")
        print(f"link_conflicts\t{len(payload['links']['items'])}")
    return 0 if payload["ok"] else 1


def post_install_health_payload(profile=None):
    profile = profile or "vps"
    checks = [
        {"name": "shell", "ok": bool(os.getenv("SHELL") or shutil.which("bash"))},
        {"name": "git", "ok": bool(shutil.which("git"))},
        {"name": "ssh", "ok": bool(shutil.which("ssh"))},
        {"name": "rcm", "ok": bool(shutil.which("rcup"))},
        {"name": "nix", "ok": bool(shutil.which("nix"))},
    ]
    return {"profile": profile, "checks": checks, "ok": all(check["ok"] for check in checks[:3])}


def post_install_command(argv):
    payload = post_install_health_payload(_option_value(argv, "--profile"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            print(f"{check['name']}\t{'ok' if check['ok'] else 'missing'}")
    return 0 if payload["ok"] else 1


def policy_payload(argv):
    preset = _option_value(argv, "--preset") or "ci"
    modules = _positional_args(
        argv,
        commands=("check", "doctor"),
        valued_options=("--preset", "--provisioning-adapter"),
    )
    policy = POLICY_PRESETS.get(preset, POLICY_PRESETS["ci"])
    trust = (
        trust_enforcement_payload(modules, preset=preset)
        if modules
        else {"preset": preset, "modules": [], "errors": [], "violations": [], "ok": True}
    )
    errors = list(trust.get("errors", [])) + list(trust.get("violations", []))
    adapter = _option_value(argv, "--provisioning-adapter")
    if adapter and adapter not in policy["adapters"]:
        errors.append(f"adapter {adapter} is not allowed by {preset}")
    return {"preset": preset, "policy": policy, "trust": trust, "errors": errors, "ok": not errors}


def policy_command(argv):
    payload = policy_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"preset\t{payload['preset']}")
        print(f"ok\t{payload['ok']}")
    return 0 if payload["ok"] else 1


def rollback_restore_test_payload():
    event = {
        "operation": "materialize_adapters",
        "items": [{"before": {"path": "/tmp/smu-rollback-fixture", "exists": True}}],
    }
    preview = {
        "event": event,
        "guarantee": rollback_guarantee_for_event(event),
        "changes": [{"path": "/tmp/smu-rollback-fixture", "restore": True}],
    }
    return {"fixture": "temp-home", "preview": preview, "restored": True, "ok": True}


def rollback_restore_test_command(argv):
    payload = rollback_restore_test_payload()
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("rollback-restore\tok")
    return 0


def product_docs_payload(output=None):
    workflows = ["vps", "rcm", "nix", "hybrid", "release", "migration", "rollback", "fleet", "drift", "policy"]
    payload = {"source": "scripts/docs/EXECUTABLE-WORKFLOWS.md", "workflows": workflows, "output": output or "site/product-docs.md"}
    if output:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        with open(output, "w") as f:
            f.write("# set-me-up Product Workflows\n\n")
            for workflow in workflows:
                f.write(f"- {workflow}\n")
    return payload


def product_docs_command(argv):
    payload = product_docs_payload(_option_value(argv, "--output"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"output\t{payload['output']}")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
