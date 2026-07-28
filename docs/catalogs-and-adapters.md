# Catalogs And Adapters

Users can also add local catalog manifests without forking the managed repos:

```text
~/.config/set-me-up/catalogs/
├── themes/
├── prompt-profiles/
└── presets/
```

Catalog manifests use the same TOML shape as built-in manifests. New manifests
can inherit from a built-in or another catalog manifest with `extends`:

```toml
schema_version = 1
id = "work"
extends = "nord-minimal"
name = "Work"
description = "Nord colors with the classic shell prompt."
prompt = "classic"
```

Built-in manifests load first, then user catalog manifests. User catalog IDs
must be unique and cannot replace built-in IDs; use `extends` with a new ID for
variants. Validate the merged catalog with:

```bash
smu catalog path
smu catalog doctor
smu catalog migrate --dry-run
smu catalog migrate
smu doctor
```

`schema_version = 1` is the current manifest contract. `smu catalog doctor`
fails on unsupported future versions. Existing user catalog manifests without a
version can be upgraded in place with `smu catalog migrate`; use `--dry-run`
first to preview the files that would change.

Scaffold new user catalog manifests with init commands:

```bash
smu theme init work-theme --extends gruvbox
smu prompt init work-prompt --extends starship
smu preset init work-preset
smu adapter init work-shell
smu catalog doctor
```

Init commands write to the user catalog under `~/.config/set-me-up/catalogs/`.
They reject non-kebab-case IDs and refuse to overwrite an existing manifest
unless `--force` is passed. `smu adapter init` creates a shell prompt profile
plus starter source files under `prompt-profiles/files/`.

Catalog packs make user manifests portable. A pack is a directory with
`pack.toml` plus any of `themes/`, `prompt-profiles/`, and `presets/`:

```text
work-shell.smu-pack/
├── pack.toml
└── prompt-profiles/
    ├── work-shell.toml
    └── files/
        └── work-shell.bash
```

Package a user catalog manifest and its declared adapter source files:

```bash
smu catalog package work-shell --output work-shell.smu-pack
```

Publish a pack into a registry layout:

```bash
smu catalog publish ./work-shell.smu-pack --registry ./catalog-registry
```

Publishing writes `catalog-registry/packs/work-shell.smu-pack.zip`, calculates
its SHA-256 checksum, and creates or updates `catalog-registry/index.toml`.
Pass `--force` to replace an existing registry entry.

Install a local pack into the user catalog:

```bash
smu catalog install ./work-shell.smu-pack --dry-run
smu catalog install ./work-shell.smu-pack
smu catalog doctor
```

Pack install validates `pack.toml`, rejects unsupported schema versions, and
refuses to overwrite existing catalog files unless `--force` is passed.

Catalog registries make packs discoverable. A registry is a directory with an
`index.toml` file:

```toml
schema_version = 1

[packs.work-shell]
name = "Work Shell"
description = "Portable shell prompt pack."
source = "packs/work-shell.smu-pack"
sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
```

Add a personal or team registry, search it, and install by pack ID:

```bash
smu catalog registry add local ./catalog-registry
smu catalog registry add team https://example.com/set-me-up/index.toml
smu catalog registry list
smu catalog search shell
smu catalog registry lock
smu catalog registry status
smu catalog install work-shell --dry-run
smu catalog install work-shell
```

Registry names and pack IDs must be kebab-case. Relative `source` paths resolve
from the registry index directory or URL. Registry indexes use the same
`schema_version = 1` compatibility checks as catalog packs. Remote registries
and remote pack sources must use `https://`; downloaded indexes and ZIP packs
are cached under:

```text
~/.cache/set-me-up/catalogs/
```

Remote pack sources should point at a ZIP archive containing `pack.toml` at the
archive root, or inside one top-level directory.

