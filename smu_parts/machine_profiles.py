from .core import *


MACHINE_PROFILES = {
    "minimal": {
        "modules": ("base",),
        "adapter": "rcm",
        "submodule_scope": "platform",
        "safety": {"allow_network": True, "allow_sudo": False, "secrets": "deny"},
    },
    "ci": {
        "modules": ("server/headless",),
        "adapter": "rcm",
        "submodule_scope": "platform",
        "safety": {"allow_network": True, "allow_sudo": True, "secrets": "deny"},
    },
    "vps": {
        "modules": ("server/headless",),
        "adapter": "hybrid",
        "submodule_scope": "platform",
        "safety": {"allow_network": True, "allow_sudo": True, "secrets": "deny"},
    },
    "agent-host": {
        "modules": ("server/headless", "git", "tmux"),
        "adapter": "hybrid",
        "submodule_scope": "platform",
        "safety": {"allow_network": True, "allow_sudo": True, "secrets": "deny"},
    },
    "laptop": {
        "modules": ("base",),
        "adapter": "hybrid",
        "submodule_scope": "all",
        "safety": {"allow_network": True, "allow_sudo": True, "secrets": "warn"},
    },
    "workstation": {
        "modules": ("base", "development-tools"),
        "adapter": "hybrid",
        "submodule_scope": "all",
        "safety": {"allow_network": True, "allow_sudo": True, "secrets": "warn"},
    },
}


def supported_machine_profiles():
    return tuple(sorted(MACHINE_PROFILES.keys()))


def machine_profile(name):
    if name not in MACHINE_PROFILES:
        die(f"Unknown machine profile '{name}'. Valid values: {', '.join(supported_machine_profiles())}.")
    return {**MACHINE_PROFILES[name], "id": name}


def machine_profile_modules(name):
    return tuple(machine_profile(name)["modules"])


def machine_profile_command(argv):
    json_output = "--json" in argv
    if argv and argv[0] == "list":
        payload = {"profiles": [machine_profile(name) for name in supported_machine_profiles()]}
        if json_output:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for profile in payload["profiles"]:
                print(f"{profile['id']}\t{profile['adapter']}\t{','.join(profile['modules'])}")
        return 0
    if argv and argv[0] == "show" and len(argv) > 1:
        payload = machine_profile(argv[1])
        print(json.dumps(payload, indent=2, sort_keys=True) if json_output else "\n".join(
            f"{key}\t{value}" for key, value in payload.items()
        ))
        return 0
    die("Usage: smu machine-profile [list|show <profile>] [--json]")


__all__ = [name for name in globals() if not name.startswith("__")]
