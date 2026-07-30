from .core import *
from .provisioning_adapters import PROVISIONING_ADAPTERS


BLUEPRINT_PROVIDER_EXAMPLES = {
    "debian-vps": {
        "platform": "Debian VPS",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "ubuntu-vps": {
        "platform": "Ubuntu VPS",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "arch-vps": {
        "platform": "Arch VPS",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "nixos-vps": {
        "platform": "NixOS VPS",
        "mode": "nix",
        "adapter": "nixos",
        "nix_adapter": None,
    },
    "digitalocean-droplet": {
        "platform": "DigitalOcean Droplet",
        "mode": "hybrid",
        "adapter": "hybrid",
        "nix_adapter": "home-manager",
    },
    "hetzner-cloud": {
        "platform": "Hetzner Cloud",
        "mode": "hybrid",
        "adapter": "hybrid",
        "nix_adapter": "home-manager",
    },
}


def blueprint_provider_matrix(root=None):
    root = os.path.abspath(root or smu_home_dir)
    providers = []
    errors = []
    for provider, expected in BLUEPRINT_PROVIDER_EXAMPLES.items():
        rel = os.path.join("examples", "providers", provider, "smu.toml")
        path = os.path.join(root, rel)
        exists = os.path.exists(path)
        manifest = smu_contract.read_manifest(path) if exists else {}
        provisioning = manifest.get("provisioning", {})
        if not isinstance(provisioning, dict):
            provisioning = {}
        mode = provisioning.get("mode")
        adapter = provisioning.get("adapter")
        nix_adapter = provisioning.get("nix_adapter")
        provider_errors = []
        if not exists:
            provider_errors.append("missing provider example")
        elif mode != expected["mode"]:
            provider_errors.append(f"expected mode {expected['mode']}")
        if exists and adapter != expected["adapter"]:
            provider_errors.append(f"expected adapter {expected['adapter']}")
        if exists and expected["nix_adapter"] and nix_adapter != expected["nix_adapter"]:
            provider_errors.append(f"expected nix_adapter {expected['nix_adapter']}")
        if exists and not expected["nix_adapter"] and nix_adapter:
            provider_errors.append("nix_adapter is only valid for hybrid examples")
        capability = PROVISIONING_ADAPTERS.get(adapter or expected["adapter"], {})
        errors.extend(f"{rel}: {error}" for error in provider_errors)
        providers.append({
            "id": provider,
            "platform": expected["platform"],
            "path": rel,
            "mode": mode,
            "adapter": adapter,
            "nix_adapter": nix_adapter,
            "expected_mode": expected["mode"],
            "expected_adapter": expected["adapter"],
            "expected_nix_adapter": expected["nix_adapter"],
            "capability": capability,
            "valid": not provider_errors,
        })
    return {
        "path": root,
        "providers": providers,
        "valid": not errors,
        "errors": errors,
    }


def print_blueprint_provider_matrix(root=None, json_output=False):
    payload = blueprint_provider_matrix(root=root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("provider\tplatform\tmode\tadapter\tnix_adapter\tstate")
        for provider in payload["providers"]:
            print(
                f"{provider['id']}\t{provider['platform']}\t"
                f"{provider['mode'] or '-'}\t{provider['adapter'] or '-'}\t"
                f"{provider['nix_adapter'] or '-'}\t"
                f"{'valid' if provider['valid'] else 'invalid'}"
            )
    return 0 if payload["valid"] else 1


__all__ = [name for name in globals() if not name.startswith("__")]
