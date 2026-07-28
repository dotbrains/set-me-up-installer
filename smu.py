#!/usr/bin/env python3

import argparse
import importlib.util
import subprocess
import os
import shlex
import shutil
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
profile_path = os.path.join(os.path.expanduser("~"), ".config", "set-me-up", "profile.env")
config_dir = os.path.dirname(profile_path)
theme_override_path = os.path.join(config_dir, "theme.toml")
prompt_override_path = os.path.join(config_dir, "prompt.toml")
preset_override_path = os.path.join(config_dir, "preset.toml")
catalogs_path = os.path.join(config_dir, "catalogs")
theme_catalog_path = os.path.join(catalogs_path, "themes")
prompt_catalog_path = os.path.join(catalogs_path, "prompt-profiles")
preset_catalog_path = os.path.join(catalogs_path, "presets")

# 'set-me-up' installer scripts
installer_path = os.path.join(smu_home_dir, "set-me-up-installer")
installer_scripts_path = os.path.join(installer_path, "scripts")
prompt_profiles_path = os.path.join(os.path.dirname(__file__), "prompt-profiles")
preset_profiles_path = os.path.join(os.path.dirname(__file__), "presets")

# rcm configuration file path
rcrc = os.path.join(smu_home_dir, "dotfiles/rcrc")

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

SUPPORTED_THEMES = (
    "gruvbox",
    "nord",
    "catppuccin",
    "tokyo-night",
    "rose-pine",
    "dracula",
    "everforest",
    "solarized",
    "kanagawa",
)
SUPPORTED_PROMPTS = ("starship", "starship-minimal", "classic")
DEFAULT_THEME = "gruvbox"
DEFAULT_PROMPT = "starship"
DEFAULT_PRESET = "default"

def warn(message):
    print(f"{COL_YELLOW}[warning]{COL_RESET} {message}")

def success(message):
    print(f"{COL_GREEN}[success]{COL_RESET} {message}")

def action(message):
    print(f"{COL_YELLOW}[action]{COL_RESET} ⇒ {message}")

def die(message, exit_code=1):
    print(f"{COL_RED}[error]{COL_RESET} {message}", file=sys.stderr)
    sys.exit(exit_code)

def _parse_profile_line(line):
    if "=" not in line:
        return None, None
    key, value = line.strip().split("=", 1)
    key = key.strip()
    if key.startswith("export "):
        key = key[len("export "):].strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None, None
    return key, value

def _read_simple_toml(path):
    data = {}
    current_section = None
    if not os.path.exists(path):
        return data

    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                data.setdefault(current_section, {})
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if current_section:
                data[current_section][key] = value
            else:
                data[key] = value

    return data

