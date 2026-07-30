#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_home="$(mktemp -d)"
bin_dir="$(mktemp -d)"

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
chmod +x "$bin_dir/curl"

payload="$(
    SMU_BLUEPRINT="dotbrains/set-me-up-blueprint" \
    SMU_BLUEPRINT_BRANCH="master" \
    SMU_HOME_DIR="$tmp_home/set-me-up" \
    PATH="$bin_dir:$PATH" \
    bash "$repo_root/install.sh" --no-header --skip-confirm --doctor --json
)"

python3 - "$payload" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["doctor"] is True
assert payload["blueprint"]["state"] == "missing"
assert payload["blueprint"]["readiness"] == "ready"
assert payload["installer"]["ref"] == "main"
PY

mkdir -p "$tmp_home/dirty/.git"
touch "$tmp_home/dirty/change"
git -C "$tmp_home/dirty" init --quiet

payload="$(
    SMU_BLUEPRINT="dotbrains/set-me-up-blueprint" \
    SMU_BLUEPRINT_BRANCH="master" \
    SMU_HOME_DIR="$tmp_home/dirty" \
    PATH="$bin_dir:$PATH" \
    bash "$repo_root/install.sh" --no-header --skip-confirm --doctor --json
)"

python3 - "$payload" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["blueprint"]["state"] == "dirty"
assert payload["blueprint"]["readiness"] == "blocked-dirty"
PY
