#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_home="$(mktemp -d)"
bin_dir="$(mktemp -d)"

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
    SMU_INSTALLER_REF="candidate" \
    PATH="$bin_dir:$PATH" \
    bash "$repo_root/install.sh" --no-header --skip-confirm --plan --json
)"

python3 - "$payload" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["blueprint"]["repo"] == "dotbrains/set-me-up-blueprint"
assert payload["blueprint"]["branch"] == "master"
assert payload["installer"]["ref"] == "candidate"
assert payload["mode"] == "ff-only"
PY
