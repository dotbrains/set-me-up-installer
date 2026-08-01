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
        "smu rollback [doctor|--json|--dry-run|--to event-id]",
        "Preview, inspect guarantees for, or apply rollback events.",
    ],
    "plan": [
        "smu plan [--machine profile] [--provisioning-adapter adapter] [--strict] [--json]",
        "Universal dry-run for blueprint, modules, dotfiles, secrets, trust, and rollback.",
    ],
    "machine-profile": [
        "smu machine-profile [list|show <profile>] [--json]",
        "Show built-in laptop, workstation, VPS, CI, minimal, and agent-host defaults.",
    ],
    "secrets": [
        "smu secrets doctor [--root path] [--json]",
        "Scan a blueprint or module tree for secret-like files and token-like values.",
    ],
    "trust": [
        "smu trust doctor [module ...] [--json]",
        "Inspect module trust, network, sudo, write-target, and rollback metadata.",
    ],
    "trust enforce": [
        "smu trust enforce [module ...] [--profile id] [--allow-sudo] [--allow-network] [--json]",
        "Fail when selected modules exceed the current trust policy.",
    ],
    "conformance": [
        "smu conformance [--repo path] [--json|--markdown] [--output path]",
        "Generate downstream blueprint conformance JSON or Markdown badge output.",
    ],
    "support": [
        "smu support bundle [--redact] [--output path]",
        "Emit telemetry-free diagnostics with secret-like fields redacted.",
    ],
    "release-notes": [
        "smu release-notes --from release-readiness.json [--output path]",
        "Render Markdown release notes from release-readiness provenance.",
    ],
    "migration-pr": [
        "smu migration-pr --repo path [--mode hybrid] [--output path]",
        "Generate a branch, command, and pull-request payload for blueprint adoption.",
    ],
    "contracts": [
        "smu contract [list|show <name>|schema <name>|write|validate <name> [--path path|-] [--json]]",
        "Print, write, or validate stable JSON payloads for agent and fleet integrations.",
    ],
    "vps": [
        "smu vps [init|doctor] [--target ubuntu|debian|arch|nixos] [--mode rcm|nix|hybrid] [--repo path] [--json]",
        "Plan first-run VPS commands or validate a dotfiles repo for headless setup.",
    ],
    "completion": [
        "smu completion [bash|zsh|fish]",
        "Generate shell completions for common commands and profile IDs.",
    ],
    "provisioning-adapter": [
        "smu provisioning-adapter [list|doctor|modules|coverage|dashboard|issue|parity|docs|validate|profile|audit|preflight|bootstrap|migrate|scaffold|plan|apply] [--json]",
        "Show, validate, scaffold, plan, or run the selected provisioning engine.",
    ],
    "nix": [
        "smu nix [doctor|init|audit|coverage|bootstrap|plan|apply|switch|migrate|parity] [--json]",
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
        "plan": universal_plan_payload(["--machine", "vps"]),
        "secrets-doctor": {"root": "/path/to/blueprint", "findings": [], "ok": True},
        "trust-doctor": {
            "modules": [
                {
                    "module": "base",
                    "state": "ok",
                    "trust": "first-party",
                    "network": True,
                    "requires_sudo": False,
                    "writes": [],
                    "rollback": "partial",
                }
            ],
            "warnings": [],
            "errors": [],
        },
        "support-bundle": {
            "generated_at": "2026-08-01T00:00:00Z",
            "versions": {"python": "3.14.0", "platform": "linux", "installer": "abc123", "blueprint": "def456"},
            "health": {"ok": True},
            "plan": {"machine_profiles": [], "coverage": {"nix_ready_percent": 100}},
            "secrets": {"root": "/path/to/blueprint", "findings": [], "ok": True},
            "status": {"modules": [], "adapters": [], "ledger": {}},
        },
        "conformance": {
            "root": "/path/to/blueprint",
            "checks": {
                "install_surface_ready": True,
                "rcm_ready": True,
                "nix_ready": True,
                "hybrid_ready": True,
                "vps_ready": True,
                "rollback_ready": True,
                "ci_validated": True,
            },
            "ready": True,
        },
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
        "provisioning-preflight": {
            "adapter": "home-manager",
            "action": "switch",
            "profile": "default",
            "strict": False,
            "modules": ["example"],
            "capability": {
                "mode": "nix",
                "engine": "home-manager",
                "scope": "user",
                "requires_nix": True,
                "supports_fallback": False,
            },
            "host_supported": True,
            "can_apply": True,
            "preflight": "passed",
            "plan": {
                "kind": "nix",
                "modules": [{"module": "example", "path": "home-manager.nix"}],
                "missing": [],
                "artifacts": ["~/.config/set-me-up/adapters/home-manager/default.nix"],
                "commands": [["home-manager", "switch", "-f", "~/.config/set-me-up/adapters/home-manager/default.nix"]],
                "errors": [],
            },
            "errors": [],
        },
        "provisioning-capabilities": provisioning_adapter_capabilities(),
        "blueprint-ci-readiness": {
            "path": "/home/user/set-me-up",
            "valid": True,
            "errors": [],
            "readiness": {
                "preflight": "passed",
                "summary": {
                    "configs": 7,
                    "provider_examples": 6,
                    "workflow_examples": 3,
                    "workflow_preflight": 3,
                    "readiness_docs": 1,
                },
            },
            "checks": [
                {
                    "name": "github-actions-preflight",
                    "path": "examples/github-actions/nix.yml",
                    "ok": True,
                    "message": "preflight",
                }
            ],
        },
        "dotfiles-compatibility": {
            "contract": {"name": "dotfiles-compatibility", "version": 1},
            "path": "/path/to/dotfiles",
            "valid": True,
            "mode": "hybrid",
            "adapter": "hybrid",
            "readiness": {
                "install_shim": True,
                "smu_blueprint": True,
                "platform_scope": True,
                "root_config": True,
                "rcm_ready": False,
                "nix_ready": False,
                "hybrid_ready": True,
                "vps_ready": True,
                "ci_contract": True,
            },
            "checks": [
                {"name": "install-shim", "ok": True},
                {"name": "smu-blueprint", "ok": True},
                {"name": "platform-scope", "ok": True},
                {"name": "root-smu-toml", "ok": True},
                {"name": "ci-contract", "ok": True},
            ],
            "errors": [],
        },
        "status": status_report(),
        "update-doctor": repository_update_doctor(),
        "update-preflight": client_update_preflight(),
    }


