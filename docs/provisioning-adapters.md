# Provisioning Adapters

Provisioning adapters let a blueprint choose how `smu` applies modules and
dotfiles.

Declare the adapter in `smu.toml` at the blueprint root or under `dotfiles/`:

```toml
[provisioning]
mode = "rcm"
adapter = "rcm"

[profile.default]
modules = ["nushell"]
```

Create that file with the blueprint initializer:

```bash
smu blueprint init --mode rcm
smu blueprint init --mode nix --output smu.toml --force
smu blueprint init --mode hybrid --json
smu blueprint doctor --strict --json
smu blueprint migrate --from rcm --to nix --force --json
smu blueprint migrate --from rcm --to hybrid --force --json
smu blueprint schema --output schemas/blueprint.schema.json
smu blueprint schema --check --output schemas/blueprint.schema.json
smu blueprint providers --path . --json
smu blueprint recommend --target ubuntu --path . --json
smu blueprint ci --path . --check-docs --json
smu blueprint compatibility --json
smu blueprint compatibility --output blueprint-compatibility.md
smu blueprint compatibility --check --output blueprint-compatibility.md
```

`rcm` uses thoughtbot's
[`rcm`](https://github.com/thoughtbot/rcm) for dotfile symlinks and keeps the
existing shell script, Brewfile, and Debian `packages` module behavior.

Nix-oriented adapter IDs:

- `home-manager`: Nix package manager plus Home Manager user provisioning.
- `nix-darwin`: macOS system and user provisioning through nix-darwin.
- `nixos`: full NixOS host provisioning.
- `hybrid`: Nix-first provisioning with `rcm` fallback.

All listed adapters are apply-capable. `hybrid` applies modules with the
configured Nix adapter when possible and falls back to `rcm` for legacy modules.

`smu blueprint doctor --strict` enforces that `provisioning.mode` and
`provisioning.adapter` agree. `mode = "rcm"` requires `adapter = "rcm"`,
`mode = "nix"` requires a Nix-family adapter, and `mode = "hybrid"` requires
`adapter = "hybrid"`.

`smu blueprint ci --path <checkout> --check-docs --json` is the portable CI
contract for blueprint repositories. It validates mode/adapter consistency,
provider examples, copyable GitHub Actions examples, and the checked-in
readiness document without requiring `SMU_HOME_DIR` to point at that checkout.
Use `smu blueprint providers --path <checkout> --json` to inspect the supported
provider examples as a machine-readable mode and adapter matrix.
Each provider row includes the selected adapter capability contract.
Use `smu blueprint recommend --target <host> --path <checkout> --json` when a
tool or developer wants the recommended mode, adapter, and provider example for
a host intent such as `debian`, `ubuntu`, `arch`, `nixos`, `digitalocean`,
`hetzner`, `macos`, or `rcm-only`.

Inspect support:

```bash
smu provisioning-adapter list
smu provisioning-adapter doctor --json
smu provisioning-adapter modules --json
smu provisioning-adapter coverage --json
smu provisioning-adapter capabilities --json
smu provisioning-adapter parity --json
smu provisioning-adapter docs --output provisioning-adapter-coverage.md
smu provisioning-adapter docs --check --output provisioning-adapter-coverage.md
smu provisioning-adapter validate
smu provisioning-adapter profile validate --adapter home-manager \
  --profile default --strict
smu provisioning-adapter audit --json
smu provisioning-adapter audit --adapter home-manager --profile default --strict
smu provisioning-adapter bootstrap --json
smu provisioning-adapter migrate --adapter home-manager \
  --profile default --output migration.md
smu provisioning-adapter migrate state --adapter home-manager \
  --profile default --output migration-state.json
smu provisioning-adapter migrate compare --adapter home-manager \
  --profile default --json
smu provisioning-adapter generate --adapter home-manager -m zsh
smu provisioning-adapter scaffold --adapter all -m nushell
smu nix doctor --profile default --json
smu nix audit --profile default --json
smu nix init --profile default --json
smu nix switch --profile default --dry-run --json
smu nix parity --profile default --json
smu --diff --provisioning-adapter home-manager -m editor/nvim
smu provisioning-adapter plan --adapter home-manager -m editor/nvim
smu provisioning-adapter plan --adapter nix-darwin -m nushell
smu provisioning-adapter plan --adapter nixos -m nushell
smu provisioning-adapter plan --adapter home-manager --profile default
smu provisioning-adapter plan write --adapter home-manager --profile default
smu provisioning-adapter plan flake --adapter nixos --profile server
smu provisioning-adapter apply --adapter home-manager --profile default
smu provisioning-adapter apply --adapter hybrid --profile default --dry-run --strict
smu provisioning-adapter apply --adapter home-manager --profile default \
  --action build --dry-run
smu provisioning-adapter apply --adapter nix-darwin --profile default
smu provisioning-adapter apply --adapter nixos --profile server
smu --provision --provisioning-adapter home-manager -m editor/nvim
```

`smu provisioning-adapter capabilities --json` is the stable machine-readable
contract for choosing between `rcm`, `home-manager`, `nix-darwin`, `nixos`, and
`hybrid`. It records the adapter mode, engine, scope, host families, Nix
requirement, and fallback behavior.

Module directories can publish adapter implementations with `module.toml`:

```toml
id = "editor/nvim"

[adapters.rcm]
path = "."

[adapters.home-manager]
path = "home-manager.nix"
risk = "low"
requires = ["nix"]
platforms = ["macos", "debian", "ubuntu", "arch", "linux"]
requires_root = false
secrets = false
services = []
reboot_required = false

[adapters.nixos]
path = "nixos.nix"
```

Existing modules without `module.toml` are treated as `rcm` modules when they
contain a legacy payload: `<module>.sh`, `brewfile`, or `packages`.

The typed schema for module manifests lives at
[`schemas/module.schema.json`](../schemas/module.schema.json). Validation
requires `id`, an `[adapters]` table, and a `path` for each adapter entry.

`--diff` resolves the selected provisioning adapter for each requested module.
For `hybrid`, this is a read-only compatibility plan; apply still requires an
available adapter.

The Nix-family plan command emits a small Nix module that imports every
requested module with a ready implementation for the selected adapter and
reports missing adapter coverage for the rest.

`plan write` stores that generated module under
`~/.config/set-me-up/adapters/<adapter>/<profile>.nix`, giving Nix-based
blueprints a stable local import path. Home Manager, nix-darwin, and NixOS use
the same generated import shape.

`plan flake` also writes `~/.config/set-me-up/adapters/<adapter>/flake.nix`
with the matching `homeConfigurations`, `darwinConfigurations`, or
`nixosConfigurations` output.

`apply` writes the same module and then runs the adapter's switch command:

```bash
home-manager switch -f ~/.config/set-me-up/adapters/home-manager/<profile>.nix
darwin-rebuild switch -I darwin-config=~/.config/set-me-up/adapters/nix-darwin/<profile>.nix
sudo nixos-rebuild switch -I nixos-config=~/.config/set-me-up/adapters/nixos/<profile>.nix
```

If any requested module lacks an implementation for the selected adapter,
`apply` exits before running the switch command and reports the missing adapter
coverage. `nix-darwin` apply is limited to macOS hosts, and `nixos` apply is
limited to NixOS hosts.

Use `--action build` or `--action test` to avoid switching immediately when the
underlying Nix tool supports that action. Add `--dry-run` to write the generated
artifact and print the command without executing it.

Every Nix apply and dry-run writes
`~/.config/set-me-up/adapters/<adapter>/<profile>.apply.json` with the action,
command, generated artifact path, and selected modules. Treat that as the audit
pointer for the last attempted adapter apply.

The `hybrid` adapter chooses the configured Nix adapter first and falls back to
`rcm` for modules without matching Nix coverage. Configure the Nix side with:

```toml
[provisioning]
adapter = "hybrid"
nix_adapter = "home-manager"
allow_rcm_fallback = true
```

Set `allow_rcm_fallback = false` or pass `--strict` to make migration audits
and dry-run applies fail until every selected module has the requested Nix
adapter.

## Bootstrap Readiness

`smu provisioning-adapter bootstrap --json` reports whether `nix`,
`home-manager`, `darwin-rebuild`, and `nixos-rebuild` are currently on `PATH`.
It is intentionally read-only. Install Nix and Home Manager through your chosen
system policy before running a non-dry-run apply.

## Migration Audits

`smu provisioning-adapter audit --adapter home-manager --profile default`
prints module-by-module readiness and a summary count. In JSON mode, agents can
use the same payload to create a migration checklist.

`smu provisioning-adapter coverage` prints ready/fallback/missing counts for
each adapter across discovered modules.

`smu blueprint compatibility --json` returns the full module-by-adapter matrix
using the same states, so blueprint repositories can publish a generated
compatibility dashboard or use the JSON in CI.

`smu blueprint compatibility --output blueprint-compatibility.md` writes a
generated Markdown matrix. Add `--check` to fail when the checked-in matrix is
missing or stale.

`smu provisioning-adapter parity` compares two adapters, defaulting to `rcm`
versus `home-manager`, and classifies each module as ready, source-only,
target-only, or missing.

`smu provisioning-adapter docs --output provisioning-adapter-coverage.md`
writes a generated Markdown coverage table. Use it as a checked-in dashboard or
as a drift check in repository validation.

Pass `--check` to fail when the generated coverage table is missing or stale.

`smu provisioning-adapter migrate --adapter home-manager --profile default
--output migration.md` writes a markdown checklist with ready modules checked
off and scaffold commands for missing adapter coverage.

`smu provisioning-adapter migrate state --adapter home-manager --profile
default --output migration-state.json` writes machine-readable review state for
each module. Ready modules are marked `accepted`; the rest start as `pending`.

`smu provisioning-adapter migrate compare --adapter home-manager --profile
default --json` compares the legacy `rcm` path with the target Nix adapter and
classifies each module as `ported`, `partial`, `blocked`, or `kept-rcm`.

`smu blueprint migrate --from rcm --to nix|hybrid` rewrites the blueprint
configuration for the target mode and prints the next validation commands. Use
`--force` when intentionally replacing an existing `smu.toml`.

`smu provisioning-adapter generate --adapter home-manager -m zsh` writes a
starter `home-manager.nix` adapter and updates `module.toml` for the selected
module.

## Nix Aliases

For Home Manager-first usage, `smu nix` aliases the longer adapter commands:

```bash
smu nix doctor
smu nix audit --profile default --json
smu nix init --profile default
smu nix coverage
smu nix plan --profile default
smu nix switch --profile default --dry-run
smu nix apply --profile default --dry-run --json
smu nix migrate --profile default --output migration.md
smu nix migrate compare --profile default --json
smu nix parity --profile default --json
smu nix generate-adapter -m zsh
```

`smu nix doctor --profile default --json` checks the selected profile's module
coverage, host support, required binaries, and platform policy fields. `smu nix
init` writes the generated Home Manager import file and companion flake in the
adapter state directory. `smu nix switch` writes the import file and runs
`home-manager switch`; use `--dry-run` to preview the command without executing
it.

## Install Modes

<!-- markdownlint-disable MD013 -->

| Mode | Hosts | Requires root | Apply command |
| --- | --- | --- | --- |
| `rcm` | macOS, Debian/Ubuntu, Arch | module-dependent | `smu --provision` |
| `home-manager` | macOS, Debian/Ubuntu, Arch with Nix | no | `home-manager switch -f <profile>.nix` |
| `nix-darwin` | macOS with Nix and nix-darwin | yes | `darwin-rebuild switch -I darwin-config=<profile>.nix` |
| `nixos` | NixOS | yes | `sudo nixos-rebuild switch -I nixos-config=<profile>.nix` |
| `hybrid` | Any host with selected Nix adapter support | module-dependent | Nix first, then `rcm` fallback |

<!-- markdownlint-enable MD013 -->
