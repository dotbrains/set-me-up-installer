#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_home="$(mktemp -d)"
bin_dir="$(mktemp -d)"
output="$tmp_home/install-output.log"

cleanup() {
    rm -rf "$tmp_home" "$bin_dir"
}
trap cleanup EXIT

cat > "$bin_dir/curl" <<'EOF'
#!/usr/bin/env bash
cat <<'UTILITIES'
bold=""
normal=""
get_os() { printf "debian"; }
error() { printf "%s\n" "$*" >&2; exit 1; }
warn() { printf "%s\n" "$*" >&2; }
success() { printf "%s\n" "$*" >&2; }
action() { printf "%s\n" "$*" >&2; }
cmd_exists() { command -v "$1" >/dev/null 2>&1; }
UTILITIES
EOF

cat > "$bin_dir/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    clone)
        dest="${@: -1}"
        mkdir -p "$dest/.git"
        ;;
    *)
        exit 0
        ;;
esac
EOF

chmod +x "$bin_dir/curl" "$bin_dir/git"

SMU_BLUEPRINT="dotbrains/set-me-up-blueprint" \
SMU_BLUEPRINT_BRANCH="master" \
SMU_HOME_DIR="$tmp_home/set-me-up" \
PATH="$bin_dir:$PATH" \
    bash "$repo_root/install.sh" --no-header --skip-confirm > "$output" 2>&1

grep -Fq "smu update doctor --json" "$output"
grep -Fq "smu update --plan" "$output"
