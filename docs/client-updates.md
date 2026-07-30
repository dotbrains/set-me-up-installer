# Client update operations

Use `smu update` after upstream set-me-up repos change and the local machine
needs newer config, theme, prompt, and adapter files.

```bash
smu update --check
smu update --check --json
smu update --report --json
smu update preflight --json
smu update baseline
smu update policy --set-ref stable --require-signed --validate --json
smu update policy --channel beta --set-ref none
smu update policy --report-url https://updates.example.com/smu
smu update policy --manifest-url https://updates.example.com/manifest.json
smu update policy --min-interval-seconds 3600 --backoff-seconds 900
smu update doctor --json
smu update schedule install --json
smu update schedule status
smu update --yes --json --validate
smu update --ref stable --require-signed --validate
smu update --self --validate
smu update --rollback
smu update --rollback --repos
```

State files:

- `~/.config/set-me-up/update.lock`
- `~/.config/set-me-up/update-policy.json`
- `~/.config/set-me-up/update-history.json`
- `~/.config/set-me-up/state/ledger.json`

The lock records active preset, theme, prompt, requested ref, before/after
repository SHAs, generated config fingerprints, validation exit code, and update
actions. The history file stores recent update outcomes for audit and retry
decisions. The policy file stores durable defaults for ref, signed commits,
validation, scheduled update intent, auto-apply intent, optional HTTPS report
delivery, retry backoff, rate-limit interval, and history retention.
Channels map friendly names like `stable` or `beta` to refs so clients can move
between rollout tracks without learning branch or tag names.

`smu update --check --json` and `smu update --report --json` include:

- `policy` and `update_policy_path`
- `policy_errors`, `rate_limit`, and recent `history`
- `last_update` and `update_lock_path`
- `repositories`
- `updates_available`
- `config_drift`
- `theme`, `prompt`, and `preset`

Reports also include a stable anonymous client ID. Hostname reporting is opt-in:
set `SMU_REPORT_HOSTNAME=1` before running report/update commands.

`smu update preflight --json` runs the read-only safety checks used by schedulers:
policy schema, channel ref resolution, rate-limit readiness, repository state,
config drift, client identity, and update manifest verification.

Use `smu update baseline` after upgrading an existing machine to a version that
supports update locks. It records the current generated config fingerprints
without pulling or rewriting config, clearing first-run drift.

Use `smu update doctor --json` before enabling unattended updates. It checks
lockfile, policy schema, drift, schedule, rate-limit readiness, report hook,
and signature health.

When `report_url` is configured, `smu update --report --json` and completed
updates POST their JSON payload to that endpoint. Report delivery failures are
recorded in the payload and history but do not fail the local update.

When `manifest_url` is configured, preflight downloads the update manifest. If
`manifest_sha256` is also configured, the manifest must match that pinned digest
before the preflight passes.

Scheduled jobs should run check/report first, then apply with
`smu update --yes --json --validate` only when policy allows it.
`smu update schedule install` writes the scheduler payload to
`~/.config/set-me-up/update-schedule.json`; platform-specific launchd/systemd
wrappers can consume that file without duplicating policy parsing.

`--require-signed` verifies checked-out `HEAD` in each managed repo with local
Git trust settings before generated config is rewritten. Unsigned or untrusted
commits stop the update and write the failed attempt to the update lock.
`smu update --rollback --repos` checks out the prior repository SHAs recorded in
the last successful update lock.
