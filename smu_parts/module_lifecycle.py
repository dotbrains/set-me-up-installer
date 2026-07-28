from .core import *
from .module_discovery import *


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


def module_status_report(search=None, show_all=False, verbose=False):
    buckets = discover_modules()
    if not buckets:
        return []

    current = _current_os_bucket()
    report = []
    for bucket, mods in buckets.items():
        if not show_all and current and bucket not in (current, "universal"):
            continue
        if search:
            needle = search.lower()
            mods = [(name, kind) for name, kind in mods if needle in name.lower()]
        for name, kind in mods:
            state, detail = module_status(name)
            item = {"bucket": bucket, "name": name, "kind": kind, "state": state}
            if verbose and detail:
                item["detail"] = detail
            report.append(item)
    return report


def status_modules(search=None, show_all=False, verbose=False):
    """Print an installed/missing report grouped by bucket."""
    rows = module_status_report(search=search, show_all=show_all, verbose=verbose)
    if not rows:
        if not discover_modules():
            warn(f"No modules found in '{module_path}'.")
        elif search:
            warn(f"No modules match '{BOLD}{search}{NORMAL}'.")
        else:
            warn("No modules to display.")
        return

    visible = {}
    for row in rows:
        visible.setdefault(row["bucket"], []).append(row)

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
        max_name = max(len(row["name"]) for row in mods)
        max_kind = max(len(row["kind"]) for row in mods)
        for row in mods:
            name = row["name"]
            kind = row["kind"]
            state = row["state"]
            counts[state] += 1
            color, glyph = glyphs[state]
            tag = f"[{kind}]".ljust(max_kind + 2)
            detail = row.get("detail")
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

    if uninstalled and not dry_run:
        record_state_event("uninstall_modules", [
            {"module": module}
            for module in sorted(uninstalled)
        ])


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
    if provisioned:
        record_state_event("provision_modules", [
            {"module": module}
            for module in sorted(provisioned)
        ])


__all__ = [name for name in globals() if not name.startswith("__")]