def contract_command(argv):
    command = argv[0] if argv else "list"
    if command == "list":
        for name in sorted(json_contracts()):
            print(name)
        return 0
    if command == "show":
        contracts = json_contracts()
        if len(argv) < 2 or argv[1] not in contracts:
            die("Usage: smu contract show <name>")
        print(json.dumps(contracts[argv[1]], indent=2, sort_keys=True))
        return 0
    if command == "schema":
        if len(argv) < 2:
            die("Usage: smu contract schema <name>")
        schema = smu_contract.json_contract_schema(argv[1])
        if not schema:
            die(f"Unknown contract schema: {argv[1]}")
        print(json.dumps(schema, indent=2, sort_keys=True))
        return 0
    if command == "write":
        contracts = json_contracts()
        os.makedirs(contracts_path, exist_ok=True)
        for name, payload in contracts.items():
            write_json_file(os.path.join(contracts_path, f"{name}.json"), payload)
        print(f"wrote\t{len(contracts)}\t{contracts_path}")
        return 0
    if command == "validate":
        if len(argv) < 2:
            die("Usage: smu contract validate <name> [--path path|-] [--json]")
        name = argv[1]
        json_output = "--json" in argv
        path = _option_value(argv, "--path")
        if path == "-":
            payload = json.load(sys.stdin)
            source = "stdin"
        elif path:
            source = os.path.abspath(os.path.expanduser(path))
            with open(source, encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            example_path = os.path.join(contracts_path, f"{name}.example.json")
            if os.path.exists(example_path):
                source = example_path
                with open(example_path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            else:
                contracts = json_contracts()
                payload = contracts.get(name)
                source = "runtime"
        if payload is None:
            die(f"Unknown contract: {name}")
        errors = smu_contract.json_contract_errors(name, payload)
        if json_output:
            print(json.dumps({
                "name": name,
                "source": source,
                "valid": not errors,
                "errors": errors,
            }, indent=2, sort_keys=True))
        elif not errors:
            print(f"valid\t{name}\t{source}")
        else:
            for error in errors:
                print(f"invalid\t{name}\t{error}", file=sys.stderr)
        return 0 if not errors else 1
    die("Usage: smu contract [list|show <name>|schema <name>|write|validate <name> [--path path|-] [--json]]")


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
        "adapter", "bootstrap", "catalog", "completion", "conformance", "contract", "diff",
        "doctor", "help", "init", "machine-profile", "migration-pr", "plan", "profile",
        "prompt", "preset", "release-notes", "rollback", "secrets", "state", "status",
        "support", "theme", "trust", "update",
        *supported_themes(), *supported_prompts(), *supported_presets(),
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