def _load_theme_registry():
    registry_path = os.path.join(colorscheme_module_dir(), "scripts", "theme_registry.py")
    if not os.path.exists(registry_path):
        return None

    spec = importlib.util.spec_from_file_location("smu_theme_registry", registry_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _load_prompt_registry():
    registry_path = os.path.join(os.path.dirname(__file__), "scripts", "prompt_registry.py")
    if not os.path.exists(registry_path):
        return None

    spec = importlib.util.spec_from_file_location("smu_prompt_registry", registry_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _load_preset_registry():
    registry_path = os.path.join(os.path.dirname(__file__), "scripts", "preset_registry.py")
    if not os.path.exists(registry_path):
        return None

    spec = importlib.util.spec_from_file_location("smu_preset_registry", registry_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _merge_manifest(parent, child):
    merged = {}
    for key, value in parent.items():
        if isinstance(value, dict):
            merged[key] = dict(value)
        else:
            merged[key] = value

    for key, value in child.items():
        if key == "extends":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value

    return merged

def _resolve_manifest_inheritance(manifests):
    by_id = {
        manifest["id"]: manifest
        for manifest in manifests
        if manifest.get("id")
    }
    resolved = {}
    resolving = set()

    def resolve(manifest):
        manifest_id = manifest.get("id")
        parent_id = manifest.get("extends")
        if not manifest_id or not parent_id:
            return manifest
        if manifest_id in resolved:
            return resolved[manifest_id]
        if manifest_id in resolving:
            return manifest
        parent = by_id.get(parent_id)
        if not parent:
            return manifest
        resolving.add(manifest_id)
        resolved_parent = resolve(parent)
        resolving.remove(manifest_id)
        resolved_manifest = _merge_manifest(resolved_parent, manifest)
        resolved[manifest_id] = resolved_manifest
        return resolved_manifest

    return [resolve(manifest) for manifest in manifests]

def _merge_catalog_manifests(builtins, user_manifests):
    merged = list(builtins)
    seen = {entry.get("id") for entry in builtins if entry.get("id")}
    for manifest in user_manifests:
        manifest_id = manifest.get("id")
        if manifest_id and manifest_id not in seen:
            merged.append(manifest)
            seen.add(manifest_id)
    return _resolve_manifest_inheritance(merged)

def _read_manifest_dir(path, registry=None):
    if registry:
        return list(registry.manifests(path))

    manifests = []
    if os.path.isdir(path):
        for filename in sorted(os.listdir(path)):
            if not filename.endswith(".toml"):
                continue
            manifest = _read_simple_toml(os.path.join(path, filename))
            if manifest.get("id"):
                manifests.append(manifest)
    return manifests

def _catalog_duplicate_ids(entries):
    seen = set()
    duplicates = []
    for entry in entries:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        if entry_id in seen and entry_id not in duplicates:
            duplicates.append(entry_id)
        seen.add(entry_id)
    return duplicates

def prompt_profiles():
    registry = _load_prompt_registry()
    profiles = _merge_catalog_manifests(
        _read_manifest_dir(prompt_profiles_path, registry),
        _read_manifest_dir(prompt_catalog_path, registry),
    )

    if profiles:
        return profiles

    return [{"id": prompt} for prompt in SUPPORTED_PROMPTS]

def supported_prompts():
    return tuple(profile["id"] for profile in prompt_profiles())

def preset_profiles():
    registry = _load_preset_registry()
    presets = _merge_catalog_manifests(
        _read_manifest_dir(preset_profiles_path, registry),
        _read_manifest_dir(preset_catalog_path, registry),
    )

    if presets:
        return presets

    return [{"id": DEFAULT_PRESET, "theme": DEFAULT_THEME, "prompt": DEFAULT_PROMPT}]

def supported_presets():
    return tuple(preset["id"] for preset in preset_profiles())

def preset_by_id(preset):
    return {
        entry["id"]: entry
        for entry in preset_profiles()
        if entry.get("id")
    }.get(preset)

def colorscheme_module_dir():
    direct = os.path.join(module_path, "colorschemes")
    if os.path.isdir(direct):
        return direct

    local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules", "colorschemes"))
    if os.path.isdir(local):
        return local

    return direct

def theme_manifests_dir():
    return os.path.join(colorscheme_module_dir(), "themes")

def theme_manifests():
    registry = _load_theme_registry()
    return _merge_catalog_manifests(
        _read_manifest_dir(theme_manifests_dir(), registry),
        _read_manifest_dir(theme_catalog_path, registry),
    )

def supported_themes():
    manifests = theme_manifests()
    if manifests:
        return tuple(theme["id"] for theme in manifests)
    return SUPPORTED_THEMES

def read_profile():
    profile = {}
    if not os.path.exists(profile_path):
        return profile

    try:
        with open(profile_path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                key, value = _parse_profile_line(line)
                if key:
                    profile[key] = value
    except (IOError, OSError) as e:
        warn(f"Could not read profile '{profile_path}': {e}")

    return profile

def write_profile(profile):
    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
    preset = profile.get("SMU_PRESET", DEFAULT_PRESET)
    theme = profile.get("SMU_THEME", DEFAULT_THEME)
    prompt = profile.get("SMU_PROMPT", DEFAULT_PROMPT)

    with open(profile_path, "w") as f:
        f.write("# set-me-up profile\n")
        f.write(f"export SMU_PRESET=\"{preset}\"\n")
        f.write(f"export SMU_THEME=\"{theme}\"\n")
        f.write(f"export SMU_PROMPT=\"{prompt}\"\n")

def _read_override_choice(path, keys):
    data = _read_simple_toml(path)
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None

def current_preset():
    return (
        os.getenv("SMU_PRESET")
        or _read_override_choice(preset_override_path, ("preset", "id"))
        or read_profile().get("SMU_PRESET", DEFAULT_PRESET)
    )

def current_theme():
    return (
        os.getenv("SMU_THEME")
        or _read_override_choice(theme_override_path, ("theme", "id"))
        or read_profile().get("SMU_THEME", DEFAULT_THEME)
    )

def current_prompt():
    return (
        os.getenv("SMU_PROMPT")
        or _read_override_choice(prompt_override_path, ("prompt", "id"))
        or read_profile().get("SMU_PROMPT", DEFAULT_PROMPT)
    )

def set_preset(preset):
    entry = preset_by_id(preset)
    if not entry:
        die(f"Unknown preset '{preset}'. Valid values: {', '.join(supported_presets())}")

    theme = entry.get("theme")
    prompt = entry.get("prompt")
    if theme not in supported_themes():
        die(f"Preset '{preset}' references unknown theme '{theme}'.")
    if prompt not in supported_prompts():
        die(f"Preset '{preset}' references unknown prompt '{prompt}'.")

    profile = read_profile()
    profile["SMU_PRESET"] = preset
    profile["SMU_THEME"] = theme
    profile["SMU_PROMPT"] = prompt
    write_profile(profile)
    success(f"Saved preset={preset}, theme={theme}, prompt={prompt} to {profile_path}")

def set_profile_value(key, value, allowed):
    if value not in allowed:
        die(f"Unknown {key.lower().replace('smu_', '')} '{value}'. Valid values: {', '.join(allowed)}")

    profile = read_profile()
    profile[key] = value
    profile.setdefault("SMU_PRESET", current_preset())
    profile.setdefault("SMU_THEME", current_theme())
    profile.setdefault("SMU_PROMPT", current_prompt())
    write_profile(profile)
    success(f"Saved {key}={value} to {profile_path}")

def print_profile():
    print(f"Profile: {profile_path}")
    print(f"Preset: {BOLD}{current_preset()}{NORMAL}")
    print(f"Theme:  {BOLD}{current_theme()}{NORMAL}")
    print(f"Prompt: {BOLD}{current_prompt()}{NORMAL}")

def handle_profile_command(argv):
    if not argv:
        print_profile()
        return

    command = argv[0]
    if command in ("show", "current"):
        print_profile()
        return

    die(f"Unknown profile command '{command}'. Use: smu profile [show]")

def handle_theme_command(argv):
    if not argv or argv[0] in ("current", "show"):
        print(current_theme())
        return

    command = argv[0]
    if command == "list":
        for theme in supported_themes():
            marker = "*" if theme == current_theme() else " "
            print(f"{marker} {theme}")
        return

    if command == "set":
        if len(argv) < 2:
            die("Usage: smu theme set <theme> [--apply]")
        theme = argv[1]
        apply_after = "--apply" in argv[2:]
        set_profile_value("SMU_THEME", theme, supported_themes())
        if apply_after:
            provision_module("colorschemes")
        return

    if command == "doctor":
        theme = argv[1] if len(argv) > 1 else current_theme()
        raise SystemExit(theme_doctor(theme))

    if command == "apply":
        provision_module("colorschemes")
        return

    die("Usage: smu theme [list|current|set <theme> [--apply]|apply]")

def handle_prompt_command(argv):
    if not argv or argv[0] in ("current", "show"):
        print(current_prompt())
        return

    command = argv[0]
    if command == "list":
        for profile in prompt_profiles():
            prompt = profile["id"]
            marker = "*" if prompt == current_prompt() else " "
            description = profile.get("description")
            if description:
                print(f"{marker} {prompt} - {description}")
            else:
                print(f"{marker} {prompt}")
        return

    if command == "set":
        if len(argv) < 2:
            die("Usage: smu prompt set <prompt>")
        set_profile_value("SMU_PROMPT", argv[1], supported_prompts())
        return

    if command == "doctor":
        prompt = argv[1] if len(argv) > 1 else current_prompt()
        raise SystemExit(prompt_doctor(prompt))

    die("Usage: smu prompt [list|current|set <prompt>|doctor [prompt]]")

def handle_preset_command(argv):
    if not argv or argv[0] in ("current", "show"):
        print(current_preset())
        return

    command = argv[0]
    if command == "list":
        for preset in preset_profiles():
            preset_id = preset["id"]
            marker = "*" if preset_id == current_preset() else " "
            description = preset.get("description")
            bundle = f"{preset.get('theme', '?')} + {preset.get('prompt', '?')}"
            if description:
                print(f"{marker} {preset_id} - {bundle} - {description}")
            else:
                print(f"{marker} {preset_id} - {bundle}")
        return

    if command == "set":
        if len(argv) < 2:
            die("Usage: smu preset set <preset> [--apply]")
        preset = argv[1]
        apply_after = "--apply" in argv[2:]
        set_preset(preset)
        if apply_after:
            provision_module("colorschemes")
        return

    if command == "doctor":
        preset = argv[1] if len(argv) > 1 else current_preset()
        raise SystemExit(preset_doctor(preset))

    die("Usage: smu preset [list|current|set <preset> [--apply]|doctor [preset]]")

def handle_catalog_command(argv):
    if not argv or argv[0] == "doctor":
        raise SystemExit(catalog_doctor())
    if argv[0] == "path":
        print(catalogs_path)
        return
    die("Usage: smu catalog [doctor|path]")

def _catalog_layer_errors(label, builtin_dir, user_dir, registry=None):
    errors = []
    builtin = _read_manifest_dir(builtin_dir, registry)
    user = _read_manifest_dir(user_dir, registry)

    for entry_id in _catalog_duplicate_ids(builtin):
        errors.append(f"{label}: duplicate built-in id {entry_id}")
    for entry_id in _catalog_duplicate_ids(user):
        errors.append(f"{label}: duplicate user catalog id {entry_id}")

    builtin_ids = {entry.get("id") for entry in builtin if entry.get("id")}
    for entry in user:
        entry_id = entry.get("id")
        if entry_id in builtin_ids:
            errors.append(f"{label}: user catalog id {entry_id} conflicts with built-in manifest")
        parent = entry.get("extends")
        all_ids = builtin_ids | {candidate.get("id") for candidate in user if candidate.get("id")}
        if parent and parent not in all_ids:
            errors.append(f"{label}: {entry_id} extends unknown manifest {parent}")

    return errors

def catalog_doctor():
    errors = []
    errors.extend(_catalog_layer_errors(
        "themes",
        theme_manifests_dir(),
        theme_catalog_path,
        _load_theme_registry(),
    ))
    errors.extend(_catalog_layer_errors(
        "prompts",
        prompt_profiles_path,
        prompt_catalog_path,
        _load_prompt_registry(),
    ))
    errors.extend(_catalog_layer_errors(
        "presets",
        preset_profiles_path,
        preset_catalog_path,
        _load_preset_registry(),
    ))

    prompt_registry = _load_prompt_registry()
    if prompt_registry:
        for profile in prompt_profiles():
            errors.extend(
                f"prompts: {error}"
                for error in prompt_registry.validate_profile(profile)
            )

    preset_registry = _load_preset_registry()
    if preset_registry:
        for preset in preset_profiles():
            errors.extend(
                f"presets: {error}"
                for error in preset_registry.validate_preset(
                    preset,
                    supported_themes(),
                    supported_prompts(),
                )
            )

    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1

    print(f"{COL_GREEN}OK{COL_RESET}   catalogs {catalogs_path}")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_themes())} theme(s)")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_prompts())} prompt profile(s)")
    print(f"{COL_GREEN}OK{COL_RESET}   {len(supported_presets())} preset(s)")
    return 0

def preset_doctor(preset):
    entry = preset_by_id(preset)
    if not entry:
        warn(f"Unknown preset '{preset}'.")
        return 1

    registry = _load_preset_registry()
    errors = []
    if registry:
        errors.extend(registry.validate_preset(entry, supported_themes(), supported_prompts()))

    failed = False
    for error in errors:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} {error}")

    theme = entry.get("theme")
    prompt = entry.get("prompt")
    if theme in supported_themes():
        print(f"{COL_GREEN}OK{COL_RESET}   theme {theme}")
    else:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} preset {preset} references unknown theme {theme}")

    if prompt in supported_prompts():
        print(f"{COL_GREEN}OK{COL_RESET}   prompt {prompt}")
    else:
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} preset {preset} references unknown prompt {prompt}")

    return 1 if failed else 0

