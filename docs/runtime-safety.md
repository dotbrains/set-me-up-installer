# Runtime safety

Use `smu bootstrap` for first-run setup:

```bash
smu bootstrap --dry-run --json --theme nord --prompt starship
smu bootstrap --theme nord --prompt starship --preset default --force
```

Bootstrap plans profile selection, resolved profile generation, adapter
materialization, and client update baselining. It refuses unmanaged adapter
target conflicts unless `--force` is provided.

Adapter materialization is conflict-safe by default:

```bash
smu adapter materialize --dry-run
smu adapter materialize nord starship --force
```

Existing targets are accepted when they are already the managed symlink or have
the same content as the source. Other targets stop the write so user-managed
config is not silently overwritten.

Mutating runtime commands use `~/.config/set-me-up/runtime.lock` so concurrent
shells or agents cannot write profile, adapter, catalog, update, or prune state
at the same time. Adapter copy and symlink writes are staged and swapped into
place to avoid partially-written targets.

Catalog trust policy is stored in `~/.config/set-me-up/catalog-trust.json`:

```bash
smu catalog trust status --json
smu catalog trust publisher dotbrains
smu catalog trust registry official
SMU_CATALOG_PUBLISHER=dotbrains smu catalog package work-shell
```

Rollback previews are machine-readable:

```bash
smu rollback --json
smu rollback --dry-run
```

`smu doctor --json` returns a full health snapshot covering profile choices,
catalog errors and trust policy, adapter conflicts, status, and client update
preflight state.
