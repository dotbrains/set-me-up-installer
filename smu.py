#!/usr/bin/env python3

import argparse
import subprocess
import os
import sys

# ANSI escape codes for colors
COL_YELLOW = '\033[93m'
COL_RED = '\033[91m'
COL_GREEN = '\033[92m'
COL_RESET = '\033[0m'

# Text styling using ANSI escape sequences
BOLD = '\033[1m'
NORMAL = '\033[0m'

# set-me-up paths
smu_home_dir = os.getenv("SMU_HOME_DIR", os.path.join(os.path.expanduser("~"), "set-me-up"))
module_path = os.path.join(smu_home_dir, "dotfiles/modules")

# 'set-me-up' installer scripts
installer_path = os.path.join(smu_home_dir, "set-me-up-installer")
installer_scripts_path = os.path.join(installer_path, "scripts")

# rcm configuration file path
rcrc = os.path.join(smu_home_dir, "dotfiles/rcrc")

# GitHub blueprint for finding removed files (optimizes broken symlink cleanup)
smu_blueprint = os.getenv("SMU_BLUEPRINT")
smu_blueprint_branch = os.getenv("SMU_BLUEPRINT_BRANCH")

# Determine if OS is MacOS
macOS = sys.platform == "darwin"

# Determine if OS is Linux
linux = sys.platform.startswith("linux")

# Generic function to check Linux distribution
def _is_linux_distro(distro_ids):
    """Check if the system matches any of the given distribution IDs.

    Args:
        distro_ids: List of distribution identifiers to check for (e.g., ['debian', 'ubuntu'])

    Returns:
        bool: True if the system matches any of the given distro IDs
    """
    if not linux or not os.path.exists("/etc/os-release"):
        return False

    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
            # Check for ID=<distro> or ID_LIKE=<distro>
            return any(
                f"id={distro}" in content or f"id_like={distro}" in content
                for distro in distro_ids
            )
    except (IOError, OSError):
        return False

# Determine if OS is debian-based (Debian, Ubuntu)
debian = _is_linux_distro(['debian', 'ubuntu'])

# Determine if OS is arch-based (Arch)
arch = _is_linux_distro(['arch'])

def warn(message):
    print(f"{COL_YELLOW}[warning]{COL_RESET} {message}")

def success(message):
    print(f"{COL_GREEN}[success]{COL_RESET} {message}")

def action(message):
    print(f"{COL_YELLOW}[action]{COL_RESET} ⇒ {message}")

def die(message, exit_code=1):
    print(f"{COL_RED}[error]{COL_RESET} {message}", file=sys.stderr)
    sys.exit(exit_code)

