#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
    printf "SKIP container smoke: docker not found\n"
    exit 0
fi

for image in debian:stable-slim ubuntu:24.04 archlinux:latest; do
    printf "container smoke\t%s\n" "$image"
    if ! docker run --rm \
        -v "$repo_root:/src:ro" \
        -e HOME=/tmp/smu-home \
        "$image" \
        sh -eu -c '
            command -v python3 >/dev/null 2>&1 || exit 0
            cd /src
            mkdir -p "$HOME/set-me-up/dotfiles/modules/universal/ci-shell"
            printf "[profile.default]\nmodules = [\"ci-shell\"]\n" > "$HOME/set-me-up/smu.toml"
            printf "id = \"ci-shell\"\n\n[adapters.home-manager]\npath = \"home-manager.nix\"\nplatforms = [\"linux\"]\n" > "$HOME/set-me-up/dotfiles/modules/universal/ci-shell/module.toml"
            printf "{ ... }:\n\n{\n}\n" > "$HOME/set-me-up/dotfiles/modules/universal/ci-shell/home-manager.nix"
            python3 smu.py nix doctor --profile default --json
            python3 smu.py nix init -m ci-shell --json
            python3 smu.py nix switch -m ci-shell --dry-run --json
        '; then
        printf "SKIP container smoke: %s unavailable on this host\n" "$image"
    fi
done
