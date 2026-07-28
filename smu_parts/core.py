#!/usr/bin/env python3

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import os
import shlex
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
import smu_contract

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
resolved_profile_path = os.path.join(config_dir, "resolved.env")
theme_override_path = os.path.join(config_dir, "theme.toml")
prompt_override_path = os.path.join(config_dir, "prompt.toml")
preset_override_path = os.path.join(config_dir, "preset.toml")
catalogs_path = os.path.join(config_dir, "catalogs")
theme_catalog_path = os.path.join(catalogs_path, "themes")
prompt_catalog_path = os.path.join(catalogs_path, "prompt-profiles")
preset_catalog_path = os.path.join(catalogs_path, "presets")
catalog_registries_path = os.path.join(config_dir, "registries.toml")
catalog_registry_lock_path = os.path.join(config_dir, "registry.lock")
catalog_cache_path = os.path.join(os.path.expanduser("~"), ".cache", "set-me-up", "catalogs")
adapter_state_path = os.path.join(config_dir, "adapters")
adapter_manifest_env_path = os.path.join(adapter_state_path, "manifest.env")
adapter_manifest_json_path = os.path.join(adapter_state_path, "manifest.json")

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
ADAPTER_MODES = smu_contract.ADAPTER_MODES

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
    return smu_contract.read_manifest(path)

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
    return smu_contract.merge_manifest(parent, child)

def _resolve_manifest_inheritance(manifests):
    return smu_contract.resolve_inheritance(manifests)

def _merge_catalog_manifests(builtins, user_manifests):
    return smu_contract.merge_catalog_manifests(builtins, user_manifests)

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
    return smu_contract.duplicate_ids(entries)

def _valid_catalog_id(manifest_id):
    return smu_contract.valid_id(manifest_id)

def _display_name(manifest_id):
    return manifest_id.replace("-", " ").title()

def _write_catalog_file(path, content, force=False):
    if os.path.exists(path) and not force:
        die(f"Catalog manifest already exists: {path}. Use --force to overwrite.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    success(f"Wrote catalog manifest to {path}")

def _schema_version_line():
    return f"{smu_contract.SCHEMA_VERSION_KEY} = {smu_contract.SUPPORTED_SCHEMA_VERSION}\n"

def _init_theme(manifest_id, parent=None, force=False):
    if not _valid_catalog_id(manifest_id):
        die(f"Theme id must be kebab-case: {manifest_id}")
    parent = parent or current_theme()
    path = os.path.join(theme_catalog_path, f"{manifest_id}.toml")
    content = (
        _schema_version_line() +
        f'id = "{manifest_id}"\n'
        f'extends = "{parent}"\n'
        f'name = "{_display_name(manifest_id)}"\n'
    )
    _write_catalog_file(path, content, force=force)

def _init_prompt(manifest_id, parent=None, force=False):
    if not _valid_catalog_id(manifest_id):
        die(f"Prompt id must be kebab-case: {manifest_id}")
    parent = parent or current_prompt()
    path = os.path.join(prompt_catalog_path, f"{manifest_id}.toml")
    content = (
        _schema_version_line() +
        f'id = "{manifest_id}"\n'
        f'extends = "{parent}"\n'
        f'name = "{_display_name(manifest_id)}"\n'
        f'description = "Custom prompt profile."\n'
    )
    _write_catalog_file(path, content, force=force)

def _init_preset(manifest_id, force=False):
    if not _valid_catalog_id(manifest_id):
        die(f"Preset id must be kebab-case: {manifest_id}")
    path = os.path.join(preset_catalog_path, f"{manifest_id}.toml")
    content = (
        _schema_version_line() +
        f'id = "{manifest_id}"\n'
        f'name = "{_display_name(manifest_id)}"\n'
        f'description = "Custom set-me-up preset."\n'
        f'theme = "{current_theme()}"\n'
        f'prompt = "{current_prompt()}"\n'
    )
    _write_catalog_file(path, content, force=force)

def _init_adapter(manifest_id, force=False):
    if not _valid_catalog_id(manifest_id):
        die(f"Adapter id must be kebab-case: {manifest_id}")

    os.makedirs(os.path.join(prompt_catalog_path, "files"), exist_ok=True)
    manifest_path = os.path.join(prompt_catalog_path, f"{manifest_id}.toml")
    source_files = {
        "bash": os.path.join(prompt_catalog_path, "files", f"{manifest_id}.bash"),
        "zsh": os.path.join(prompt_catalog_path, "files", f"{manifest_id}.zsh"),
        "fish": os.path.join(prompt_catalog_path, "files", f"{manifest_id}.fish"),
        "nushell": os.path.join(prompt_catalog_path, "files", f"{manifest_id}.nu"),
    }
    content = (
        _schema_version_line() +
        f'id = "{manifest_id}"\n'
        f'name = "{_display_name(manifest_id)}"\n'
        f'description = "Custom materialized shell prompt."\n'
        'engine = "shell"\n'
        'theme_aware = true\n\n'
        '[shell]\n'
        'mode = "native"\n\n'
        '[adapters]\n'
        f'bash = "prompts/{manifest_id}.bash"\n'
        f'zsh = "prompts/{manifest_id}.zsh"\n'
        f'fish = "prompts/{manifest_id}.fish"\n'
        f'nushell = "prompts/{manifest_id}.nu"\n\n'
        '[adapter_sources]\n'
        f'bash = "files/{manifest_id}.bash"\n'
        f'zsh = "files/{manifest_id}.zsh"\n'
        f'fish = "files/{manifest_id}.fish"\n'
        f'nushell = "files/{manifest_id}.nu"\n\n'
        '[adapter_targets]\n'
        f'bash = "~/.config/bash/prompts/{manifest_id}.bash"\n'
        f'zsh = "~/.config/zsh/prompts/{manifest_id}.zsh"\n'
        f'fish = "~/.config/fish/prompts/{manifest_id}.fish"\n'
        f'nushell = "~/.config/nushell/prompts/{manifest_id}.nu"\n\n'
        '[adapter_modes]\n'
        'bash = "copy"\n'
        'zsh = "copy"\n'
        'fish = "copy"\n'
        'nushell = "copy"\n'
    )
    _write_catalog_file(manifest_path, content, force=force)

    stubs = {
        "bash": "#!/usr/bin/env bash\nexport PS1='\\u@\\h:\\w\\$ '\n",
        "zsh": "PROMPT='%n@%m:%~%# '\n",
        "fish": "function fish_prompt\n    printf '%s@%s:%s> ' (whoami) (hostname -s) (prompt_pwd)\nend\n",
        "nushell": "$env.PROMPT_COMMAND = { || $\"(whoami)@(hostname):(pwd)> \" }\n",
    }
    for shell, path in source_files.items():
        if os.path.exists(path) and not force:
            continue
        with open(path, "w") as f:
            f.write(stubs[shell])

