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
BLUEPRINT_PROVIDER_ALIASES = {
    "debian": "debian-vps",
    "debian-vps": "debian-vps",
    "ubuntu": "ubuntu-vps",
    "ubuntu-vps": "ubuntu-vps",
    "arch": "arch-vps",
    "arch-vps": "arch-vps",
    "nixos": "nixos-vps",
    "nixos-vps": "nixos-vps",
    "digitalocean": "digitalocean-droplet",
    "digitalocean-droplet": "digitalocean-droplet",
    "droplet": "digitalocean-droplet",
    "hetzner": "hetzner-cloud",
    "hetzner-cloud": "hetzner-cloud",
}
BLUEPRINT_HOST_RECOMMENDATIONS = {
    "macos": {
        "mode": "nix",
        "adapter": "nix-darwin",
        "provider": None,
        "reason": "macOS system-level Nix provisioning uses nix-darwin.",
    },
    "rcm": {
        "mode": "rcm",
        "adapter": "rcm",
        "provider": None,
        "reason": "rcm keeps the traditional thoughtbot dotfile flow.",
    },
    "rcm-only": {
        "mode": "rcm",
        "adapter": "rcm",
        "provider": None,
        "reason": "rcm-only hosts should avoid Nix-specific adapter requirements.",
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


def _provider_by_id(root):
    return {provider["id"]: provider for provider in blueprint_provider_matrix(root=root)["providers"]}


def blueprint_provider_recommendation(target=None, root=None):
    root = os.path.abspath(root or smu_home_dir)
    normalized = (target or "").strip().lower().replace("_", "-")
    if not normalized:
        return {
            "target": target,
            "valid": False,
            "errors": ["target is required"],
            "recommendation": None,
        }
    providers = _provider_by_id(root)
    provider_id = BLUEPRINT_PROVIDER_ALIASES.get(normalized)
    if provider_id:
        provider = providers.get(provider_id)
        return {
            "target": target,
            "valid": bool(provider and provider["valid"]),
            "errors": [] if provider and provider["valid"] else [f"{provider_id}: provider example is invalid or missing"],
            "recommendation": {
                "mode": provider["mode"] if provider else None,
                "adapter": provider["adapter"] if provider else None,
                "nix_adapter": provider["nix_adapter"] if provider else None,
                "provider": provider_id,
                "path": provider["path"] if provider else None,
                "capability": provider["capability"] if provider else {},
                "reason": f"Use the {provider_id} provider example for {target}.",
            },
        }
    if normalized in BLUEPRINT_HOST_RECOMMENDATIONS:
        recommendation = dict(BLUEPRINT_HOST_RECOMMENDATIONS[normalized])
        adapter = recommendation["adapter"]
        recommendation["capability"] = PROVISIONING_ADAPTERS.get(adapter, {})
        return {
            "target": target,
            "valid": True,
            "errors": [],
            "recommendation": recommendation,
        }
    known = sorted(set(BLUEPRINT_PROVIDER_ALIASES) | set(BLUEPRINT_HOST_RECOMMENDATIONS))
    return {
        "target": target,
        "valid": False,
        "errors": [f"unknown target '{target}'. Known targets: {', '.join(known)}"],
        "recommendation": None,
    }


def print_blueprint_provider_recommendation(target=None, root=None, json_output=False):
    payload = blueprint_provider_recommendation(target=target, root=root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload["valid"]:
        recommendation = payload["recommendation"]
        print("mode\tadapter\tnix_adapter\tprovider\tpath")
        print(
            f"{recommendation['mode']}\t{recommendation['adapter']}\t"
            f"{recommendation.get('nix_adapter') or '-'}\t"
            f"{recommendation.get('provider') or '-'}\t"
            f"{recommendation.get('path') or '-'}"
        )
    else:
        for error in payload["errors"]:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
    return 0 if payload["valid"] else 1


__all__ = [name for name in globals() if not name.startswith("__")]
