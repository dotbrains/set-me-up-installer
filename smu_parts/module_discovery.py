from .core import *


def _current_os_bucket():
    """Return the modules/<bucket> name matching the current OS, or None."""
    if macOS:
        return "macos"
    if debian:
        return "debian"
    if arch:
        return "arch"
    return None


def discover_modules():
    """Walk the modules directory and return {bucket: [(name, kind), ...]}.

    A module is any directory containing '<basename>.sh', 'brewfile', or 'packages'.
    `name` is the path relative to the bucket (e.g. 'productivity-tools/hyperkey'),
    which is the exact form accepted by `-m`. `kind` is 'script', 'brewfile', or 'packages'.
    """
    if not os.path.isdir(module_path):
        return {}

    buckets = {}
    for bucket in sorted(os.listdir(module_path)):
        bucket_dir = os.path.join(module_path, bucket)
        if not os.path.isdir(bucket_dir):
            continue

        modules = []
        for dirpath, _dirnames, filenames in os.walk(bucket_dir):
            if dirpath == bucket_dir:
                continue
            basename = os.path.basename(dirpath)
            has_script = f"{basename}.sh" in filenames
            has_brewfile = "brewfile" in filenames
            has_packages = "packages" in filenames
            if has_script or has_brewfile or has_packages:
                rel = os.path.relpath(dirpath, bucket_dir)
                if has_script:
                    kind = "script"
                elif has_brewfile:
                    kind = "brewfile"
                else:
                    kind = "packages"
                modules.append((rel, kind))

        if modules:
            buckets[bucket] = sorted(modules)

    return buckets


def list_modules(search=None, show_all=False):
    """Print a human-readable list of available modules."""
    buckets = discover_modules()
    if not buckets:
        warn(f"No modules found in '{module_path}'.")
        return

    current = _current_os_bucket()

    visible = {}
    for bucket, mods in buckets.items():
        if not show_all and current and bucket not in (current, "universal"):
            continue
        if search:
            needle = search.lower()
            mods = [(name, kind) for name, kind in mods if needle in name.lower()]
        if mods:
            visible[bucket] = mods

    if not visible:
        if search:
            warn(f"No modules match '{BOLD}{search}{NORMAL}'.")
        else:
            warn("No modules to display.")
        return

    total = 0
    for bucket in sorted(visible.keys()):
        mods = visible[bucket]
        total += len(mods)
        print(f"{BOLD}{bucket}/{NORMAL}")
        max_name = max(len(name) for name, _ in mods)
        for name, kind in mods:
            if kind == "script":
                tag_color = COL_GREEN
            elif kind == "brewfile":
                tag_color = COL_YELLOW
            else:
                tag_color = COL_RED
            print(f"  {name.ljust(max_name)}  {tag_color}[{kind}]{COL_RESET}")
        print()

    scope = ""
    if not show_all and current:
        scope = f" (showing '{current}' + 'universal'; use --all to include other OS buckets)"
    print(f"Found {BOLD}{total}{NORMAL} module(s){scope}.")
    print(f"Run a module with: {BOLD}smu -p --no-base -m <module>{NORMAL}")


def _format_fzf_lines(entries):
    """Format (bucket, name, kind) tuples into aligned fzf input lines."""
    if not entries:
        return []
    max_bucket = max(len(b) for b, _, _ in entries)
    max_name = max(len(n) for _, n, _ in entries)
    return [
        f"{bucket.ljust(max_bucket)}  {name.ljust(max_name)}  [{kind}]"
        for bucket, name, kind in entries
    ]


def _parse_fzf_selection(line):
    """Pull the module name (column 2) out of an fzf output line."""
    parts = line.split()
    if len(parts) >= 2:
        return parts[1]
    return None


