#!/usr/bin/env python3

"""Shared set-me-up manifest contract helpers."""

import pathlib
import re


ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ADAPTER_MODES = ("copy", "symlink")
SCHEMA_VERSION_KEY = "schema_version"
SUPPORTED_SCHEMA_VERSION = 1


def parse_value(value):
    value = value.strip().strip('"').strip("'")
    if value == "true":
        return True
    if value == "false":
        return False
    if re.match(r"^-?[0-9]+$", value):
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
        section_match = re.match(r"^\[([A-Za-z0-9_-]+)\]$", line)
        if section_match:
            current_section = section_match.group(1)
            data.setdefault(current_section, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = parse_value(value)
        if current_section:
            data[current_section][key] = value
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