Run `smu catalog registry lock` after adding or updating registries. The lock is
written to `~/.config/set-me-up/registry.lock` and records registry index hashes,
resolved pack sources, names, descriptions, and optional pack SHA-256 checksums.
When a lock exists, `smu catalog install <pack-id>` installs from the locked pack
metadata first. Use `smu catalog registry status` or `smu catalog doctor` to
detect registry drift and refresh the lock intentionally.

Remote pack entries can pin downloaded bytes with `sha256`. Generate the value
before publishing the registry index:

```bash
shasum -a 256 work-shell.smu-pack.zip
```

When `sha256` is present, `smu catalog install <pack-id>` refuses to install a
remote pack if the downloaded bytes do not match the registry entry.

Generate the shell-facing resolved profile after changing profile, override, or
catalog files:

```bash
smu profile resolve
smu profile doctor
```

`smu profile resolve` writes:

```text
~/.config/set-me-up/resolved.env
```

That file is generated from the selected preset, theme, prompt, override files,
catalog manifests, and inherited manifest fields. Shell, editor, terminal, and
module integrations can source one stable contract instead of duplicating
resolution logic:

```bash
export SMU_PRESET="nord-minimal"
export SMU_THEME="nord"
export SMU_PROMPT="starship-minimal"
export SMU_THEME_NAME="Nord"
export SMU_PROMPT_ENGINE="starship"
export SMU_PROMPT_THEME_AWARE="true"
```

`smu profile doctor` verifies that the selected preset, theme, and prompt exist
and that `resolved.env` matches the current resolved state.

Adapter packs are the files a selected theme or prompt exposes to the rest of
the system. Theme manifests declare adapters through sections such as
`[starship]`, `[alacritty]`, `[tmux]`, and `[nvim]`; prompt profiles declare
shell adapters in `[adapters]`.

Inspect and validate the resolved adapter pack:

```bash
smu adapter list
smu adapter doctor
smu adapter materialize --dry-run
smu adapter install nord classic
```

`smu adapter list [theme] [prompt]` prints every declared adapter path and
whether it exists. `smu adapter doctor [theme] [prompt]` fails if the selected
theme, prompt, or any declared adapter file is missing. `smu adapter install`
saves the selected theme and prompt, runs the `colorschemes` module, and
refreshes `resolved.env`.

Portable catalog manifests can declare files to materialize with explicit
source, target, and mode sections:

```toml
[adapter_sources]
bash = "files/work.bash"

[adapter_targets]
bash = "~/.config/bash/prompts/work.bash"

[adapter_modes]
bash = "copy"
```

Sources are relative to the manifest file unless they are absolute paths.
Targets support `~`. Supported modes are `copy` and `symlink`. Running
`smu adapter materialize [theme] [prompt]` writes generated tracking files to:

```text
~/.config/set-me-up/adapters/manifest.env
~/.config/set-me-up/adapters/manifest.json
```

Use `smu theme doctor [theme]` from the aggregate `set-me-up` checkout to check
that a theme manifest has the expected adapter files across the installer,
colorscheme module, shell, terminal, tmux, and editor repositories.

Prompt profiles are first-class manifests too. Each `prompt-profiles/*.toml`
declares the prompt engine, whether the prompt is theme-aware, and the Bash,
Zsh, Fish, and Nushell adapter paths required for that profile. Use
`smu prompt doctor [prompt]` from the aggregate checkout to validate those
adapters.

Prompt authoring checks:

```bash
python3 scripts/prompt_contract.py --local
python3 scripts/preset_contract.py
python3 scripts/generate-prompt-adapters.py --check-templates
python3 scripts/prompt_contract.py
python3 scripts/generate-prompt-adapters.py --check
python3 scripts/generate-prompt-adapters.py --write
```

The `--local` and `--check-templates` commands work in the standalone installer
repo. The full contract and generated adapter drift checks require the aggregate
`set-me-up` checkout because the shell adapters live in separate repositories.

Shared manifest semantics live in `scripts/smu_contract.py`. Reuse that module
for TOML parsing, kebab-case ID validation, catalog merging, inheritance
resolution, schema-version migration, and adapter source/target validation
instead of duplicating those rules in new scripts.

