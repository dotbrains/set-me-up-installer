# Client update operations

Use `smu update` after upstream set-me-up repos change and the local machine
needs newer config, theme, prompt, and adapter files.

```bash
smu update --check
smu update --check --json
smu update --report --json
smu update baseline
smu update policy --set-ref stable --require-signed --validate --json
smu update doctor --json
smu update --yes --json --validate
smu update --ref stable --require-signed --validate
smu update --self --validate
smu update --rollback
```

State files:

- `~/.config/set-me-up/update.lock`
- `~/.config/set-me-up/update-policy.json`
- `~/.config/set-me-up/state/ledger.json`

The lock records active preset, theme, prompt, requested ref, before/after
repository SHAs, generated config fingerprints, validation exit code, and update
actions. The policy file stores durable defaults for ref, signed commits,
validation, scheduled update intent, and auto-apply intent.

`smu update --check --json` and `smu update --report --json` include:

- `policy` and `update_policy_path`
- `last_update` and `update_lock_path`
- `repositories`
- `updates_available`
- `config_drift`
- `theme`, `prompt`, and `preset`

Use `smu update baseline` after upgrading an existing machine to a version that
supports update locks. It records the current generated config fingerprints
without pulling or rewriting config, clearing first-run drift.

Use `smu update doctor --json` before enabling unattended updates. It checks
lockfile, policy, drift, schedule, and signature health.

Scheduled jobs should run check/report first, then apply with
`smu update --yes --json --validate` only when policy allows it.

`--require-signed` verifies checked-out `HEAD` in each managed repo with local
Git trust settings before generated config is rewritten. Unsigned or untrusted
commits stop the update and write the failed attempt to the update lock.
