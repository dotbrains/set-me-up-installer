# Headless VPS

Use this path for a headless Ubuntu/Debian VPS such as a DigitalOcean Droplet.

```bash
SMU_SUBMODULE_SCOPE=platform bash <(curl -s -L "$INSTALL_URL")
smu --setup-profile vps
```

`SMU_SUBMODULE_SCOPE=platform` initializes only the submodules needed by the
current host family plus shared docs, utilities, installer, and universal
modules. On Debian/Ubuntu that includes `dotfiles/modules/debian` and skips
macOS-only module repositories.

The `vps` setup profile provisions `server/headless`, a small server baseline
for transport, Git, archive, JSON, terminal, editor, and sync packages.
