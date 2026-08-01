from .core import *
from .module_lifecycle import provision_modules_batch


SETUP_PROFILE_DESCRIPTIONS = {
    "minimal": "Provision only the baseline dotfile manager.",
    "ci": "Provision a deterministic CI validation host.",
    "vps": "Provision a small Ubuntu/Debian server baseline.",
    "agent-host": "Provision a headless host suitable for agent workflows.",
    "laptop": "Provision a personal laptop baseline.",
    "workstation": "Provision a fuller development workstation baseline.",
}


def supported_setup_profiles():
    return supported_machine_profiles()


def setup_profile_modules(profile):
    return machine_profile_modules(profile)


def run_setup_profile(profile):
    if profile not in supported_setup_profiles():
        die(f"Unknown setup profile '{profile}'. Supported profiles: {', '.join(supported_setup_profiles())}.")
    spec = machine_profile(profile)
    if profile in ("vps", "ci", "agent-host") and not debian:
        die(f"The '{profile}' setup profile is only supported on Debian-based systems.")

    modules = list(spec["modules"])
    warn(f"Running setup profile '{BOLD}{profile}{NORMAL}' ({SETUP_PROFILE_DESCRIPTIONS[profile]})")
    provision_modules_batch(modules)


__all__ = [name for name in globals() if not name.startswith("__")]
