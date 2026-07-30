# Upgrade notes

After pulling a newer set-me-up installer on an existing machine, run:

```bash
smu update baseline
smu doctor --json
smu update preflight --json
```

Then optionally configure unattended client updates:

```bash
smu update policy --schedule daily --validate --auto-apply
smu update policy --min-interval-seconds 3600 --backoff-seconds 900
smu update schedule install --json
```

If adapter targets already exist, preview before writing:

```bash
smu bootstrap --dry-run --json
smu adapter materialize --dry-run
```

Use `--force` only after reviewing conflicts. Runtime commands that mutate
set-me-up state now use a local process lock so concurrent shells or agents do
not write the same state files at the same time.
