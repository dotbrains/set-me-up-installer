#!/usr/bin/env python3

"""Shared set-me-up manifest contract helpers."""

import json
import pathlib
import re


ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ADAPTER_MODES = ("copy", "symlink")
SCHEMA_VERSION_KEY = "schema_version"
SUPPORTED_SCHEMA_VERSION = 1
PROVISIONING_CONTRACT_VERSION = 1
PROVISIONING_BLUEPRINT_KEYS = (
    "provisioning.mode",
    "provisioning.adapter",
    "provisioning.nix_adapter",
)
PROVISIONING_ADAPTER_IDS = ("rcm", "home-manager", "nix-darwin", "nixos", "hybrid")
JSON_SCHEMA_CONTRACTS = (
    "provisioning-preflight",
    "provisioning-capabilities",
    "blueprint-ci-readiness",
)


def parse_value(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        items = []
        raw_items = value[1:-1].split(",")
        for item in raw_items:
            item = item.strip()
            if item:
                items.append(parse_value(item))
        return items
    quoted = (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    )
    value = value.strip('"').strip("'")
    if value == "true":
        return True
    if value == "false":
        return False
    if not quoted and re.match(r"^-?[0-9]+$", value):
        return int(value)
    return value


def read_manifest(path):
    data = {}
    current_section = None

    if not pathlib.Path(path).exists():
        return data

    for raw_line in pathlib.Path(path).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.match(r"^\[([A-Za-z0-9_.-]+)\]$", line)
        if section_match:
            section_names = section_match.group(1).split(".")
            current_section = data
            for section_name in section_names:
                current_section = current_section.setdefault(section_name, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = parse_value(value)
        if current_section is not None:
            current_section[key] = value
        else:
            data[key] = value

    return data


def format_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'


def write_manifest(path, manifest):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    scalar_items = [
        (key, value)
        for key, value in manifest.items()
        if not isinstance(value, dict)
    ]
    for key, value in scalar_items:
        lines.append(f"{key} = {format_value(value)}")

    for key, values in manifest.items():
        if not isinstance(values, dict):
            continue
        if lines:
            lines.append("")
        lines.append(f"[{key}]")
        for nested_key, nested_value in values.items():
            lines.append(f"{nested_key} = {format_value(nested_value)}")

    path.write_text("\n".join(lines) + "\n")


def manifests(manifests_dir):
    return [
        read_manifest(path)
        for path in sorted(pathlib.Path(manifests_dir).glob("*.toml"))
    ]


def manifest_by_id(manifests_dir):
    return {
        manifest["id"]: manifest
        for manifest in manifests(manifests_dir)
        if manifest.get("id")
    }


def valid_id(manifest_id):
    return bool(manifest_id and ID_RE.match(manifest_id))


def schema_version(manifest):
    version = manifest.get(SCHEMA_VERSION_KEY)
    if version is None:
        return None
    if isinstance(version, int) and not isinstance(version, bool):
        return version
    if isinstance(version, str) and re.match(r"^[0-9]+$", version):
        return int(version)
    return version


def migrate_manifest(manifest):
    migrated = {}
    migrated[SCHEMA_VERSION_KEY] = SUPPORTED_SCHEMA_VERSION
    for key, value in manifest.items():
        if key == SCHEMA_VERSION_KEY:
            continue
        if isinstance(value, dict):
            migrated[key] = dict(value)
        else:
            migrated[key] = value
    return migrated


def schema_version_errors(label, manifests, require_schema_version=False):
    errors = []
    for manifest in manifests:
        manifest_id = manifest.get("id", "<unknown>")
        version = schema_version(manifest)
        if version is None:
            if require_schema_version:
                errors.append(f"{label}: {manifest_id} missing schema_version")
            continue
        if not isinstance(version, int):
            errors.append(f"{label}: {manifest_id} schema_version must be an integer")
            continue
        if version != SUPPORTED_SCHEMA_VERSION:
            errors.append(
                f"{label}: {manifest_id} schema_version {version} is not supported; expected {SUPPORTED_SCHEMA_VERSION}"
            )
    return errors


def merge_manifest(parent, child):
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


def resolve_inheritance(manifests):
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
        resolved_manifest = merge_manifest(resolved_parent, manifest)
        resolved[manifest_id] = resolved_manifest
        return resolved_manifest

    return [resolve(manifest) for manifest in manifests]


def merge_catalog_manifests(builtins, user_manifests):
    merged = list(builtins)
    seen = {entry.get("id") for entry in builtins if entry.get("id")}
    for manifest in user_manifests:
        manifest_id = manifest.get("id")
        if manifest_id and manifest_id not in seen:
            merged.append(manifest)
            seen.add(manifest_id)
    return resolve_inheritance(merged)


def duplicate_ids(entries):
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


def adapter_authoring_errors(label, manifests):
    errors = []
    for manifest in manifests:
        manifest_id = manifest.get("id", "<unknown>")
        if manifest.get("id") and not valid_id(manifest["id"]):
            errors.append(f"{label}: {manifest_id} id must be kebab-case")

        sources = manifest.get("adapter_sources", {})
        targets = manifest.get("adapter_targets", {})
        modes = manifest.get("adapter_modes", {})
        if sources and not isinstance(sources, dict):
            errors.append(f"{label}: {manifest_id} [adapter_sources] must be a table")
            sources = {}
        if targets and not isinstance(targets, dict):
            errors.append(f"{label}: {manifest_id} [adapter_targets] must be a table")
            targets = {}
        if modes and not isinstance(modes, dict):
            errors.append(f"{label}: {manifest_id} [adapter_modes] must be a table")
            modes = {}

        for name in sorted(set(sources) - set(targets)):
            errors.append(f"{label}: {manifest_id} adapter {name} has source without target")
        for name in sorted(set(targets) - set(sources)):
            errors.append(f"{label}: {manifest_id} adapter {name} has target without source")
        for name, mode in sorted(modes.items()):
            if name not in sources:
                errors.append(f"{label}: {manifest_id} adapter {name} has mode without source")
            if mode not in ADAPTER_MODES:
                errors.append(
                    f"{label}: {manifest_id} adapter {name} mode must be one of {', '.join(ADAPTER_MODES)}"
                )

    return errors


def manifest_authoring_errors(label, manifests, require_schema_version=False):
    errors = []
    errors.extend(schema_version_errors(label, manifests, require_schema_version))
    errors.extend(adapter_authoring_errors(label, manifests))
    return errors


def _require_object(errors, payload, key, label):
    value = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(value, dict):
        errors.append(f"{label}.{key} must be an object")
        return {}
    return value


def _require_list(errors, payload, key, label):
    value = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(value, list):
        errors.append(f"{label}.{key} must be an array")
        return []
    return value


def json_contract_schema_path(name):
    if name not in JSON_SCHEMA_CONTRACTS:
        return None
    return pathlib.Path(__file__).resolve().parents[1] / "docs" / "json-contracts" / "schemas" / f"{name}.schema.json"


def json_contract_schema(name):
    path = json_contract_schema_path(name)
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_type_matches(value, expected):
    if isinstance(expected, list):
        return any(_schema_type_matches(value, item) for item in expected)
    return {
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
    }.get(expected, True)


def _json_schema_errors(schema, value, path):
    errors = []
    if "type" in schema and not _schema_type_matches(value, schema["type"]):
        errors.append(f"{path} must be {schema['type']}")
        return errors
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path} must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {', '.join(map(str, schema['enum']))}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path} missing {key}")
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                errors.extend(_json_schema_errors(child_schema, value[key], f"{path}.{key}"))

    if isinstance(value, list):
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(_json_schema_errors(schema["items"], item, f"{path}[{index}]"))
        for required_value in schema.get("x-required-values", []):
            if required_value not in value:
                errors.append(f"{path} missing {required_value}")
        required_ids = schema.get("x-required-item-ids", [])
        if required_ids:
            item_ids = {item.get("id") for item in value if isinstance(item, dict)}
            for required_id in required_ids:
                if required_id not in item_ids:
                    errors.append(f"{path} missing {required_id}")
    return errors


