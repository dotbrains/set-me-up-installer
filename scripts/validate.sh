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
    local tmp_home pack_root pack_dir registry_dir registry_home install_home profile_home contract_home
    tmp_home="$(mktemp -d)"
    pack_root="$(mktemp -d)"
    pack_dir="$pack_root/ci-shell.smu-pack"
    registry_dir="$(mktemp -d)/catalog-registry"
    registry_home="$(mktemp -d)"
    install_home="$(mktemp -d)"
    profile_home="$(mktemp -d)"
    contract_home="$(mktemp -d)"

    HOME="$tmp_home" "$python_bin" smu.py adapter init ci-shell
    mkdir -p "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell"
    printf '[provisioning]\nmode = "nix"\nadapter = "home-manager"\n\n[profile.default]\nmodules = ["ci-shell"]\n' > "$tmp_home/set-me-up/smu.toml"
    printf 'id = "ci-shell"\n\n[adapters.home-manager]\npath = "home-manager.nix"\n' > "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell/module.toml"
    printf '{ ... }:\n\n{\n}\n' > "$tmp_home/set-me-up/dotfiles/modules/universal/ci-shell/home-manager.nix"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter validate
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter capabilities --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter coverage --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter dashboard --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter issue --output "$tmp_home/adapter-issue.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter parity --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter docs --output "$tmp_home/coverage.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter docs --check --output "$tmp_home/coverage.md"
    HOME="$tmp_home" "$python_bin" smu.py blueprint schema --check --output schemas/blueprint.schema.json
    HOME="$tmp_home" "$python_bin" smu.py blueprint compatibility --json
    HOME="$tmp_home" "$python_bin" smu.py blueprint compatibility --output "$tmp_home/compatibility.md"
    HOME="$tmp_home" "$python_bin" smu.py blueprint compatibility --check --output "$tmp_home/compatibility.md"
    HOME="$tmp_home" "$python_bin" smu.py blueprint doctor --strict --json
    HOME="$tmp_home" "$python_bin" smu.py plan --machine vps
    HOME="$tmp_home" "$python_bin" smu.py plan --machine vps --json
    HOME="$tmp_home" "$python_bin" smu.py secrets doctor --json
    HOME="$tmp_home" "$python_bin" smu.py trust doctor --json
    HOME="$tmp_home" "$python_bin" smu.py trust enforce ci-shell --allow-network --allow-unknown --json
    HOME="$tmp_home" "$python_bin" smu.py doctor --strict --json || true
    HOME="$tmp_home" "$python_bin" smu.py support bundle --redact --output "$tmp_home/support.json"
    HOME="$tmp_home" "$python_bin" smu.py conformance --repo "$tmp_home/set-me-up" --markdown --output "$tmp_home/conformance.md" || true
    HOME="$tmp_home" "$python_bin" smu.py migration-pr --repo "$tmp_home/set-me-up" --output "$tmp_home/migration-pr.json"
    HOME="$tmp_home" "$python_bin" smu.py release-package --version 1.2.3 --json
    HOME="$tmp_home" "$python_bin" smu.py inventory --json
    HOME="$tmp_home" "$python_bin" smu.py facts collect --json
    HOME="$tmp_home" "$python_bin" smu.py plan diff --from /dev/null --json
    HOME="$tmp_home" "$python_bin" smu.py approval --preset strict --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py state timeline --json
    HOME="$tmp_home" "$python_bin" smu.py lock --output "$tmp_home/smu.lock" --json
    HOME="$tmp_home" "$python_bin" smu.py bootstrap bundle --output "$tmp_home/bootstrap.zip" --json
    HOME="$tmp_home" "$python_bin" smu.py policy explain --preset ci --json
    HOME="$tmp_home" "$python_bin" smu.py golden-examples --json
    HOME="$tmp_home" "$python_bin" smu.py provenance --version 1.2.3 --json
    printf 'app1 root\n' > "$tmp_home/hosts.txt"
    HOME="$tmp_home" "$python_bin" smu.py fleet plan --hosts "$tmp_home/hosts.txt" --profile vps --json
    HOME="$tmp_home" "$python_bin" smu.py blueprint-registry --json
    HOME="$tmp_home" "$python_bin" smu.py module-graph base rcm --json
    HOME="$tmp_home" "$python_bin" smu.py tui --profile vps --json
    HOME="$tmp_home" "$python_bin" smu.py drift doctor --json
    HOME="$tmp_home" "$python_bin" smu.py post-install doctor --profile vps --json
    HOME="$tmp_home" "$python_bin" smu.py policy check --preset ci --json
    HOME="$tmp_home" "$python_bin" smu.py rollback-test restore --json
    HOME="$tmp_home" "$python_bin" smu.py product-docs generate --output "$tmp_home/product-docs.md" --json
    for contract in plan secrets-doctor trust-doctor support-bundle conformance fleet-plan drift-doctor policy-check release-package module-graph post-install; do
        "$python_bin" smu.py contract schema "$contract" >/dev/null
        "$python_bin" smu.py contract validate "$contract" --json
    done
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter profile validate --adapter home-manager --strict --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter audit --adapter home-manager -m ci-shell --strict --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter preflight --adapter home-manager -m ci-shell --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter preflight --adapter hybrid -m ci-shell --strict --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter bootstrap --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter plan flake --adapter home-manager -m ci-shell
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter apply --adapter hybrid -m ci-shell --strict --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter migrate --adapter home-manager -m ci-shell --output "$tmp_home/migration.md"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter migrate state --adapter home-manager -m ci-shell --output "$tmp_home/migration-state.json"
    HOME="$tmp_home" "$python_bin" smu.py provisioning-adapter migrate compare --adapter home-manager -m ci-shell --json
    HOME="$tmp_home" "$python_bin" smu.py nix coverage --json
    HOME="$tmp_home" "$python_bin" smu.py nix doctor --profile default --json
    HOME="$tmp_home" "$python_bin" smu.py nix init -m ci-shell --json
    HOME="$tmp_home" "$python_bin" smu.py nix switch -m ci-shell --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py nix apply -m ci-shell --dry-run --json
    HOME="$tmp_home" "$python_bin" smu.py nix migrate compare -m ci-shell --json
    HOME="$tmp_home" "$python_bin" smu.py nix parity --json
    HOME="$tmp_home" "$python_bin" smu.py nix generate-adapter -m ci-shell --output "$tmp_home/generated-home-manager.nix"
    for blueprint_mode in rcm nix hybrid; do
        mode_home="$(mktemp -d)"
        HOME="$mode_home" "$python_bin" smu.py blueprint init --mode "$blueprint_mode" --json
        HOME="$mode_home" "$python_bin" smu.py provisioning-adapter doctor --json
        HOME="$mode_home" "$python_bin" smu.py blueprint doctor --strict --json
    done
    migrate_home="$(mktemp -d)"
    mkdir -p "$migrate_home/set-me-up/dotfiles/modules/universal/ci-shell"
    printf 'id = "ci-shell"\n\n[adapters.rcm]\npath = "."\n' > "$migrate_home/set-me-up/dotfiles/modules/universal/ci-shell/module.toml"
    HOME="$migrate_home" "$python_bin" smu.py blueprint migrate --from rcm --to hybrid --force --json
    mkdir -p "$contract_home/examples/github-actions"
    mkdir -p "$contract_home/examples/providers/"{debian-vps,ubuntu-vps,arch-vps,nixos-vps,digitalocean-droplet,hetzner-cloud}
    printf '[provisioning]\nmode = "rcm"\nadapter = "rcm"\n' > "$contract_home/smu.toml"
    for workflow in rcm nix hybrid; do
        printf 'name: %s\njobs:\n  validate:\n    steps:\n      - run: smu provisioning-adapter preflight --json\n' \
            "$workflow" > "$contract_home/examples/github-actions/$workflow.yml"
    done
    for provider in debian-vps ubuntu-vps arch-vps; do
        printf '[provisioning]\nmode = "nix"\nadapter = "home-manager"\n' > "$contract_home/examples/providers/$provider/smu.toml"
    done
    printf '[provisioning]\nmode = "nix"\nadapter = "nixos"\n' > "$contract_home/examples/providers/nixos-vps/smu.toml"
    for provider in digitalocean-droplet hetzner-cloud; do
        printf '[provisioning]\nmode = "hybrid"\nadapter = "hybrid"\nnix_adapter = "home-manager"\n' > "$contract_home/examples/providers/$provider/smu.toml"
    done
    printf 'examples/providers/debian-vps\nexamples/github-actions/nix.yml\n' > "$contract_home/PROVISIONING-COMPATIBILITY.md"
    "$python_bin" smu.py blueprint providers --path "$contract_home" --json
    "$python_bin" smu.py blueprint recommend --path "$contract_home" --target ubuntu --json
    "$python_bin" smu.py blueprint recommend --path "$contract_home" --target rcm-only --dry-run --json
    "$python_bin" smu.py blueprint recommend --path "$contract_home" --target rcm-only --validate --json
    "$python_bin" smu.py blueprint ci --path "$contract_home" --check-docs --json
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
    "$python_bin" smu.py release-notes --from "$tmp_home/support.json" --output "$tmp_home/release-notes.md"
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
