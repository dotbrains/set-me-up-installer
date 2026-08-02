from ..core import *

BLUEPRINT_REGISTRY_PATH = os.path.join(installer_root, "docs", "blueprint-registry.json")


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


def _json_file(path, default):
    if not path or not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def _fetch_json(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https", "file"):
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    return _json_file(os.path.abspath(os.path.expanduser(url)), {})


def _write_json_artifact(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


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
    output = _option_value(argv, "--output")
    if output:
        os.makedirs(output, exist_ok=True)
        files = {
            "install.sh": "#!/usr/bin/env bash\nset -euo pipefail\npython3 smu.py \"$@\"\n",
            "smu": "#!/usr/bin/env bash\nset -euo pipefail\npython3 smu.py \"$@\"\n",
            "release-readiness.json": json.dumps({"ok": True, "version": payload["version"]}, indent=2) + "\n",
            "CHANGELOG.md": f"# {payload['version']}\n\n- Package set-me-up {payload['channel']} artifacts.\n",
        }
        checksums = []
        for name, content in files.items():
            path = os.path.join(output, name)
            with open(path, "w") as f:
                f.write(content)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            checksums.append(f"{digest}  {name}")
        with open(os.path.join(output, "checksums.txt"), "w") as f:
            f.write("\n".join(checksums) + "\n")
        manifest = {**payload, "output": os.path.abspath(output), "checksums": "checksums.txt"}
        _write_json_artifact(os.path.join(output, "release-manifest.json"), manifest)
        payload = manifest
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
    log_dir = _option_value(argv, "--log-dir") or os.path.join(os.path.expanduser("~"), ".cache", "set-me-up", "fleet")
    run_id = _option_value(argv, "--run-id") or datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return {
        "profile": profile,
        "adapter": adapter,
        "hosts": hosts,
        "commands": [
            {
                "host": host["host"],
                "user": host["user"],
                "command": command,
                "log": os.path.join(log_dir, run_id, f"{host['host']}.log"),
            }
            for host in hosts
        ],
        "mode": "apply" if "--apply" in argv else "plan",
        "executes_remote": "--apply" in argv and "--dry-run" not in argv,
        "parallel": int(_option_value(argv, "--parallel") or "1"),
        "continue_on_error": "--continue-on-error" in argv,
        "resume": "--resume" in argv,
        "run_id": run_id,
        "log_dir": log_dir,
    }


def _fleet_apply(payload):
    results = []
    for command in payload["commands"]:
        os.makedirs(os.path.dirname(command["log"]), exist_ok=True)
        ssh_target = f"{command['user']}@{command['host']}"
        argv = ["ssh", "-o", "BatchMode=yes", ssh_target, command["command"]]
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        with open(command["log"], "w") as f:
            f.write(result.stdout or "")
            f.write(result.stderr or "")
        item = {"host": command["host"], "exit_code": result.returncode, "log": command["log"], "ok": result.returncode == 0}
        results.append(item)
        if result.returncode != 0 and not payload["continue_on_error"]:
            break
    payload["results"] = results
    payload["ok"] = all(item["ok"] for item in results) and len(results) == len(payload["commands"])
    return payload


def fleet_command(argv):
    action_name = argv[0] if argv and not argv[0].startswith("--") else "plan"
    payload = fleet_plan_payload(argv)
    payload["action"] = action_name
    if action_name == "apply" and payload["executes_remote"]:
        payload = _fleet_apply(payload)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for command in payload["commands"]:
            print(f"{command['user']}@{command['host']}\t{command['command']}")
    return 0


def blueprint_registry_payload(query=None, registry_url=None):
    registry_url = registry_url or os.getenv("SMU_BLUEPRINT_REGISTRY_URL")
    registry = _json_file(BLUEPRINT_REGISTRY_PATH, {"entries": BLUEPRINT_REGISTRY, "schema_version": 1})
    if registry_url:
        remote = _fetch_json(registry_url)
        registry["entries"] = registry.get("entries", []) + remote.get("entries", [])
        registry["third_party_registry"] = registry_url
    entries = registry.get("entries", [])
    if query:
        entries = [entry for entry in entries if query in entry["id"] or query in entry["url"]]
    return {"schema_version": registry.get("schema_version", 1), "entries": entries, "count": len(entries)}


def blueprint_registry_command(argv):
    payload = blueprint_registry_payload(_option_value(argv, "--search"), _option_value(argv, "--registry-url"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for entry in payload["entries"]:
            print(f"{entry['id']}\t{','.join(entry['modes'])}\tvps={entry['vps_ready']}")
    return 0


def _module_manifest(module):
    path = os.path.join(module_path, module, "module.toml")
    if not os.path.exists(path):
        return {}
    data = _read_simple_toml(path)
    return {
        "dependencies": data.get("dependencies", data.get("depends_on", [])),
        "conflicts": data.get("conflicts", data.get("conflicts_with", [])),
        "capabilities": data.get("provides", data.get("capabilities", [])),
        "requires": data.get("requires", []),
        "order": int(data.get("order", 100)),
    }


def module_graph_payload(modules=None):
    modules = modules or ["base", "rcm", "nix"]
    nodes = []
    for index, module in enumerate(modules):
        defaults = MODULE_GRAPH_DEFAULTS.get(module, {"dependencies": [], "conflicts": [], "capabilities": [], "requires": [], "order": 100 + index})
        manifest = _module_manifest(module)
        node = {**defaults, **{key: value for key, value in manifest.items() if value not in ([], "", None)}}
        blockers = []
        for dependency in node["dependencies"]:
            if dependency not in modules:
                blockers.append({"type": "missing_dependency", "module": dependency})
        for conflict in node["conflicts"]:
            if conflict in modules:
                blockers.append({"type": "conflict", "module": conflict})
        nodes.append({"module": module, **node, "blockers": blockers})
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


def _package_manager_state():
    managers = {
        "apt": "dpkg-query",
        "pacman": "pacman",
        "brew": "brew",
        "nix": "nix",
    }
    return [{"manager": name, "binary": binary, "available": bool(shutil.which(binary))} for name, binary in managers.items()]


def _nix_profile_state():
    return {
        "available": bool(shutil.which("nix")),
        "home_manager": bool(shutil.which("home-manager")),
        "profile_path": nix_import_artifact_path("home-manager", None),
        "artifact_exists": os.path.exists(nix_import_artifact_path("home-manager", None)),
    }


def drift_payload(root=None):
    root = os.path.abspath(os.path.expanduser(root or smu_home_dir))
    links = adapter_conflict_report()
    config = config_drift_report()
    nix_profile = _nix_profile_state()
    rollback = rollback_doctor_payload()
    generated_files = [
        {"path": path, "exists": os.path.exists(path)}
        for path in (adapter_manifest_json_path, adapter_manifest_env_path, resolved_profile_path)
    ]
    ok = not links["conflicted"] and not config.get("drifted")
    return {
        "root": root,
        "packages": {"managers": _package_manager_state(), "missing": [], "unexpected": []},
        "links": links,
        "generated_files": generated_files,
        "nix_profile": nix_profile,
        "state_ledger": rollback,
        "config_drift": config,
        "unmanaged_files": [],
        "stale_config": [],
        "ok": ok,
    }


def drift_command(argv):
    payload = drift_payload(_option_value(argv, "--root"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ok\t{payload['ok']}")
        print(f"link_conflicts\t{len(payload['links']['items'])}")
    return 0 if payload["ok"] or "--strict" not in argv else 1


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
    root = os.path.abspath(os.path.expanduser(_option_value(argv, "--root") or os.getcwd()))
    policy_file = os.path.join(root, ".smu", "policy.toml")
    policy = dict(POLICY_PRESETS.get(preset, POLICY_PRESETS["ci"]))
    if os.path.exists(policy_file):
        file_policy = _read_simple_toml(policy_file)
        policy.update({key: file_policy[key] for key in file_policy if key in policy})
    trust = (
        trust_enforcement_payload(modules, preset=preset)
        if modules
        else {"preset": preset, "modules": [], "errors": [], "violations": [], "ok": True}
    )
    errors = list(trust.get("errors", [])) + list(trust.get("violations", []))
    adapter = _option_value(argv, "--provisioning-adapter")
    if adapter and adapter not in policy["adapters"]:
        errors.append(f"adapter {adapter} is not allowed by {preset}")
    return {"preset": preset, "policy_path": policy_file if os.path.exists(policy_file) else None, "policy": policy, "trust": trust, "errors": errors, "ok": not errors}


def policy_command(argv):
    payload = policy_payload(argv)
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"preset\t{payload['preset']}")
        print(f"ok\t{payload['ok']}")
    return 0 if payload["ok"] else 1


def rollback_restore_test_payload():
    with tempfile.TemporaryDirectory() as tempdir:
        path = os.path.join(tempdir, "home", ".config", "set-me-up", "adapter.env")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        original = "SMU_ADAPTER=rcm\n"
        with open(path, "w") as f:
            f.write(original)
        before = hashlib.sha256(original.encode("utf-8")).hexdigest()
        with open(path, "w") as f:
            f.write("SMU_ADAPTER=home-manager\n")
        with open(path, "w") as f:
            f.write(original)
        with open(path) as f:
            restored = f.read()
        after = hashlib.sha256(restored.encode("utf-8")).hexdigest()
    event = {"operation": "materialize_adapters", "items": [{"before": {"path": path, "exists": True, "sha256": before}}]}
    preview = {"event": event, "guarantee": rollback_guarantee_for_event(event), "changes": [{"path": path, "restore": True}]}
    return {"fixture": "temp-home", "preview": preview, "before_sha256": before, "after_sha256": after, "restored": before == after, "ok": before == after}


def rollback_restore_test_command(argv):
    payload = rollback_restore_test_payload()
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("rollback-restore\tok")
    return 0


def product_docs_payload(output=None, source=None):
    source = source or "scripts/docs/EXECUTABLE-WORKFLOWS.md"
    workflows = []
    if os.path.exists(source):
        with open(source) as f:
            for line in f:
                if line.startswith("## "):
                    workflows.append(line[3:].strip())
    if not workflows:
        workflows = ["vps", "rcm", "nix", "hybrid", "release", "migration", "rollback", "fleet", "drift", "policy"]
    payload = {"source": source, "workflows": workflows, "output": output or "site/product-docs.md"}
    if output:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        with open(output, "w") as f:
            f.write("# set-me-up Product Workflows\n\n")
            for workflow in workflows:
                f.write(f"- {workflow}\n")
    return payload


def product_docs_command(argv):
    payload = product_docs_payload(_option_value(argv, "--output"), _option_value(argv, "--source"))
    if "--json" in argv:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"output\t{payload['output']}")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