def doctor():
    failed = False
    preset = current_preset()
    theme = current_theme()
    prompt = current_prompt()

    print(f"{BOLD}Preset:{NORMAL} {preset}")
    failed = preset_doctor(preset) != 0 or failed
    print(f"\n{BOLD}Catalogs:{NORMAL} {catalogs_path}")
    failed = catalog_doctor() != 0 or failed
    print(f"\n{BOLD}Theme:{NORMAL} {theme}")
    failed = theme_doctor(theme) != 0 or failed
    print(f"\n{BOLD}Prompt:{NORMAL} {prompt}")
    failed = prompt_doctor(prompt) != 0 or failed

    return 1 if failed else 0

def prompt_doctor(prompt):
    profiles = {entry["id"]: entry for entry in prompt_profiles() if entry.get("id")}
    if prompt not in profiles:
        warn(f"Unknown prompt profile '{prompt}'.")
        return 1

    registry = _load_prompt_registry()
    if not registry:
        warn("Prompt registry is not available.")
        return 1

    profile = profiles[prompt]
    failed = False
    for error in registry.validate_profile(profile):
        failed = True
        print(f"{COL_RED}FAIL{COL_RESET} {error}")

    set_me_up_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for label, path in registry.adapter_paths(set_me_up_root, profile):
        if os.path.exists(path):
            print(f"{COL_GREEN}OK{COL_RESET}   {label}")
        else:
            failed = True
            print(f"{COL_RED}MISS{COL_RESET} {label}: {path}")

    return 1 if failed else 0

