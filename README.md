# `set-me-up` installer

[![Tests](https://github.com/dotbrains/set-me-up-installer/actions/workflows/tests.yml/badge.svg)](https://github.com/dotbrains/set-me-up-installer/actions/workflows/tests.yml)
[![License: PolyForm Shield 1.0.0](https://img.shields.io/badge/License-PolyForm%20Shield%201.0.0-blue.svg)](https://polyformproject.org/licenses/shield/1.0.0)

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

Detailed catalog, registry, pack publishing, resolved profile, and adapter
authoring workflows live in [Catalogs And Adapters](docs/catalogs-and-adapters.md).

For the common checks after changing local profile or catalog files, run:

```bash
smu catalog doctor
smu profile resolve
smu profile doctor
smu adapter doctor
```

## Auditing what's installed

Use `smu status` or `-st` / `--status` to see which modules are currently
installed on the machine. Detection is read-only and never prompts:

```bash
smu status
smu --status
smu status --search font
smu status --all      # include modules from other OS buckets
smu status -V         # verbose: show per-entry detail
smu status --json     # machine-readable state for agents and scripts
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

## Planning and rollback

`smu` keeps an append-only state ledger at:

```text
~/.config/set-me-up/state/ledger.json
```

The ledger records module provision batches, module uninstall batches, and
adapter materialization runs. Adapter events include the previous file or
symlink state for each target so `smu rollback` can restore overwritten adapter
files.

Preview module and adapter changes before running them:

```bash
smu diff productivity/raycast
smu --diff -m productivity/raycast
smu adapter materialize --dry-run
smu -u -m productivity/raycast --dry-run
smu rollback --dry-run
```

Rollback is intentionally conservative:

- The last adapter materialization restores captured file or symlink snapshots.
- The last module provision batch runs the existing uninstall flow for those
  modules.
- Uninstall events are recorded for audit, but are not automatically rolled
  back because reinstalling removed package state can be lossy.

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
scripts/validate.sh --all
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
[PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0)
-- see [LICENSE](LICENSE) for details.
