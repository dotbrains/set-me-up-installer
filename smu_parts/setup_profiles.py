from .core import *
from .module_lifecycle import provision_modules_batch


SETUP_PROFILES = {
    "vps": {
        "name": "Headless VPS",
        "description": "Provision a small Ubuntu/Debian server baseline.",
        "modules": ("server/headless",),
        "debian_only": True,
    },
}


def supported_setup_profiles():
    return tuple(sorted(SETUP_PROFILES.keys()))


def setup_profile_modules(profile):
    return tuple(SETUP_PROFILES[profile]["modules"])


def run_setup_profile(profile):
    if profile not in SETUP_PROFILES:
        die(f"Unknown setup profile '{profile}'. Supported profiles: {', '.join(supported_setup_profiles())}.")

    spec = SETUP_PROFILES[profile]
    if spec.get("debian_only") and not debian:
        die(f"The '{profile}' setup profile is only supported on Debian-based systems.")

    modules = list(spec["modules"])
    warn(f"Running setup profile '{BOLD}{profile}{NORMAL}' ({spec['description']})")
    provision_modules_batch(modules)


__all__ = [name for name in globals() if not name.startswith("__")]