def theme_doctor(theme):
    themes = {entry["id"]: entry for entry in theme_manifests()}
    if theme not in supported_themes():
        warn(f"Unknown theme '{theme}'.")
        return 1

    colorschemes = colorscheme_module_dir()
    set_me_up_root = os.path.abspath(os.path.join(colorschemes, "..", ".."))
    theme_entry = themes.get(theme, {"id": theme})
    registry = _load_theme_registry()

    if registry:
        checks = registry.adapter_paths(
            colorschemes,
            theme_entry,
            aggregate_root=set_me_up_root,
        )
    else:
        checks = [
            ("colorscheme manifest", os.path.join(colorschemes, "themes", f"{theme}.toml")),
            ("universal script", os.path.join(colorschemes, "universal", f"{theme}.sh")),
            ("macos script", os.path.join(colorschemes, "macos", f"{theme}.sh")),
            ("arch script", os.path.join(colorschemes, "arch", f"{theme}.sh")),
        ]

    failed = False
    for label, path in checks:
        if os.path.exists(path):
            print(f"{COL_GREEN}OK{COL_RESET}   {label}")
        else:
            failed = True
            print(f"{COL_RED}MISS{COL_RESET} {label}: {path}")

    return 1 if failed else 0

def list_symlinks():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"lsrc -v -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def symlink():
    os.environ["RCRC"] = rcrc

    subprocess.run(f"rcup -v -f -d {os.path.join(smu_home_dir, 'dotfiles')}", shell=True)

