from .core import *
from .provisioning_adapters import PROVISIONING_ADAPTERS


BLUEPRINT_PROVIDER_EXAMPLES = {
    "debian-vps": {
        "platform": "Debian VPS",
        "host_family": "debian",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "ubuntu-vps": {
        "platform": "Ubuntu VPS",
        "host_family": "ubuntu",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "arch-vps": {
        "platform": "Arch VPS",
        "host_family": "arch",
        "mode": "nix",
        "adapter": "home-manager",
        "nix_adapter": None,
    },
    "nixos-vps": {
        "platform": "NixOS VPS",
        "host_family": "nixos",
        "mode": "nix",
        "adapter": "nixos",
        "nix_adapter": None,
    },
    "digitalocean-droplet": {
        "platform": "DigitalOcean Droplet",
        "host_family": "linux",
        "mode": "hybrid",
        "adapter": "hybrid",
        "nix_adapter": "home-manager",
    },
    "hetzner-cloud": {
        "platform": "Hetzner Cloud",
        "host_family": "linux",
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
        "host_family": "macos",
        "mode": "nix",
        "adapter": "nix-darwin",
        "provider": None,
        "reason": "macOS system-level Nix provisioning uses nix-darwin.",
    },
    "rcm": {
        "host_family": "linux",
        "mode": "rcm",
        "adapter": "rcm",
        "provider": None,
        "reason": "rcm keeps the traditional thoughtbot dotfile flow.",
    },
    "rcm-only": {
        "host_family": "linux",
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
        if exists:
            provider_errors.extend(_blueprint_provider_compatibility_errors(expected, mode, adapter, nix_adapter))
        capability = PROVISIONING_ADAPTERS.get(adapter or expected["adapter"], {})
        errors.extend(f"{rel}: {error}" for error in provider_errors)
        providers.append({
            "id": provider,
            "platform": expected["platform"],
            "host_family": expected["host_family"],
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


def blueprint_adapter_compatibility_errors(mode, adapter, nix_adapter=None, host_family=None):
    errors = []
    if mode not in ("rcm", "nix", "hybrid"):
        errors.append(f"unsupported provisioning mode '{mode}'")
        return errors
    capability = PROVISIONING_ADAPTERS.get(adapter)
    if not capability:
        errors.append(f"unsupported provisioning adapter '{adapter}'")
        return errors
    if capability["mode"] != mode:
        errors.append(f"adapter '{adapter}' is for mode '{capability['mode']}', not '{mode}'")
    if host_family and host_family not in capability["host_families"]:
        errors.append(f"adapter '{adapter}' does not support host family '{host_family}'")
    if mode == "hybrid":
        if adapter != "hybrid":
            errors.append("hybrid mode requires adapter 'hybrid'")
        if nix_adapter not in ("home-manager", "nix-darwin", "nixos"):
            errors.append("hybrid mode requires nix_adapter 'home-manager', 'nix-darwin', or 'nixos'")
        else:
            nix_capability = PROVISIONING_ADAPTERS[nix_adapter]
            if host_family and host_family not in nix_capability["host_families"]:
                errors.append(f"hybrid nix_adapter '{nix_adapter}' does not support host family '{host_family}'")
    elif nix_adapter:
        errors.append("nix_adapter is only valid for hybrid mode")
    return errors


def _blueprint_provider_compatibility_errors(expected, mode, adapter, nix_adapter):
    return blueprint_adapter_compatibility_errors(
        mode,
        adapter,
        nix_adapter,
        expected.get("host_family"),
    )


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
                "host_family": provider["host_family"] if provider else None,
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


def blueprint_recommendation_config(recommendation):
    lines = [
        "[provisioning]",
        f'mode = "{recommendation["mode"]}"',
        f'adapter = "{recommendation["adapter"]}"',
    ]
    if recommendation.get("nix_adapter"):
        lines.append(f'nix_adapter = "{recommendation["nix_adapter"]}"')
    if recommendation["mode"] == "hybrid":
        lines.append("allow_rcm_fallback = true")
    lines.extend([
        "",
        "[profile.default]",
        'modules = ["example"]',
        "",
    ])
    return "\n".join(lines)


def write_blueprint_recommendation_config(
    target=None,
    root=None,
    output_path=None,
    force=False,
    dry_run=False,
    json_output=False,
):
    payload = blueprint_provider_recommendation(target=target, root=root)
    if not payload["valid"]:
        if json_output:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for error in payload["errors"]:
                print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1
    output_path = output_path or os.path.join(os.path.abspath(root or smu_home_dir), "smu.toml")
    config = blueprint_recommendation_config(payload["recommendation"])
    result = dict(payload)
    result.update({
        "output": output_path,
        "content": config,
        "written": False,
    })
    if not dry_run:
        if os.path.exists(output_path) and not force:
            result["valid"] = False
            result["errors"] = [f"Blueprint config already exists: {output_path}. Use --force to overwrite."]
            if json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"{COL_RED}FAIL{COL_RESET} {result['errors'][0]}")
            return 1
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(config)
        result["written"] = True
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif dry_run:
        print(config, end="")
    else:
        print(output_path)
    return 0


def validate_blueprint_recommendation_config(target=None, root=None, input_path=None, json_output=False):
    root = os.path.abspath(root or smu_home_dir)
    input_path = input_path or os.path.join(root, "smu.toml")
    payload = blueprint_provider_recommendation(target=target, root=root)
    errors = list(payload["errors"])
    manifest = smu_contract.read_manifest(input_path) if os.path.exists(input_path) else {}
    provisioning = manifest.get("provisioning", {})
    if not os.path.exists(input_path):
        errors.append(f"{input_path}: missing")
    elif not isinstance(provisioning, dict):
        errors.append(f"{input_path}: [provisioning] must be a table")
    if payload["valid"] and isinstance(provisioning, dict):
        recommendation = payload["recommendation"]
        expected = {
            "mode": recommendation["mode"],
            "adapter": recommendation["adapter"],
            "nix_adapter": recommendation.get("nix_adapter"),
        }
        for key, value in expected.items():
            current = provisioning.get(key)
            if value and current != value:
                errors.append(f"{input_path}: expected {key} {value}")
            if key == "nix_adapter" and not value and current:
                errors.append(f"{input_path}: nix_adapter is not expected for {target}")
        errors.extend(
            f"{input_path}: {error}" for error in blueprint_adapter_compatibility_errors(
                provisioning.get("mode"),
                provisioning.get("adapter"),
                provisioning.get("nix_adapter"),
                recommendation.get("host_family"),
            )
        )
        if recommendation["mode"] == "hybrid" and provisioning.get("allow_rcm_fallback") is not True:
            errors.append(f"{input_path}: hybrid recommendations require allow_rcm_fallback = true")
    result = {
        "target": target,
        "path": input_path,
        "valid": not errors,
        "errors": errors,
        "recommendation": payload.get("recommendation"),
    }
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
    else:
        print(f"{COL_GREEN}OK{COL_RESET}   recommendation config {input_path}")
    return 0 if result["valid"] else 1


__all__ = [name for name in globals() if not name.startswith("__")]