def list_symlinks():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"lsrc -v -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def symlink():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"rcup -v -f -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def remove_symlinks():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"rcdn -v -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

    # Clean up broken symlinks and empty directories left behind by rcdn
    # Use lsrc to get the list of symlinks managed by rcm - this is more efficient
    # than scanning tag-* directories, as lsrc already knows what's managed
    dotfiles_dir = os.path.join(smu_home_dir, "dotfiles")
    home_dir = os.path.expanduser("~")

    if os.path.exists(dotfiles_dir):
        # Get all symlink targets from lsrc (files and directories managed by rcm)
        result = subprocess.run(
            f"lsrc -v {os.path.join(smu_home_dir, 'dotfiles')}",
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            # Extract basenames from lsrc output (format: target -> source)
            lines = result.stdout.strip().split('\n')
            basenames = set()
            
            for line in lines:
                # lsrc output format: "/home/user/.zshrc -> /path/to/dotfiles/..."
                # Extract the target path (left side of ->)
                if '->' in line:
                    target = line.split('->')[0].strip()
                    if target:
                        basename = os.path.basename(target)
                        if basename:
                            basenames.add(basename)

            if basenames:
                # Build a single find command with -o (OR) conditions for all names
                name_conditions = []
                for name in basenames:
                    # Escape single quotes in names
                    escaped_name = name.replace("'", "'\\''")
                    name_conditions.append(f"-name '{escaped_name}'")

                find_expr = " -o ".join(name_conditions)

                # Remove empty directories matching any name in ~/.config and ~/.local
                subprocess.run(
                    f"find {home_dir}/.config {home_dir}/.local -type d -empty \\( {find_expr} \\) -delete 2>/dev/null || true",
                    shell=True
                )

                # Remove symlinks (not regular files) matching any name in ~/.config, ~/.local, and ~
                # This only removes symlinks that rcm created, not regular files the user might have
                subprocess.run(
                    f"find {home_dir}/.config {home_dir}/.local {home_dir} -type l \\( {find_expr} \\) -delete 2>/dev/null || true",
                    shell=True
                )

        # Clean up broken symlinks from files that were removed from the blueprint repo
        # This is more efficient than scanning all of ~ by using GitHub API to get the list
        # of files that currently exist in the blueprint, then finding what's missing locally
        
        # Get the list of basenames from the blueprint repo (what should exist)
        blueprint_basenames = _get_blueprint_basenames()
        
        if blueprint_basenames:
            # Build find expression for only the basenames that exist in blueprint
            name_conditions = []
            for name in blueprint_basenames:
                escaped_name = name.replace("'", "'\\''")
                name_conditions.append(f"-name '{escaped_name}'")

            find_expr = " -o ".join(name_conditions)

            # Only check for broken symlinks matching blueprint files (not all symlinks)
            subprocess.run(
                f"find {home_dir}/.config {home_dir}/.local {home_dir} -type l \\( {find_expr} \\) ! -exec test -e {{}} \\; -delete 2>/dev/null || true",
                shell=True
            )


def _get_blueprint_basenames():
    """Get the set of file basenames from the blueprint repo's tag-* directories.
    
    Uses GitHub API to efficiently get the list of files without scanning local directories.
    Returns a set of basenames (e.g., {'zshrc', 'gitconfig', 'alacritty.toml'})
    """
    # Validate required environment variables
    if not smu_blueprint:
        die("SMU_BLUEPRINT environment variable is not set. Please set it to your blueprint repo (e.g., 'owner/repo').")
    
    if not smu_blueprint_branch:
        die("SMU_BLUEPRINT_BRANCH environment variable is not set. Please set it to your blueprint branch (e.g., 'main').")
    
    try:
        # Use GitHub API to get tree of tag-* directories from the blueprint repo
        # This is much faster than scanning ~ recursively
        result = subprocess.run(
            f"gh api repos/{smu_blueprint}/git/trees/{smu_blueprint_branch}?recursive=1 --jq '.tree[].path' 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0 or not result.stdout.strip():
            return set()

        # Filter to only tag-* directories under dotfiles/ and extract basenames
        basenames = set()
        for path in result.stdout.strip().split('\n'):
            # Only match dotfiles/tag-* paths
            if path.startswith('dotfiles/tag-') and '/' in path:
                # Get the basename (last component of the path)
                basename = os.path.basename(path)
                if basename:
                    basenames.add(basename)

        return basenames
    except subprocess.TimeoutExpired:
        return set()
    except Exception:
        return set()

def create_boot_disk():
    # Execute create boot disk script
    script_path = os.path.join(installer_scripts_path, "create_boot_disk/create_boot_disk.sh")
    subprocess.run(f"bash {script_path}", shell=True)

def update():
    """
    Update the given OS.
    """

    if debian:
        script_path = os.path.join(installer_scripts_path, "update/debian.sh")
    elif macOS:
        script_path = os.path.join(installer_scripts_path, "update/macos.sh")
    elif arch:
        script_path = os.path.join(installer_scripts_path, "update/arch.sh")

    subprocess.run(f"bash {script_path}", shell=True)

def get_module_path(module_name):
    """
    Get the path to the given module.
    If the module is not supported on the current OS or does not exist then return None.
    """

    def extract_dir_and_module_name(module):
        """
        Extract the directory name and module name from the given string.
        """

        # Get the directory name and module name
        # e.g., python/pip (module_name)
        # dir_name = python/pip
        # module_name = pip

        # Split the string by '/'
        parts = module.split('/')

        # The directory name is the input string itself
        dir_name = module

        # The module name is the last part of the split string
        module_name = parts[-1]

        return dir_name, module_name

    def obtain_universal_module_path(module_name):
        """
        Get the path to the given universal module.
        If the module does not exist then return None.
        """

        # If the module name contains a '/', then the module is in a subdirectory of the 'universal' directory
        # e.g., modules/universal/python/pip/pip.sh
        if '/' in module_name:
            dir_name, extracted_module_name = extract_dir_and_module_name(module_name)
            module_dir = os.path.join(module_path, "universal", dir_name)
            script_path = os.path.join(module_dir, f"{extracted_module_name}.sh")
            brewfile_path = os.path.join(module_dir, "brewfile")
            packages_path = os.path.join(module_dir, "packages")

            if os.path.exists(script_path):
                return script_path
            if os.path.exists(brewfile_path):
                return brewfile_path
            if os.path.exists(packages_path):
                return packages_path
            return None

        # Universal module path
        # e.g., modules/universal/fonts/fonts.sh
        module_dir = os.path.join(module_path, "universal", module_name)
        script_path = os.path.join(module_dir, f"{module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")

        if os.path.exists(script_path):
            return script_path
        if os.path.exists(brewfile_path):
            return brewfile_path
        if os.path.exists(packages_path):
            return packages_path
        return None

    # If we are trying to get the 'base' module, then return the path to the 'base' directory
    if module_name == "base":
        return os.path.join(smu_home_dir, "dotfiles/base", f"{module_name}.sh")

    # Determine the OS of the module by checking if the module is part of an OS-specific directory
    # e.g., modules/macos/fonts/fonts.sh
    #       modules/debian/fonts/fonts.sh
    #       modules/arch/fonts/fonts.sh
    # If the module is not part of an OS-specific directory, then the module is universal, so
    # check the 'universal' directory for the module
    # e.g., modules/universal/python/pip/pip.sh

    if not macOS and not debian and not arch:
        return obtain_universal_module_path(module_name)

    smu_os = ""

    if macOS:
        smu_os = "macos"
    elif debian:
        smu_os = "debian"
    elif arch:
        smu_os = "arch"

    # Module path
    # e.g., modules/macos/fonts/fonts.sh
    #       modules/macos/productivity/rectangle-pro/rectangle-pro.sh
    #       modules/debian/fonts/fonts.sh
    if '/' in module_name:
        dir_name, extracted_module_name = extract_dir_and_module_name(module_name)
        module_dir = os.path.join(module_path, smu_os, dir_name)
        script_path = os.path.join(module_dir, f"{extracted_module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")
    else:
        module_dir = os.path.join(module_path, smu_os, module_name)
        script_path = os.path.join(module_dir, f"{module_name}.sh")
        brewfile_path = os.path.join(module_dir, "brewfile")
        packages_path = os.path.join(module_dir, "packages")

    if os.path.exists(script_path):
        return script_path
    if os.path.exists(brewfile_path):
        return brewfile_path
    if os.path.exists(packages_path):
        return packages_path
    return obtain_universal_module_path(module_name)


def provision_module(module_name):
    # Get the path to the module
    script_path = get_module_path(module_name)

    # Check if the script exists
    if not script_path:
        warn(f"'{script_path}' does not seem to exist, skipping.")
        return False

    # Check that bash is installed
    if subprocess.call("command -v bash &> /dev/null", shell=True) != 0:
        warn("'bash' is not installed, skipping.")
        return False

    action(f"Running {script_path} module\n")

    script_dir = os.path.dirname(script_path)
    os.chdir(script_dir)

    if os.path.basename(script_path) == "brewfile":
        subprocess.run("brew bundle install --file brewfile", shell=True)
        return True

    if os.path.basename(script_path) == "packages":
        if not debian:
            warn(f"'{script_path}' is only supported on Debian-based systems, skipping.")
            return False
        utilities = os.path.join(smu_home_dir, "dotfiles/utilities/utilities.sh")
        subprocess.run(
            f"bash -c 'source {utilities} && apt_install_from_file packages'",
            shell=True,
        )
        return True

    # Execute before.sh if exists
    before_script = os.path.join(script_dir, "before.sh")
    if os.path.exists(before_script):
        subprocess.run(f"bash -c 'source {before_script}'", shell=True)

    # Execute main script
    subprocess.run(f"bash -c 'source {script_path}'", shell=True)

    # Execute after.sh if exists
    after_script = os.path.join(script_dir, "after.sh")
    if os.path.exists(after_script):
        subprocess.run(f"bash -c 'source {after_script}'", shell=True)

    return True

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

        def run_install_script():
            """
            Run the install.sh script from the 'set-me-up-installer' repository.
            """

            command = "bash <(curl -s -L https://raw.githubusercontent.com/dotbrains/set-me-up-installer/main/install.sh) --no-header --skip-confirm"

            subprocess.run(
                ['bash', '-c', command],
                env=os.environ,
            )

        # Clean the 'set-me-up' directory
        subprocess.run(f"rm -rf {smu_home_dir}", shell=True)

        run_install_script()

        # Clean up old symlinks
        remove_symlinks()

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

def _module_basename(script_path):
    """Return the basename used by *.sh-style modules (e.g. 'cursor' for cursor.sh)."""
    base = os.path.basename(script_path)
    if base.endswith(".sh"):
        return base[:-3]
    return base


def _packages_entries(packages_file):
    """Parse a 'packages' file and yield (kind, value) tuples.

    Mirrors apt_install_from_file's regex set so detection/removal stay symmetric
    with installation. Comments and unrecognised lines are skipped silently.
    """
    import re

    patterns = [
        ("ppa",          re.compile(r'^\s*ppa "(.*)"\s*$')),
        ("apt",          re.compile(r'^\s*apt "(.*)"\s*$')),
        ("snap",         re.compile(r'^\s*snap "(.*)" \[args: "(.*)"\]\s*$')),
        ("deb",          re.compile(r'^\s*deb "(.*)" \[args: "(.*)", "(.*)"\]\s*$')),
        ("source",       re.compile(r'^\s*source "(.*)" \[args: "(.*)"\]\s*$')),
    ]

    if not os.path.exists(packages_file):
        return

    with open(packages_file) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            for kind, pat in patterns:
                m = pat.match(line)
                if m:
                    yield (kind, m.groups())
                    break


def _packages_entry_installed(kind, groups):
    """Return True if the given parsed entry is currently installed."""
    if kind in ("apt", "deb"):
        package = groups[0]
        return subprocess.call(
            f"dpkg -s {package}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) == 0
    if kind == "snap":
        package = groups[0]
        return subprocess.call(
            f"snap list {package}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) == 0
    if kind == "ppa":
        ppa = groups[0]
        slug = ppa.replace("/", "-")
        result = subprocess.run(
            f"ls /etc/apt/sources.list.d/ 2>/dev/null | grep -i {slug}",
            shell=True,
            capture_output=True,
        )
        return result.returncode == 0
    if kind == "source":
        list_name = groups[0]
        return os.path.exists(f"/etc/apt/sources.list.d/{list_name}")
    return False


def module_status(module_name):
    """Determine whether a module's payload is currently installed.

    Returns a tuple (state, detail) where state is one of:
      - 'installed': everything declared by the module is present
      - 'missing':   nothing declared by the module is present
      - 'partial':   some entries present, others not (packages-only)
      - 'unknown':   *.sh module with no <name>.installed marker, or off-OS
    """
    script_path = get_module_path(module_name)
    if not script_path:
        return ("unknown", "module path not found")

    basename = os.path.basename(script_path)
    script_dir = os.path.dirname(script_path)

    if basename == "brewfile":
        if not macOS:
            return ("unknown", "brewfile is only supported on macOS")
        result = subprocess.run(
            f"cd {script_dir} && brew bundle check --file brewfile --no-upgrade",
            shell=True,
            capture_output=True,
        )
        return ("installed", None) if result.returncode == 0 else ("missing", None)

    if basename == "packages":
        if not debian:
            return ("unknown", "packages is only supported on Debian-based systems")
        entries = list(_packages_entries(script_path))
        installable = [(k, g) for k, g in entries if k in ("apt", "deb", "snap", "ppa", "source")]
        if not installable:
            return ("unknown", "no installable entries declared")
        present = sum(1 for k, g in installable if _packages_entry_installed(k, g))
        if present == len(installable):
            return ("installed", f"{present}/{len(installable)} entries present")
        if present == 0:
            return ("missing", f"0/{len(installable)} entries present")
        return ("partial", f"{present}/{len(installable)} entries present")

    # *.sh module: defer to optional <basename>.installed marker
    name = _module_basename(script_path)
    marker = os.path.join(script_dir, f"{name}.installed")
    if not os.path.exists(marker):
        return ("unknown", f"no {name}.installed marker")

    utilities = os.path.join(smu_home_dir, "dotfiles/utilities/utilities.sh")
    result = subprocess.run(
        f"bash -c 'source {utilities} && source {marker}'",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ("installed", None) if result.returncode == 0 else ("missing", None)


def _uninstall_steps(script_path):
    """Return the ordered list of inverse steps for a module path.

    Each step is a (label, runnable) tuple. `label` is a human-readable
    description used in dry-run output and the batch plan; `runnable` is a
    zero-arg callable that performs the step. Order matters: for *.sh modules
    that share a directory with a `packages` (Debian) or `brewfile` (macOS)
    file, the per-module uninstall script runs FIRST (it cleans up the apt
    repo / signing keys / vendor dirs the install script added beyond the
    declarative file), and the declarative cleanup follows to remove the
    shared dependencies the install script asked for via the packages /
    brewfile entries.
    """
    basename = os.path.basename(script_path)
    script_dir = os.path.dirname(script_path)
    steps = []

    def _brewfile_step(path):
        return ("brew bundle cleanup --force",
                lambda: subprocess.run("brew bundle cleanup --file brewfile --force", shell=True))

    def _packages_step(path):
        utilities = os.path.join(smu_home_dir, "dotfiles/utilities/utilities.sh")
        return ("apt_remove_from_file packages",
                lambda: subprocess.run(
                    f"bash -c 'source {utilities} && apt_remove_from_file packages'",
                    shell=True,
                ))

    if basename == "brewfile":
        if not macOS:
            return None  # signals "off-OS, skip"
        steps.append(_brewfile_step(script_path))
        return steps

    if basename == "packages":
        if not debian:
            return None
        steps.append(_packages_step(script_path))
        return steps

    # *.sh module: require an explicit sibling uninstaller, then chain the
    # declarative inverse for any sibling packages/brewfile in the same dir.
    name = _module_basename(script_path)
    uninstaller = os.path.join(script_dir, f"{name}.uninstall.sh")
    if not os.path.exists(uninstaller):
        return []  # signals "no automatic inverse available"

    steps.append((
        f"{name}.uninstall.sh",
        lambda: subprocess.run(f"bash -c 'source {uninstaller}'", shell=True),
    ))

    sibling_packages = os.path.join(script_dir, "packages")
    sibling_brewfile = os.path.join(script_dir, "brewfile")
    if debian and os.path.exists(sibling_packages):
        steps.append(_packages_step(sibling_packages))
    if macOS and os.path.exists(sibling_brewfile):
        steps.append(_brewfile_step(sibling_brewfile))

    return steps


def uninstall_module(module_name, dry_run=False):
    """Inverse of provision_module.

    Returns True on success/dry-run plan, False if skipped (no automatic
    inverse available — e.g. a *.sh module without a <name>.uninstall.sh).
    """
    script_path = get_module_path(module_name)
    if not script_path:
        warn(f"'{module_name}' does not seem to exist, skipping.")
        return False

    if subprocess.call("command -v bash &> /dev/null", shell=True) != 0:
        warn("'bash' is not installed, skipping.")
        return False

    steps = _uninstall_steps(script_path)
    if steps is None:
        warn(f"'{script_path}' is not supported on this OS, skipping.")
        return False
    if not steps:
        name = _module_basename(script_path)
        warn(f"'{module_name}' has no {name}.uninstall.sh — skipping. Manual cleanup required.")
        return False

    os.chdir(os.path.dirname(script_path))

    for label, runnable in steps:
        if dry_run:
            action(f"[dry-run] {label}\n")
            continue
        action(f"Running: {label}\n")
        runnable()

    return True


def status_modules(search=None, show_all=False, verbose=False):
    """Print an installed/missing report grouped by bucket."""
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

    counts = {"installed": 0, "missing": 0, "partial": 0, "unknown": 0}
    glyphs = {
        "installed": (COL_GREEN, "[OK]"),
        "missing":   (COL_RED,   "[--]"),
        "partial":   (COL_YELLOW,"[~~]"),
        "unknown":   (COL_YELLOW,"[??]"),
    }

    for bucket in sorted(visible.keys()):
        mods = visible[bucket]
        print(f"{BOLD}{bucket}/{NORMAL}")
        max_name = max(len(name) for name, _ in mods)
        max_kind = max(len(kind) for _, kind in mods)
        for name, kind in mods:
            state, detail = module_status(name)
            counts[state] += 1
            color, glyph = glyphs[state]
            tag = f"[{kind}]".ljust(max_kind + 2)
            tail = f"  {COL_YELLOW}({detail}){COL_RESET}" if verbose and detail else ""
            print(f"  {name.ljust(max_name)}  {tag}  {color}{glyph} {state}{COL_RESET}{tail}")
        print()

    total = sum(counts.values())
    summary = (
        f"{COL_GREEN}{counts['installed']} installed{COL_RESET}, "
        f"{COL_RED}{counts['missing']} missing{COL_RESET}, "
        f"{COL_YELLOW}{counts['partial']} partial{COL_RESET}, "
        f"{COL_YELLOW}{counts['unknown']} unknown{COL_RESET}"
    )
    scope = ""
    if not show_all and current:
        scope = f" (showing '{current}' + 'universal'; use --all to include other OS buckets)"
    print(f"{BOLD}{total}{NORMAL} module(s){scope}: {summary}")


def uninstall_modules_batch(modules, dry_run=False, no_confirm=False):
    """Uninstall a list of modules and print a per-module summary."""
    if not modules:
        return

    # Resolve up-front to surface modules with no automatic inverse
    plan = []
    unsupported = []
    for module in modules:
        script_path = get_module_path(module)
        if not script_path:
            unsupported.append((module, "module not found"))
            continue
        steps = _uninstall_steps(script_path)
        if steps is None:
            unsupported.append((module, "not supported on this OS"))
            continue
        if not steps:
            name = _module_basename(script_path)
            unsupported.append((module, f"no {name}.uninstall.sh"))
            continue
        labels = [label for label, _ in steps]
        plan.append((module, labels))

    print()
    if plan:
        print("The following will be uninstalled:")
        for module, labels in plan:
            chain = " ; ".join(labels)
            print(f"  {COL_GREEN}-{COL_RESET} {BOLD}{module}{NORMAL}  ({chain})")
        print()
    if unsupported:
        print(f"{COL_YELLOW}Cannot auto-uninstall:{COL_RESET}")
        for module, reason in unsupported:
            print(f"  {COL_YELLOW}!{COL_RESET} {BOLD}{module}{NORMAL}  ({reason})")
        print()

    if not plan:
        warn("Nothing to uninstall.")
        return

    if dry_run:
        warn("Dry run — no changes will be made.")
    elif not no_confirm:
        try:
            answer = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            warn("Aborted.")
            return

    uninstalled = set()
    errored = set()
    skipped = set()

    for module, _labels in plan:
        try:
            ok = uninstall_module(module, dry_run=dry_run)
            if ok:
                uninstalled.add(module)
            else:
                skipped.add(module)
        except subprocess.CalledProcessError as e:
            errored.add(module)
            print(f"Failed to uninstall '{module}': {e}", file=sys.stderr)

    if uninstalled:
        verb = "would be uninstalled" if dry_run else "uninstalled"
        print(f"\nModules {verb}:")
        for module in uninstalled:
            success(f"  - '{BOLD}{module}{NORMAL}'")

    if errored:
        print("\nModules that failed to uninstall:")
        for module in errored:
            warn(f"  - '{BOLD}{module}{NORMAL}'")

    if skipped:
        print("\nModules that were skipped:")
        for module in skipped:
            warn(f"  - '{BOLD}{module}{NORMAL}'")


def provision_modules_batch(modules):
    """Provision a list of modules and print a per-module summary."""
    if not modules:
        return

    warn("This script will execute the following modules:")
    for module in modules:
        print(f"  - '{BOLD}{module}{NORMAL}'\n")

    warn(f"'{BOLD}set-me-up{NORMAL}' may overwrite existing files in your home directory.")

    provisioned = set()
    errored = set()
    skipped = set()

    for module in modules:
        try:
            was_provisioned = provision_module(module)
            if was_provisioned:
                provisioned.add(module)
            else:
                skipped.add(module)
        except subprocess.CalledProcessError as e:
            errored.add(module)
            print(f"Failed to provision '{module}': {e}", file=sys.stderr)

    if provisioned:
        print("Modules that were successfully provisioned:")
        for module in provisioned:
            success(f"  - '{BOLD}{module}{NORMAL}'\n")

    if errored:
        print("Modules that failed to provision:")
        for module in errored:
            warn(f"  - '{BOLD}{module}{NORMAL}'\n")

    if skipped:
        print("Modules that were skipped:")
        for module in skipped:
            warn(f"  - '{BOLD}{module}{NORMAL}'\n")

    warn("It is recommended to restart your computer to ensure all updates take effect.")
    success(f"Completed running '{BOLD}set-me-up{NORMAL}'.")


def main():
    parser = argparse.ArgumentParser(description="set-me-up installer")
    parser.add_argument("-v", "--version", action="version", version="set-me-up 1.0.0")
    parser.add_argument("-du", "--debian-update", action="store_true", help="Update Debian-based system")
    parser.add_argument("-mu", "--macos-update", action="store_true", help="Update MacOS system")
    parser.add_argument("-au", "--arch-update", action="store_true", help="Update Arch-based system")
    parser.add_argument("-b", "--base", action="store_true", help="Run base module")
    parser.add_argument("-nb", "--no-base", action="store_true", help="Do not run base module")
    parser.add_argument("-su", "--self-update", action="store_true", help="Update set-me-up")
    parser.add_argument("-us", "--update-submodules", action="store_true", help="Update set-me-up submodules")
    parser.add_argument("-p", "--provision", action="store_true", help="Provision given modules")
    parser.add_argument("-m", "--modules", nargs='*', default=[], help="Modules to provision")
    parser.add_argument("--lsrc", action="store_true", help="List files that will be symlinked via 'rcm' into your home directory")
    parser.add_argument("--rcup", action="store_true", help="Symlink files via 'rcm' into your home directory")
    parser.add_argument("--rcdn", action="store_true", help="Remove files that were symlinked via 'rcup")
    parser.add_argument("-cbd", "--create-boot-disk", action="store_true", help="Creates a MacOS boot disk")
    parser.add_argument("-l", "--list-modules", action="store_true", help="List available modules grouped by OS bucket")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactively pick modules with fzf (SPACE to toggle, ENTER to run)")
    parser.add_argument("-st", "--status", action="store_true", help="Show installed/missing status for visible modules")
    parser.add_argument("-u", "--uninstall", action="store_true", help="Uninstall the given modules")
    parser.add_argument("-iu", "--uninstall-interactive", action="store_true", help="Pick modules to uninstall via fzf")
    parser.add_argument("--dry-run", action="store_true", help="With --uninstall: print the plan, do nothing")
    parser.add_argument("-y", "--yes", action="store_true", help="With --uninstall: skip the confirmation prompt")
    parser.add_argument("-V", "--verbose", action="store_true", help="With --status: show per-entry detail")
    parser.add_argument("--search", metavar="QUERY", help="Filter --list-modules / --status / --interactive by substring (case-insensitive)")
    parser.add_argument("--all", action="store_true", help="With --list-modules / --status / --interactive, include modules for other OS buckets")

    args = parser.parse_args()

    # --------------------------------------------------------------------------------------

    # Check if 'rcm' is installed, because it is required for this script to work.
    # 'rcm' is a dotfile management tool that is used to symlink files into the home directory.
    # see: https://github.com/thoughtbot/rcm
    rcm = subprocess.call("command -v rcup &> /dev/null", shell=True) == 0

    command = ""

    if args.lsrc:
        command = "lsrc"
    elif args.rcup:
        command = "rcup"
    elif args.rcdn:
        command = "rcdn"

    # If 'rcm' is not installed, and the user is trying to run 'rcup', 'rcdn', or 'lsrc',
    if not rcm and (args.lsrc or args.rcup or args.rcdn):
        die(f"'rcm' is not installed. Please run the '{BOLD}base{NORMAL}' module prior to executing '{command}'.")

    # --------------------------------------------------------------------------------------

    if args.list_modules:
        list_modules(search=args.search, show_all=args.all)
        return

    if args.status:
        status_modules(search=args.search, show_all=args.all, verbose=args.verbose)
        return

    if args.uninstall_interactive:
        modules = interactive_select_modules(search=args.search, show_all=args.all)
        if not modules:
            return
        uninstall_modules_batch(modules, dry_run=args.dry_run, no_confirm=args.yes)
        return

    if args.uninstall:
        modules = list(args.modules)
        if not modules:
            die("--uninstall requires -m <module> [<module> ...] (or use --uninstall-interactive).")
        uninstall_modules_batch(modules, dry_run=args.dry_run, no_confirm=args.yes)
        return

    if args.lsrc:
        list_symlinks()
    elif args.rcup:
        symlink()
    elif args.rcdn:
        remove_symlinks()
    elif args.debian_update:
        if not debian:
            die("This module is only supported on Debian-based systems.")

        update()
    elif args.macos_update:
        if not macOS:
            die("This module is only supported on MacOS.")

        update()
    elif args.arch_update:
        if not arch:
            die("This module is only supported on Arch-based systems.")

        update()
    elif args.create_boot_disk:
        if not macOS:
            die("This module is only supported on MacOS.")

        create_boot_disk()
    elif args.self_update:
        self_update()
    elif args.update_submodules:
        update_submodules()
    elif args.base:
        provision_module("base")
    elif args.provision:
        modules = list(args.modules)

        # If the 'base' module is not in the module list, add it to the beginning.
        if args.base and "base" not in modules:
            modules.insert(0, "base")

        # If 'no-base' is specified, remove the 'base' module from the module list.
        if args.no_base and "base" in modules:
            modules.remove("base")

        provision_modules_batch(modules)
    elif args.interactive:
        modules = interactive_select_modules(search=args.search, show_all=args.all)
        if not modules:
            return

        if args.base and "base" not in modules:
            modules.insert(0, "base")
        if args.no_base and "base" in modules:
            modules.remove("base")

        provision_modules_batch(modules)
    elif args.modules:
        # Handle the case where modules are specified without --provision
        print("Modules specified, but --provision flag is not set.", file=sys.stderr)
    else:
        # If no modules are specified, show help
        parser.print_help()


if __name__ == "__main__":
    main()