def remove_symlinks():
    os.environ["RCRC"] = rcrc

    dotfiles_dir = os.path.join(smu_home_dir, "dotfiles")
    quoted_dotfiles_dir = shlex.quote(dotfiles_dir)
    managed_targets = []

    if os.path.exists(dotfiles_dir):
        # Capture the exact destinations before rcdn removes anything. This keeps
        # cleanup proportional to managed links instead of scanning home.
        result = subprocess.run(
            f"lsrc -v {quoted_dotfiles_dir}",
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                if '->' not in line:
                    continue

                target = line.split('->', 1)[0].strip()
                if target:
                    managed_targets.append(target)

    subprocess.run(f"rcdn -v -d {quoted_dotfiles_dir}", shell=True)

    for target in managed_targets:
        if os.path.islink(target):
            os.unlink(target)
        elif os.path.isdir(target):
            try:
                os.rmdir(target)
            except OSError:
                pass

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

    direct_module_dir = os.path.join(module_path, module_name)
    direct_script_path = os.path.join(direct_module_dir, f"{module_name}.sh")
    direct_brewfile_path = os.path.join(direct_module_dir, "brewfile")
    direct_packages_path = os.path.join(direct_module_dir, "packages")

    if os.path.exists(direct_script_path):
        return direct_script_path
    if os.path.exists(direct_brewfile_path):
        return direct_brewfile_path
    if os.path.exists(direct_packages_path):
        return direct_packages_path

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
    if len(sys.argv) > 1:
        command = sys.argv[1]
        command_args = sys.argv[2:]
        if command == "profile":
            handle_profile_command(command_args)
            return
        if command == "theme":
            handle_theme_command(command_args)
            return
        if command == "prompt":
            handle_prompt_command(command_args)
            return
        if command == "preset":
            handle_preset_command(command_args)
            return
        if command == "catalog":
            handle_catalog_command(command_args)
            return
        if command == "doctor":
            raise SystemExit(doctor())

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
    parser.add_argument("--theme", choices=supported_themes(), help="Save the selected set-me-up theme before provisioning")
    parser.add_argument("--prompt", choices=supported_prompts(), help="Save the selected set-me-up prompt profile before provisioning")
    parser.add_argument("--preset", choices=supported_presets(), help="Save the selected set-me-up preset before provisioning")

    args = parser.parse_args()

    if args.preset:
        set_preset(args.preset)
    if args.theme:
        set_profile_value("SMU_THEME", args.theme, supported_themes())
    if args.prompt:
        set_profile_value("SMU_PROMPT", args.prompt, supported_prompts())

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
