# Provisioning Adapters

Provisioning adapters let a blueprint choose how `smu` applies modules and
dotfiles.

Declare the adapter in `smu.toml` at the blueprint root or under `dotfiles/`:

```toml
[provisioning]
adapter = "rcm"

[profile.default]
modules = ["nushell"]
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

Inspect support:

```bash
smu provisioning-adapter list
smu provisioning-adapter doctor --json
smu provisioning-adapter modules --json
smu provisioning-adapter coverage --json
smu provisioning-adapter parity --json
smu provisioning-adapter docs --output provisioning-adapter-coverage.md
smu provisioning-adapter validate
smu provisioning-adapter profile validate --adapter home-manager \
  --profile default --strict
smu provisioning-adapter audit --json
smu provisioning-adapter audit --adapter home-manager --profile default --strict
smu provisioning-adapter bootstrap --json
smu provisioning-adapter migrate --adapter home-manager \
  --profile default --output migration.md
smu provisioning-adapter scaffold --adapter all -m nushell
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

`smu provisioning-adapter parity` compares two adapters, defaulting to `rcm`
versus `home-manager`, and classifies each module as ready, source-only,
target-only, or missing.

`smu provisioning-adapter docs --output provisioning-adapter-coverage.md`
writes a generated Markdown coverage table. Use it as a checked-in dashboard or
as a drift check in repository validation.

`smu provisioning-adapter migrate --adapter home-manager --profile default
--output migration.md` writes a markdown checklist with ready modules checked
off and scaffold commands for missing adapter coverage.

## Nix Aliases

For Home Manager-first usage, `smu nix` aliases the longer adapter commands:

```bash
smu nix doctor
smu nix audit --profile default --json
smu nix init --profile default
smu nix coverage
smu nix plan --profile default
smu nix switch --profile default --dry-run
smu nix migrate --profile default --output migration.md
smu nix parity --profile default --json
```

`smu nix init` writes the generated Home Manager import file and companion
flake in the adapter state directory. `smu nix switch` writes the import file
and runs `home-manager switch`; use `--dry-run` to preview the command without
executing it.
