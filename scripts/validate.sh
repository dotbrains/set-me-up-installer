#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mode="${1:---all}"
python_bin="${PYTHON:-python3}"

python_checks() {
    "$python_bin" scripts/check_file_sizes.py
    "$python_bin" scripts/check_flat_directories.py
    find smu.py smu_parts tests scripts/check_file_sizes.py scripts/check_flat_directories.py \
        -type f -name "*.py" -print0 |
        xargs -0 "$python_bin" -m py_compile
    "$python_bin" -m unittest discover -s tests -t . -v

    if "$python_bin" -m pytest --version >/dev/null 2>&1; then
        "$python_bin" -m pytest tests/ -v
    fi

    "$python_bin" scripts/prompt_contract.py --local
    "$python_bin" scripts/preset_contract.py
    "$python_bin" scripts/generate-prompt-adapters.py --check-templates
}

cli_smoke() {
    local tmp_home pack_root pack_dir registry_dir registry_home install_home profile_home
    tmp_home="$(mktemp -d)"
    pack_root="$(mktemp -d)"
    pack_dir="$pack_root/ci-shell.smu-pack"
    registry_dir="$(mktemp -d)/catalog-registry"
    registry_home="$(mktemp -d)"
    install_home="$(mktemp -d)"
    profile_home="$(mktemp -d)"

    HOME="$tmp_home" "$python_bin" smu.py adapter init ci-shell
    mkdir -p "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell"
    printf '[profile.default]\nmodules = ["ci-shell"]\n' > "$tmp_home/set-me-up/smu.toml"
    printf 'id = "ci-shell"\n\n[adapters.home-manager]\npath = "home-manager.nix"\n' > "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell/module.toml"
    printf '{ ... }:\n\n{\n}\n' > "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell/home-manager.nix"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter validate
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter coverage --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter parity --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter docs --output "$tmp_home/coverage.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter docs --check --output "$tmp_home/coverage.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter profile validate --adapter home-manager --strict --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter audit --adapter home-manager -m ci-shell --strict --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter bootstrap --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter plan flake --adapter home-manager -m ci-shell
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter apply --adapter hybrid -m ci-shell --strict --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter migrate --adapter home-manager -m ci-shell --output "$tmp_home/migration.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter migrate state --adapter home-manager -m ci-shell --output "$tmp_home/migration-state.json"
    HOME="$tmp_home" "$python_bin" smu.py nix coverage --json
    HOME="$tmp_home" "$python_bin" smu.py nix doctor --profile default --json
    HOME="$tmp_home" "$python_bin" smu.py nix init -m ci-shell --json
    HOME="$tmp_home" "$python_bin" smu.py nix switch -m ci-shell --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py nix parity --json
    HOME="$tmp_home" "$python_bin" smu.py nix generate-adapter -m ci-shell --output "$tmp_home/generated-home-manager.nix"
    HOME="$tmp_home" "$python_bin" smu.py catalog package ci-shell --output "$pack_dir"
    "$python_bin" smu.py catalog publish "$pack_dir" --registry "$registry_dir"
    HOME="$registry_home" "$python_bin" smu.py catalog registry add local "$registry_dir"
    HOME="$registry_home" "$python_bin" smu.py catalog registry list
    HOME="$registry_home" "$python_bin" smu.py catalog search ci
    HOME="$registry_home" "$python_bin" smu.py catalog registry lock
    HOME="$registry_home" "$python_bin" smu.py catalog registry status
    HOME="$registry_home" "$python_bin" smu.py catalog install ci-shell --dry-run
    HOME="$install_home" "$python_bin" smu.py catalog install "$pack_dir" --dry-run
    HOME="$tmp_home" "$python_bin" smu.py catalog migrate --dry-run
    HOME="$tmp_home" "$python_bin" smu.py catalog doctor
    HOME="$tmp_home" "$python_bin" smu.py status --json --search ci
    HOME="$tmp_home" "$python_bin" smu.py diff ci-shell
    HOME="$tmp_home" "$python_bin" smu.py rollback --dry-run || true
    HOME="$profile_home" "$python_bin" smu.py profile resolve
    HOME="$profile_home" "$python_bin" smu.py profile doctor
    HOME="$profile_home" "$python_bin" smu.py adapter list
    HOME="$profile_home" "$python_bin" smu.py adapter materialize --dry-run
    tests/test_install_plan.sh
    tests/test_install_doctor.sh
    tests/test_install_guidance.sh
    scripts/container-smoke.sh
}

shell_checks() {
    find scripts -type f -name "*.sh" -print0 | xargs -0 shellcheck
    shellcheck install.sh smu
}

markdown_checks() {
    npx markdownlint-cli2 "**/*.md"
}

case "$mode" in
    --python)
        python_checks
        cli_smoke
        ;;
    --shell)
        shell_checks
        ;;
    --markdown)
        markdown_checks
        ;;
    --all)
        python_checks
        cli_smoke
        shell_checks
        markdown_checks
        ;;
    *)
        printf "Usage: %s [--all|--python|--shell|--markdown]\\n" "$0" >&2
        exit 2
        ;;
esac
