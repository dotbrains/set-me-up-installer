# Headless VPS

Use this path for a headless Ubuntu/Debian VPS such as a DigitalOcean Droplet.

Install the base OS tools first:

```bash
sudo apt-get update
sudo apt-get install -y bash curl git ca-certificates
```

Preview and install a blueprint with only platform-relevant submodules:

```bash
INSTALL_URL="https://raw.githubusercontent.com/<OWNER>/<BLUEPRINT>/main/dotfiles/modules/install.sh"
SMU_SUBMODULE_SCOPE=platform bash <(curl -s -L "$INSTALL_URL") --plan
SMU_SUBMODULE_SCOPE=platform bash <(curl -s -L "$INSTALL_URL")
smu --setup-profile vps
```

`SMU_SUBMODULE_SCOPE=platform` initializes only the submodules needed by the
current host family plus shared docs, utilities, installer, and universal
modules. On Debian/Ubuntu that includes `dotfiles/modules/debian` and skips
macOS-only module repositories.

Fresh installs use shallow Git fetches for the blueprint and selected
submodules, which keeps small VPS bootstrap runs from paying for unrelated
history.

The `vps` setup profile provisions `server/headless`, a small server baseline
for transport, Git, archive, JSON, terminal, editor, and sync packages.

For a Nix-backed VPS blueprint, validate and apply the Home Manager adapter:

```bash
smu vps doctor --target ubuntu --mode nix --json
smu provisioning-adapter preflight --adapter home-manager --profile default --json
smu provisioning-adapter apply --adapter home-manager --profile default
```

For current rcm-backed dotfiles, use:

```bash
smu provisioning-adapter preflight --adapter rcm --profile default --json
smu provisioning-adapter apply --adapter rcm --profile default
```

Operational commands after first install:

```bash
smu rollback --json
smu rollback
smu update --all --dry-run
smu update --all --validate
```

Dotfiles repositories can validate the install surface without adopting the
full blueprint repository shape:

```bash
smu blueprint migrate-dotfiles --repo . --mode hybrid --dry-run --json
smu blueprint dotfiles-contract --repo . --strict --json
smu contract schema dotfiles-compatibility
smu contract validate dotfiles-compatibility \
  --path docs/json-contracts/dotfiles-compatibility.example.json \
  --json
```