def json_contract_schema_errors(name, payload):
    schema = json_contract_schema(name)
    if not schema:
        return [f"unknown JSON contract schema: {name}"]
    return _json_schema_errors(schema, payload, name)


def provisioning_preflight_contract_errors(payload):
    errors = json_contract_schema_errors("provisioning-preflight", payload)
    if not isinstance(payload, dict):
        return errors

    required = {"adapter", "action", "host_supported", "can_apply", "preflight", "plan", "errors"}
    for key in sorted(required - set(payload)):
        message = f"provisioning-preflight missing {key}"
        if message not in errors:
            errors.append(message)

    if "preflight" in payload and not isinstance(payload["preflight"], str):
        errors.append("provisioning-preflight.preflight must be a string")
    plan = _require_object(errors, payload, "plan", "provisioning-preflight")
    _require_list(errors, plan, "commands", "provisioning-preflight.plan")
    _require_list(errors, payload, "errors", "provisioning-preflight")
    return errors


def provisioning_capabilities_contract_errors(payload):
    errors = json_contract_schema_errors("provisioning-capabilities", payload)
    if not isinstance(payload, dict):
        return errors

    contract = _require_object(errors, payload, "contract", "provisioning-capabilities")
    if contract.get("version") != PROVISIONING_CONTRACT_VERSION:
        errors.append("provisioning-capabilities.contract.version must be 1")
    for key in PROVISIONING_BLUEPRINT_KEYS:
        if key not in contract.get("blueprint_keys", []):
            errors.append(f"provisioning-capabilities.contract.blueprint_keys missing {key}")
    if contract.get("module_manifest_table") != "adapters":
        errors.append("provisioning-capabilities.contract.module_manifest_table must be adapters")
    if "path" not in contract.get("module_adapter_required_keys", []):
        errors.append("provisioning-capabilities.contract.module_adapter_required_keys missing path")

    adapters = {
        adapter.get("id"): adapter
        for adapter in _require_list(errors, payload, "adapters", "provisioning-capabilities")
        if isinstance(adapter, dict)
    }
    for adapter_id in PROVISIONING_ADAPTER_IDS:
        if adapter_id not in adapters:
            errors.append(f"provisioning-capabilities.adapters missing {adapter_id}")
    return errors


def blueprint_ci_readiness_contract_errors(payload):
    errors = json_contract_schema_errors("blueprint-ci-readiness", payload)
    if not isinstance(payload, dict):
        return errors

    readiness = _require_object(errors, payload, "readiness", "blueprint-ci-readiness")
    summary = _require_object(errors, readiness, "summary", "blueprint-ci-readiness.readiness")
    if readiness.get("preflight") != "passed":
        errors.append("blueprint-ci-readiness.readiness.preflight must be passed")
    if summary.get("workflow_preflight") != 3:
        errors.append("blueprint-ci-readiness.readiness.summary.workflow_preflight must be 3")
    if summary.get("provider_examples") != 6:
        errors.append("blueprint-ci-readiness.readiness.summary.provider_examples must be 6")
    return errors


JSON_CONTRACT_VALIDATORS = {
    "provisioning-preflight": provisioning_preflight_contract_errors,
    "provisioning-capabilities": provisioning_capabilities_contract_errors,
    "blueprint-ci-readiness": blueprint_ci_readiness_contract_errors,
}


def json_contract_errors(name, payload):
    validator = JSON_CONTRACT_VALIDATORS.get(name)
    if not validator:
        return [f"unknown JSON contract: {name}"]
    return validator(payload)
