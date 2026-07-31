# Operability

Discover newer commands without opening docs:

```bash
smu help
smu help bootstrap
smu help update preflight
```

Generate shell completions:

```bash
smu completion bash
smu completion zsh
smu completion fish
```

Write or inspect JSON contract examples for automation:

```bash
smu contract list
smu contract show doctor
smu contract write
```

Contracts are written to `docs/json-contracts/` and cover bootstrap planning,
catalog trust, doctor health, status, update preflight, provisioning preflight,
adapter capabilities, and blueprint CI readiness payloads.

Publish an update manifest for pinned rollouts:

```bash
smu update manifest --json
smu update manifest --output manifest.json
```

Prune stale runtime files:

```bash
smu state prune --dry-run --json
smu state prune
```

State pruning removes generated schedule files and catalog cache entries. It
does not delete the update lock, update history, profile, or adapter manifest.
