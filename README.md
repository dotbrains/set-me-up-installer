# `set-me-up` installer

[![Tests](https://github.com/dotbrains/set-me-up-installer/actions/workflows/tests.yml/badge.svg)](https://github.com/dotbrains/set-me-up-installer/actions/workflows/tests.yml)
[![License: PolyForm Shield 1.0.0](https://img.shields.io/badge/License-PolyForm%20Shield%201.0.0-blue.svg)](https://polyformproject.org/licenses/shield/1.0.0/)

![preview](.github/preview.png)

This is the universal installer script used to install `set-me-up` (`smu`) on a
Mac, *debian*, or *arch* based machine.

## Obtaining `set-me-up` installer

To start, your default shell must be set to `bash` prior to executing the
`install` snippet for the first time. This is because on newer versions of Mac
OS, the default shell is `zsh` instead of `bash`. To change your default shell,
run the following command in your console.

```bash
sudo chsh -s $(which bash) $(whoami)
```

Once the default shell is `bash`, close and reopen the terminal window. Then,
run the following command in your console.

(⚠️ **DO NOT** run the `install` snippet if you don't fully
understand [what it does](../install.sh). Seriously, **DON'T**!)

```bash
INSTALL_URL="https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh"
bash <(curl -s -L "$INSTALL_URL")
```

You can change the `smu` home directory by setting an environment variable
called `SMU_HOME_DIR`. Keep the variable declared or the `smu` scripts are
unable to pick up the sources.

```bash
export SMU_HOME_DIR="some-path"
INSTALL_URL="https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh"
bash <(curl -s -L "$INSTALL_URL")
```

## Discovering modules

`smu` resolves a module name like `productivity-tools/hyperkey` against the
directory tree at `$SMU_HOME_DIR/dotfiles/modules/`, which is laid out by OS
bucket:

```text
$SMU_HOME_DIR/dotfiles/modules/
├── macos/        # MacOS-only modules
├── debian/       # Debian/Ubuntu-only modules
├── arch/         # Arch-only modules
└── universal/    # Modules that work on any supported OS
```

A module is any directory under one of those buckets that contains a matching
`<name>.sh` script, a `brewfile`, or a `packages` file on Debian-based systems.
The path you pass to `-m` is the path relative to the bucket. For example,
`modules/macos/productivity-tools/hyperkey/hyperkey.sh` is invoked as:

```bash
smu -p --no-base -m productivity-tools/hyperkey
```

The community-maintained module collections live in their own repositories.
Browse these to see what's available and to crib examples when authoring your
own:

- [dotbrains/set-me-up-macos-modules](https://github.com/dotbrains/set-me-up-macos-modules)
- [dotbrains/set-me-up-debian-modules](https://github.com/dotbrains/set-me-up-debian-modules)
- [dotbrains/set-me-up-universal-modules](https://github.com/dotbrains/set-me-up-universal-modules)

### Listing what's installed locally

To see the modules currently available in your `$SMU_HOME_DIR`, use `-l` /
`--list-modules`:

```bash
smu -l
```

Output is grouped by OS bucket. Each entry is tagged `[script]`, `[brewfile]`,
or `[packages]` so you know what kind of module it is, and the name shown is the
exact value you'd pass to `-m`:

```text
macos/
  productivity/hyperkey       [brewfile]
  terminal/alacritty          [script]

debian/
  browsers/chrome             [packages]
  development-tools/cursor    [script]

universal/
  python/pip                  [script]
  shell                       [brewfile]

Found 6 module(s).
Showing 'macos' + 'universal'; use --all to include other OS buckets.
Run a module with: smu -p --no-base -m <module>
```

By default the list hides modules that don't apply to the current OS. Pass
`--all` to include every bucket:

```bash
smu -l --all
```

To narrow the list, pass `--search <query>` for a case-insensitive substring
match against the module name:

```bash
smu -l --search hyper
smu -l --search python --all
```

### Interactive picker (fzf)

For a faster workflow, use `-i` / `--interactive` to launch an
[`fzf`](https://github.com/junegunn/fzf)-powered multi-select picker. Type to
fuzzy-filter, press **SPACE** or **TAB** to toggle a module, and press
**ENTER** to provision everything you selected:

```bash
smu -i --no-base
```

`-i` honors the same filters as `-l`:

```bash
smu -i --search node          # pre-fill the fzf query with "node"
smu -i --all                  # include modules from other OS buckets
```

Selected modules are run through the same provisioning pipeline as `-p -m ...`,
including the `-b` / `--no-base` flags. Requires `fzf` to be installed with
`brew install fzf`, `apt install fzf`, or `pacman -S fzf`.

## Theme and prompt profile

`set-me-up` stores the user's visual preferences in:

```text
~/.config/set-me-up/profile.env
```

The profile is a shell-compatible environment file:

```bash
export SMU_THEME="gruvbox"
export SMU_PROMPT="starship"
export SMU_PRESET="default"
```

Supported themes are discovered from the colorscheme module manifests at
`modules/colorschemes/themes/*.toml`:

- `gruvbox`
- `nord`
- `catppuccin`
- `tokyo-night`
- `rose-pine`
- `dracula`
- `everforest`
- `solarized`
- `kanagawa`

Supported prompt profiles are discovered from `prompt-profiles/*.toml`:

- `starship` - the default Starship prompt
- `starship-minimal` - a minimal Starship config, when provided by the
  active colorscheme module
- `classic` - a native shell prompt without Starship

Presets are discovered from `presets/*.toml`. A preset is a named bundle that
selects one theme and one prompt profile:

- `default` - Gruvbox with the full Starship prompt
- `nord-minimal` - Nord with the minimal Starship prompt
- `classic-gruvbox` - Gruvbox with the native shell prompt
- `tokyo-night` - Tokyo Night with the full Starship prompt

Set preferences after install:

```bash
smu theme list
smu theme set nord --apply
smu theme doctor nord
smu prompt list
smu prompt set classic
smu prompt doctor classic
smu preset list
smu preset set nord-minimal --apply
smu preset doctor nord-minimal
smu doctor
smu profile
```

Set preferences during bootstrap:

```bash
INSTALL_URL="https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh"
bash <(curl -s -L "$INSTALL_URL") --theme nord --prompt classic
bash <(curl -s -L "$INSTALL_URL") --preset nord-minimal
```

The `--apply` flag on `smu theme set` runs the `colorschemes` module so tool
adapters such as Starship, lazygit, fish, and Alacritty are updated
immediately. Shells and dotfiles also read `SMU_THEME` / `SMU_PROMPT` directly,
so new terminals pick up the saved profile.

Users can keep machine-local choices outside the managed repo by creating
override files in `~/.config/set-me-up/`:

```toml
# theme.toml
theme = "nord"

# prompt.toml
prompt = "classic"

# preset.toml
preset = "nord-minimal"
```

Resolution order is environment variable, local override file, saved profile,
then defaults. For example, `SMU_THEME` wins over `theme.toml`, and
`theme.toml` wins over `profile.env`.

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
smu doctor
```

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

## Auditing what's installed

Use `-st` / `--status` to see which modules are currently installed on the
machine. Detection is read-only and never prompts:

```bash
smu --status
smu --status --search font
smu --status --all      # include modules from other OS buckets
smu --status -V         # verbose: show per-entry detail
```

Output lists every visible module with a state tag and a count summary at the
bottom:

```text
debian/
  browsers/chrome             [packages]   [OK] installed
  development-tools/cursor    [script]     [OK] installed
  development-tools/zed       [script]     [--] missing
  fonts/fira-code             [script]     [??] unknown

3 module(s).
Showing 'debian' + 'universal'; use --all to include other OS buckets.
  1 installed, 1 missing, 0 partial, 1 unknown
```

State meanings:

| Tag | Meaning |
| --- | --- |
| `[OK] installed` | The module's payload is fully present. |
| `[--] missing` | The module's payload is fully absent. |
| `[~~] partial` | Some package entries are present, others aren't. |
| `[??] unknown` | A `*.sh` module without a sibling marker. |

How each kind is detected:

- **`brewfile`** → `brew bundle check --file <brewfile> --no-upgrade`.
- **`packages`** → each entry checked individually with `dpkg -s`, `snap list`,
  or `sources.list.d` lookups. Reports `partial` when only some entries are
  present.
- **`*.sh`** → if the module ships an opt-in `<name>.installed` sibling, smu
  sources it under `utilities.sh`; exit 0 means installed. Without the marker
  the module reports `unknown`.

## Uninstalling modules

Use `-u` / `--uninstall` to undo a module's install. Brewfiles and `packages`
files are reversed declaratively; `*.sh` modules require an opt-in
`<name>.uninstall.sh` sibling. Without one, they are surfaced as manual cleanup
and skipped.

```bash
smu -u -m media/spotify productivity/raycast    # prompts [y/N]
smu -u -m media/spotify --dry-run               # show the plan, change nothing
smu -u -m media/spotify -y                      # skip the prompt (scripts/CI)
smu -iu                                         # fzf picker, multi-select uninstall
```

The plan is shown before any destructive action so you can sanity-check it:

```text
The following will be uninstalled:
  - development-tools/cursor  (cursor.uninstall.sh ; apt_remove_from_file packages)
  - browsers/chrome           (apt_remove_from_file packages)

Cannot auto-uninstall:
  ! installers                (no installers.uninstall.sh)

Continue? [y/N]
```

How each kind is reversed:

- **`brewfile`** → `brew bundle cleanup --file <brewfile> --force`.
- **`packages`** → `apt_remove_from_file packages`, mirroring
  `apt_install_from_file` for apt packages, snaps, apt repositories, source
  lists, and keyrings.
- **`*.sh`** → sources sibling `<name>.uninstall.sh`. Modules that share their
  directory with a `packages` or `brewfile` run **both** inverses in order:
  per-module uninstaller first, then declarative cleanup.

### Authoring sibling files for a custom `*.sh` module

Two optional files alongside `<name>.sh` opt the module into the status and
uninstall flows:

- `<name>.installed` — sourced by `--status`. Exit 0 means installed; non-zero
  means missing. Keep it terse:

  ```bash
  # development-tools/cursor/cursor.installed
  package_is_installed "cursor"
  ```

- `<name>.uninstall.sh` — sourced by `--uninstall`. Same shape as the install
  script: source `utilities.sh`, guard with `is_macos` / `is_debian`, do the
  inverse work. Do not re-undo what a sibling `packages` or `brewfile` declares;
  `smu` chains those automatically:

  ```bash
  # development-tools/cursor/cursor.uninstall.sh
  source "$HOME/set-me-up/dotfiles/utilities/utilities.sh"

  main() {
      if ! is_debian; then error "Debian only!"; return 1; fi
      ask_for_sudo
      sudo apt-get remove --purge -y cursor &> /dev/null
      sudo rm -f /etc/apt/sources.list.d/cursor.list
      sudo rm -f /etc/apt/keyrings/cursor.gpg
      sudo apt-get autoremove -qqy &> /dev/null
  }
  main
  ```

Without these sibling files a module installs as before but reports `unknown`
under `--status` and is skipped by `--uninstall`.

## Reproducible dev environment (Flox)

The installer ships a [Flox](https://flox.dev) manifest at
`.flox/env/manifest.toml` that pins the toolchain used by CI: `bash`,
`python3`, `shellcheck`, `nodejs`, `git`, and a project-local `pytest` venv.
Activating it gives you the same versions GitHub Actions runs, on macOS or
Linux, without touching your global Python or Homebrew state.

```bash
# One-time: install Flox.
brew install flox

# From the installer/ directory:
flox activate

# Inside the activated shell you can run the same checks CI runs:
pytest tests/ -v
shellcheck install.sh smu scripts/*.sh
npx markdownlint-cli2 "**/*.md"
```

`SMU_BLUEPRINT` and `SMU_BLUEPRINT_BRANCH` are seeded with the same placeholder
values the CI workflow uses. Export your own before `flox activate` to test
against a real blueprint.

## Liability

The creator of this repo is *not responsible* if your machine ends up in a
state you are not happy with.

## Contributions

Yes please! This is a GitHub repo. I encourage anyone to contribute. 😃

## License

This project is licensed under the
[PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0/)
-- see [LICENSE](LICENSE) for details.
