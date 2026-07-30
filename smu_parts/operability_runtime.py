from .product_runtime import *


@contextlib.contextmanager
def runtime_lock(operation):
    os.makedirs(config_dir, exist_ok=True)
    with open(runtime_lock_path, "w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            die(f"Another smu operation is running: {operation}")
        lock_file.write(f"{operation}\t{_utc_timestamp()}\n")
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def locked_call(operation, callback, *args, **kwargs):
    with runtime_lock(operation):
        return callback(*args, **kwargs)


HELP_TOPICS = {
    "bootstrap": [
        "smu bootstrap [--dry-run] [--json] [--theme id] [--prompt id] [--preset id] [--force]",
        "Plan or apply first-run profile, adapter, and update-baseline setup.",
    ],
    "catalog trust": [
        "smu catalog trust [status|publisher <id>|registry <name>] [--json]",
        "Manage local trust metadata for catalog publishers and registries.",
    ],
    "update preflight": [
        "smu update preflight --json",
        "Run read-only update checks for policy, channel, manifest, drift, and rate limits.",
    ],
    "update doctor": [
        "smu update doctor [--json]",
        "Report blueprint and installer update readiness, dirty state, and sync status.",
    ],
    "update schedule": [
        "smu update schedule [install|remove|status] [--json]",
        "Write scheduler payloads plus launchd/systemd user-service files.",
    ],
    "rollback": [
        "smu rollback --json",
        "Preview the latest rollback event as JSON before applying rollback.",
    ],
    "contracts": [
        "smu contract [list|show <name>|write]",
        "Print or write stable JSON example payloads for agent and fleet integrations.",
    ],
    "completion": [
        "smu completion [bash|zsh|fish]",
        "Generate shell completions for common commands and profile IDs.",
    ],
    "provisioning-adapter": [
        "smu provisioning-adapter [list|doctor|modules|coverage|validate|profile|audit|bootstrap|migrate|scaffold|plan|apply] [--json]",
        "Show, validate, scaffold, plan, or run the selected provisioning engine.",
    ],
    "nix": [
        "smu nix [doctor|audit|coverage|bootstrap|plan|apply|migrate] [--json]",
        "Short aliases for Home Manager-oriented provisioning adapter workflows.",
    ],
    "state prune": [
        "smu state prune [--dry-run] [--json]",
        "Remove stale runtime cache and generated scheduler files.",
    ],
    "manifest": [
        "smu update manifest [--json] [--output path]",
        "Generate a pinned update manifest for release and fleet rollout publishing.",
    ],
}


def print_help_topic(topic=None):
    if not topic:
        for key in sorted(HELP_TOPICS):
            print(f"{key}\t{HELP_TOPICS[key][0]}")
        return 0
    key = " ".join(topic) if isinstance(topic, list) else topic
    if key not in HELP_TOPICS:
        die(f"Unknown help topic: {key}")
    print(HELP_TOPICS[key][0])
    print(HELP_TOPICS[key][1])
    return 0


def json_contracts():
    return {
        "bootstrap-plan": bootstrap_plan(["--theme", DEFAULT_THEME, "--prompt", DEFAULT_PROMPT]),
        "catalog-trust": {"path": catalog_trust_path, "trust": {"trusted_publishers": {}, "trusted_registries": {}}},
        "doctor": {
            "preset": {"id": DEFAULT_PRESET, "valid": True},
            "theme": {"id": DEFAULT_THEME, "valid": True},
            "prompt": {"id": DEFAULT_PROMPT, "valid": True},
            "catalogs": {"path": catalogs_path, "errors": [], "trust": read_catalog_trust()},
            "adapters": {"conflicted": False, "items": []},
            "updates": {"preflight": "passed", "manifest": {"status": "disabled"}},
        },
        "status": status_report(),
        "update-doctor": repository_update_doctor(),
        "update-preflight": client_update_preflight(),
    }


def contract_command(argv):
    command = argv[0] if argv else "list"
    contracts = json_contracts()
    if command == "list":
        for name in sorted(contracts):
            print(name)
        return 0
    if command == "show":
        if len(argv) < 2 or argv[1] not in contracts:
            die("Usage: smu contract show <name>")
        print(json.dumps(contracts[argv[1]], indent=2, sort_keys=True))
        return 0
    if command == "write":
        os.makedirs(contracts_path, exist_ok=True)
        for name, payload in contracts.items():
            write_json_file(os.path.join(contracts_path, f"{name}.json"), payload)
        print(f"wrote\t{len(contracts)}\t{contracts_path}")
        return 0
    die("Usage: smu contract [list|show <name>|write]")


def update_manifest_payload():
    repos = client_update_repository_status()
    return {
        "schema_version": 1,
        "created_at": _utc_timestamp(),
        "client": client_identity(),
        "theme": current_theme(),
        "prompt": current_prompt(),
        "preset": current_preset(),
        "repositories": [
            {"name": repo["name"], "path": repo["path"], "head": repo["head"], "signature": repo["signature"]}
            for repo in repos
        ],
    }


def update_manifest_command(argv, json_output=False):
    payload = update_manifest_payload()
    output = _option_value(argv, "--output")
    if output:
        write_json_file(os.path.abspath(os.path.expanduser(output)), payload)
    if json_output or not output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"wrote\t{output}")
    return 0


def state_prune_plan():
    paths = [update_schedule_path, update_launchd_path]
    if os.path.isdir(update_systemd_dir):
        paths.extend(os.path.join(update_systemd_dir, name) for name in os.listdir(update_systemd_dir))
    if os.path.isdir(catalog_cache_path):
        paths.extend(os.path.join(catalog_cache_path, name) for name in os.listdir(catalog_cache_path))
    return [{"path": path, "exists": os.path.exists(path), "kind": "dir" if os.path.isdir(path) else "file"} for path in paths]


def state_prune(argv):
    dry_run = "--dry-run" in argv
    json_output = "--json" in argv
    plan = state_prune_plan()
    if not dry_run:
        for item in plan:
            if not item["exists"]:
                continue
            shutil.rmtree(item["path"]) if item["kind"] == "dir" else os.unlink(item["path"])
    payload = {"dry_run": dry_run, "items": plan}
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in plan:
            print(f"{'would-prune' if dry_run else 'pruned'}\t{item['path']}")
    return 0


def completion_words():
    return sorted(set([
        "adapter", "bootstrap", "catalog", "completion", "contract", "diff", "doctor",
        "help", "init", "profile", "prompt", "preset", "rollback", "state", "status",
        "theme", "update", *supported_themes(), *supported_prompts(), *supported_presets(),
    ]))


def completion_command(argv):
    shell = argv[0] if argv else "bash"
    words = " ".join(completion_words())
    if shell == "fish":
        print(f"complete -c smu -f -a '{words}'")
    elif shell == "zsh":
        print(f"#compdef smu\n_arguments '*: :(({words}))'")
    elif shell == "bash":
        print(f"complete -W '{words}' smu")
    else:
        die("Usage: smu completion [bash|zsh|fish]")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
