# AGENTS.md

## Project Snapshot

This repository owns the `smu` installer command for `set-me-up`. It manages
bootstrap behavior, module discovery/provisioning, uninstall/status flows,
theme and prompt profile selection, catalog packs/registries, and the installer
test/validation harness.

The aggregate `set-me-up` checkout may show sibling repositories next to this
one. Do not edit those from this repo unless the user explicitly asks for
cross-repo work.

## Where To Add Things

- CLI routing and flags: `smu_parts/cli.py`.
- Shared constants, config paths, profile parsing, and TOML helpers:
  `smu_parts/core.py`.
- Theme, prompt, preset, and catalog command handlers:
  `smu_parts/profile_commands.py`.
- Adapter discovery/materialization: `smu_parts/adapters.py`.
- Catalog pack install/publish/migrate behavior: `smu_parts/catalog_packs.py`.
- Catalog registry add/list/search/lock/status behavior:
  `smu_parts/catalog_registry.py`.
- Doctor commands and module execution: `smu_parts/doctors_and_system.py`.
- Module discovery/listing: `smu_parts/module_discovery.py`.
- Module status/uninstall/provision batch behavior:
  `smu_parts/module_lifecycle.py`.
- Install state ledger, JSON status, diff plans, and rollback:
  `smu_parts/state.py`.
- Shared manifest parsing and contract rules: `scripts/smu_contract.py`.
- Built-in prompt profiles: `prompt-profiles/*.toml`.
- Built-in presets: `presets/*.toml`.
- User-facing docs: `README.md` and `docs/catalogs-and-adapters.md`.
- CI and local validation entrypoint: `.github/workflows/tests.yml` and
  `scripts/validate.sh`.

Keep `smu.py` as a thin compatibility shim. New behavior belongs in
`smu_parts/` or `scripts/`.

## Design Rules

- Preserve both `python smu.py ...` and `import smu` compatibility.
- Keep every tracked source file at or below the configured LOC budget.
- Prefer manifest-driven behavior over hard-coded theme, prompt, or catalog
  lists.
- Keep install and rollback paths conservative: never silently overwrite,
  delete, or reinstall state that cannot be described or validated.
- Keep dry-run and JSON output stable enough for agents and scripts.
- Use explicit errors for invalid manifests, unknown IDs, unsafe paths, and
  unsupported schema versions.

## Validation

Run the repo-native validator before finishing changes:

```bash
scripts/validate.sh --all
```

For narrower loops:

```bash
PYTHON=python3.14 scripts/validate.sh --python
scripts/validate.sh --shell
scripts/validate.sh --markdown
```

The Python validator runs LOC and flat-directory budgets, py_compile, unittest,
pytest when available, prompt/preset contracts, template checks, and CLI smoke.
The shell validator runs ShellCheck against installer shell entrypoints.

## Git

- Use conventional commits.
- Commit with author `Nicholas Adamou <10106289+nicholasadamou@users.noreply.github.com>`.
- Do not add `Co-Authored-By` or AI attribution footers.
- Never force-push `main`.
