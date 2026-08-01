# Blueprint Examples

Copy one of these surfaces into a downstream blueprint.

## rcm

```toml
[provisioning]
mode = "rcm"
adapter = "rcm"

[profile.default]
modules = ["base"]
```

```bash
smu plan --machine laptop
smu provisioning-adapter preflight --adapter rcm --profile default --json
```

## Nix

```toml
[provisioning]
mode = "nix"
adapter = "home-manager"

[profile.default]
modules = ["base"]
```

```bash
smu plan --machine workstation --json
smu provisioning-adapter preflight --adapter home-manager --profile default --json
```

## Hybrid

```toml
[provisioning]
mode = "hybrid"
adapter = "hybrid"
nix_adapter = "home-manager"

[profile.default]
modules = ["base"]
```

```bash
smu plan --provisioning-adapter hybrid --json
smu provisioning-adapter dashboard --adapter home-manager --json
```

## VPS

```bash
INSTALL_URL="https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh"
curl -fsSL "$INSTALL_URL" \
  | bash -s -- --profile vps --plan
curl -fsSL "$INSTALL_URL" \
  | bash -s -- --profile vps
smu doctor --strict --json
```

## CI

```yaml
name: set-me-up
on: [push, pull_request]
jobs:
  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - run: python3 set-me-up-installer/smu.py contract validate plan --json
      - run: >
          python3 set-me-up-installer/smu.py
          contract validate conformance --json
      - run: >
          python3 set-me-up-installer/smu.py
          blueprint ci --path . --check-docs --json
```