def interactive_select_modules(search=None, show_all=False):
    """Launch fzf as a multi-select picker. Returns the chosen module names."""
    if subprocess.call("command -v fzf >/dev/null 2>&1", shell=True) != 0:
        die("'fzf' is not installed. Install it via your package manager (e.g. 'brew install fzf', 'apt install fzf', 'pacman -S fzf').")

    buckets = discover_modules()
    if not buckets:
        warn(f"No modules found in '{module_path}'.")
        return []

    current = _current_os_bucket()
    entries = []
    for bucket, mods in buckets.items():
        if not show_all and current and bucket not in (current, "universal"):
            continue
        for name, kind in mods:
            entries.append((bucket, name, kind))

    if not entries:
        warn("No modules to choose from.")
        return []

    fzf_input = "\n".join(_format_fzf_lines(entries))

    fzf_cmd = [
        "fzf",
        "--multi",
        "--prompt=modules> ",
        "--header=SPACE/TAB: toggle  ENTER: run  ESC: cancel",
        "--bind=space:toggle+down",
        "--height=60%",
        "--reverse",
        "--border",
    ]
    if search:
        fzf_cmd.extend(["--query", search])

    result = subprocess.run(fzf_cmd, input=fzf_input, capture_output=True, text=True)

    if result.returncode != 0 or not result.stdout.strip():
        warn("No modules selected.")
        return []

    selected = []
    for line in result.stdout.strip().split("\n"):
        name = _parse_fzf_selection(line)
        if name and name not in selected:
            selected.append(name)

    return selected


def self_update():
    """
    Update the 'set-me-up' scripts from the remote Git repository.
    This function assumes that the 'set-me-up' directory is a Git repository.
    """

    try:
        # Update the 'set-me-up' repository

        # Access SMU_BLUEPRINT_BRANCH and SMU_BLUEPRINT from environment variables
        smu_blueprint_branch = os.getenv("SMU_BLUEPRINT_BRANCH")
        smu_blueprint = os.getenv("SMU_BLUEPRINT")

        if not smu_blueprint_branch or not smu_blueprint:
            die("Please set the SMU_BLUEPRINT_BRANCH and SMU_BLUEPRINT environment variables.")

        action(f"Updating from branch: {smu_blueprint_branch} on repository: {smu_blueprint}")
        print()

        def run_install_script():
            """
            Run the install.sh script from the 'set-me-up-installer' repository.
            """

            command = "bash <(curl -s -L https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh) --no-header --skip-confirm"

            subprocess.run(
                ['bash', '-c', command],
                env=os.environ,
            )

        # Clean up old symlinks while the current source tree still exists.
        remove_symlinks()
        print()

        # Clean the 'set-me-up' directory
        shutil.rmtree(smu_home_dir, ignore_errors=True)

        run_install_script()

        # Symlink new files
        symlink()

        print()
        success("Successfully updated 'set-me-up'.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update 'set-me-up': {e}", file=sys.stderr)

def update_submodules():
    """
    Update the 'set-me-up' submodules from the remote Git repository.
    This function assumes that the 'set-me-up' directory is a Git repository.
    """

    try:
        action("Updating 'set-me-up' submodules\n")

        # Iterate over each submodule,
        # determine the default branch,
        # and pull updates from the default branch
        export_smu_home_dir = f"export SMU_HOME_DIR={smu_home_dir};"
        update_submodules_cmd = export_smu_home_dir + r"""
        git -C $SMU_HOME_DIR submodule foreach --recursive '(
            # Get the URL of the remote repository
            remote_url=$(git config --get remote.origin.url)

            # Get the default branch of the remote repository
            default_branch=$(git ls-remote --symref "$remote_url" HEAD | awk "/^ref:/ {sub(/refs\/heads\//, \"\", \$2); print \$2}")

            # Checkout the default branch
            git checkout "$default_branch"

            # Pull updates from the default branch
            git pull origin "$default_branch"
        )'
        """
        subprocess.check_call(update_submodules_cmd, shell=True)

        print()
        success("Successfully updated 'set-me-up' submodules.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update 'set-me-up' submodules: {e}", file=sys.stderr)


__all__ = [name for name in globals() if not name.startswith("__")]
