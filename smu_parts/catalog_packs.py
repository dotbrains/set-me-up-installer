from .adapters import *
from .catalog_registry import *
from .core import *
from .profile_commands import *


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

def _manifest_authoring_errors(label, manifests):
    return smu_contract.manifest_authoring_errors(label, manifests)

def _catalog_manifest_paths(catalog_dir):
    if not os.path.isdir(catalog_dir):
        return []
    return [
        os.path.join(catalog_dir, filename)
        for filename in sorted(os.listdir(catalog_dir))
        if filename.endswith(".toml")
    ]

def _catalog_pack_manifest(pack_dir):
    path = os.path.join(pack_dir, "pack.toml")
    if not os.path.exists(path):
        return {}
    return _read_simple_toml(path)

def _catalog_pack_errors(pack_dir):
    errors = []
    pack = _catalog_pack_manifest(pack_dir)
    if not pack:
        errors.append(f"pack missing pack.toml: {pack_dir}")
        return errors

    errors.extend(
        smu_contract.schema_version_errors(
            "pack",
            [pack],
            require_schema_version=True,
        )
    )
    if not pack.get("id"):
        errors.append("pack: <unknown> missing id")
    elif not _valid_catalog_id(pack["id"]):
        errors.append(f"pack: {pack['id']} id must be kebab-case")
    if not pack.get("name"):
        errors.append(f"pack: {pack.get('id', '<unknown>')} missing name")

    manifest_dirs = {
        "themes": os.path.join(pack_dir, "themes"),
        "prompts": os.path.join(pack_dir, "prompt-profiles"),
        "presets": os.path.join(pack_dir, "presets"),
    }
    for label, manifest_dir in manifest_dirs.items():
        manifests = [_read_simple_toml(path) for path in _catalog_manifest_paths(manifest_dir)]
        errors.extend(smu_contract.manifest_authoring_errors(label, manifests))

    return errors

def _catalog_pack_destinations(pack_dir):
    return [
        ("themes", os.path.join(pack_dir, "themes"), theme_catalog_path, theme_manifests_dir()),
        ("prompts", os.path.join(pack_dir, "prompt-profiles"), prompt_catalog_path, prompt_profiles_path),
        ("presets", os.path.join(pack_dir, "presets"), preset_catalog_path, preset_profiles_path),
    ]

def _copy_catalog_tree(source_dir, target_dir, dry_run=False, force=False):
    copied = []
    if not os.path.isdir(source_dir):
        return copied

    for root, _, filenames in os.walk(source_dir):
        for filename in sorted(filenames):
            source = os.path.join(root, filename)
            relative = os.path.relpath(source, source_dir)
            target = os.path.join(target_dir, relative)
            if os.path.exists(target) and not force:
                die(f"Catalog file already exists: {target}. Use --force to overwrite.")
            copied.append((source, target))
            if dry_run:
                print(f"{COL_YELLOW}DRY{COL_RESET}  would install {target}")
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            print(f"{COL_GREEN}OK{COL_RESET}   installed {target}")

    return copied

def _catalog_install_conflicts(pack_dir, force=False):
    errors = []
    for label, source_dir, user_dir, builtin_dir in _catalog_pack_destinations(pack_dir):
        pack_manifests = [_read_simple_toml(path) for path in _catalog_manifest_paths(source_dir)]
        builtin_ids = {
            entry.get("id")
            for entry in _read_manifest_dir(builtin_dir)
            if entry.get("id")
        }
        user_ids = {
            entry.get("id")
            for entry in _read_manifest_dir(user_dir)
            if entry.get("id")
        }

        for manifest in pack_manifests:
            manifest_id = manifest.get("id")
            if not manifest_id:
                continue
            if manifest_id in builtin_ids:
                errors.append(f"{label}: pack id {manifest_id} conflicts with built-in manifest")
            if manifest_id in user_ids and not force:
                errors.append(f"{label}: pack id {manifest_id} conflicts with user catalog manifest")

    return errors

def catalog_install(pack_dir, dry_run=False, force=False):
    registry_entry = None
    requested = pack_dir
    expanded = os.path.abspath(os.path.expanduser(pack_dir))
    if _is_url(pack_dir):
        try:
            pack_dir = _resolve_pack_source(pack_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            print(f"{COL_RED}FAIL{COL_RESET} catalog pack could not be loaded: {e}")
            return 1
    elif not os.path.exists(expanded):
        registry_entry = _catalog_locked_entry(pack_dir) or _catalog_registry_entry(pack_dir)
        if not registry_entry:
            print(f"{COL_RED}FAIL{COL_RESET} catalog pack not found: {requested}")
            return 1
        try:
            pack_dir = _resolve_pack_source(registry_entry["source"], sha256=registry_entry.get("sha256"))
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            print(f"{COL_RED}FAIL{COL_RESET} catalog pack could not be loaded: {e}")
            return 1
    else:
        try:
            pack_dir = _resolve_pack_source(pack_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            print(f"{COL_RED}FAIL{COL_RESET} catalog pack could not be loaded: {e}")
            return 1

    errors = _catalog_pack_errors(pack_dir)
    errors.extend(_catalog_install_conflicts(pack_dir, force=force))
    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1

    copied = []
    for _, source_dir, target_dir, _ in _catalog_pack_destinations(pack_dir):
        copied.extend(_copy_catalog_tree(source_dir, target_dir, dry_run=dry_run, force=force))

    if not copied:
        print(f"{COL_YELLOW}WARN{COL_RESET}  pack has no catalog files")
    elif dry_run:
        print(f"{COL_GREEN}OK{COL_RESET}   pack can install {len(copied)} file(s)")
    else:
        pack_id = registry_entry["id"] if registry_entry else _catalog_pack_manifest(pack_dir).get("id")
        print(f"{COL_GREEN}OK{COL_RESET}   installed pack {pack_id}")

    return 0

def _copy_pack_entry(source, pack_root, relative_dir, force=False):
    target = os.path.join(pack_root, relative_dir, os.path.basename(source))
    if os.path.exists(target) and not force:
        die(f"Pack file already exists: {target}. Use --force to overwrite.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    return target

def _package_manifest_with_files(manifest_path, pack_root, relative_dir, force=False):
    manifest = _read_simple_toml(manifest_path)
    copied = [_copy_pack_entry(manifest_path, pack_root, relative_dir, force=force)]
    sources = manifest.get("adapter_sources", {})
    if isinstance(sources, dict):
        source_dir = os.path.dirname(manifest_path)
        for source in sources.values():
            source_path = _expand_adapter_path(source, source_dir)
            if os.path.exists(source_path):
                relative_source = os.path.relpath(source_path, source_dir)
                target = os.path.join(pack_root, relative_dir, relative_source)
                if os.path.exists(target) and not force:
                    die(f"Pack file already exists: {target}. Use --force to overwrite.")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source_path, target)
                copied.append(target)
    return copied

def catalog_package(manifest_id, output=None, force=False):
    if not _valid_catalog_id(manifest_id):
        die(f"Pack id must be kebab-case: {manifest_id}")

    output = output or f"{manifest_id}.smu-pack"
    pack_root = os.path.abspath(os.path.expanduser(output))
    if os.path.exists(pack_root) and not force:
        die(f"Pack output already exists: {pack_root}. Use --force to overwrite.")
    os.makedirs(pack_root, exist_ok=True)

    copied = []
    candidates = [
        (theme_catalog_path, "themes"),
        (prompt_catalog_path, "prompt-profiles"),
        (preset_catalog_path, "presets"),
    ]
    for source_dir, relative_dir in candidates:
        manifest_path = _manifest_file_for_id(manifest_id, (source_dir,))
        if manifest_path:
            copied.extend(_package_manifest_with_files(manifest_path, pack_root, relative_dir, force=force))

    if not copied:
        die(f"No user catalog manifest found for id '{manifest_id}'")

    smu_contract.write_manifest(os.path.join(pack_root, "pack.toml"), {
        "schema_version": smu_contract.SUPPORTED_SCHEMA_VERSION,
        "id": manifest_id,
        "name": _display_name(manifest_id),
    })
    print(f"{COL_GREEN}OK{COL_RESET}   packaged {len(copied)} file(s) into {pack_root}")
    return 0

def _write_registry_index(index_path, packs):
    lines = [
        f"schema_version = {smu_contract.SUPPORTED_SCHEMA_VERSION}",
    ]
    for pack_id, pack in sorted(packs.items()):
        lines.append("")
        lines.append(f"[packs.{pack_id}]")
        for key in ("name", "description", "source", "sha256"):
            value = pack.get(key)
            if value:
                lines.append(f"{key} = {smu_contract.format_value(value)}")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w") as f:
        f.write("\n".join(lines) + "\n")

def _zip_pack_directory(pack_dir, archive_path, force=False):
    if os.path.exists(archive_path) and not force:
        die(f"Published pack already exists: {archive_path}. Use --force to overwrite.")
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _, filenames in os.walk(pack_dir):
            for filename in sorted(filenames):
                source = os.path.join(root, filename)
                relative = os.path.relpath(source, pack_dir)
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(source, "rb") as f:
                    archive.writestr(info, f.read())

def catalog_publish(pack_dir, registry, pack_id=None, force=False):
    pack_dir = os.path.abspath(os.path.expanduser(pack_dir))
    registry = os.path.abspath(os.path.expanduser(registry))
    if _is_url(registry):
        die("Catalog publish requires a local registry path")

    errors = _catalog_pack_errors(pack_dir)
    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1

    pack = _catalog_pack_manifest(pack_dir)
    pack_id = pack_id or pack.get("id")
    if not _valid_catalog_id(pack_id):
        die(f"Published pack id must be kebab-case: {pack_id}")

    index_path = os.path.join(registry, "index.toml")
    index = _read_simple_toml(index_path)
    existing_packs = index.get("packs", {})
    if existing_packs and not isinstance(existing_packs, dict):
        print(f"{COL_RED}FAIL{COL_RESET} registry index [packs] must be a table")
        return 1
    packs = dict(existing_packs) if isinstance(existing_packs, dict) else {}
    if pack_id in packs and not force:
        die(f"Registry pack already exists: {pack_id}. Use --force to overwrite.")

    archive_name = f"{pack_id}.smu-pack.zip"
    archive_path = os.path.join(registry, "packs", archive_name)
    _zip_pack_directory(pack_dir, archive_path, force=force)
    packs[pack_id] = {
        "name": pack.get("name", _display_name(pack_id)),
        "source": f"packs/{archive_name}",
        "sha256": _sha256_file(archive_path),
    }
    if pack.get("description"):
        packs[pack_id]["description"] = pack["description"]
    _write_registry_index(index_path, packs)

    registry_errors = _registry_index_errors("published", registry, _read_simple_toml(index_path))
    if registry_errors:
        for error in registry_errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1

    print(f"{COL_GREEN}OK{COL_RESET}   published {pack_id} to {registry}")
    return 0

def catalog_migrate(dry_run=False):
    targets = [
        ("themes", theme_catalog_path),
        ("prompts", prompt_catalog_path),
        ("presets", preset_catalog_path),
    ]
    changed = []

    for label, catalog_dir in targets:
        for path in _catalog_manifest_paths(catalog_dir):
            manifest = _read_simple_toml(path)
            errors = smu_contract.schema_version_errors(label, [manifest])
            if errors:
                for error in errors:
                    print(f"{COL_RED}FAIL{COL_RESET} {error}")
                return 1
            if smu_contract.schema_version(manifest) == smu_contract.SUPPORTED_SCHEMA_VERSION:
                continue

            changed.append(path)
            if dry_run:
                print(
                    f"{COL_YELLOW}DRY{COL_RESET}  would migrate {path} "
                    f"to schema_version {smu_contract.SUPPORTED_SCHEMA_VERSION}"
                )
            else:
                smu_contract.write_manifest(path, smu_contract.migrate_manifest(manifest))
                print(
                    f"{COL_GREEN}OK{COL_RESET}   migrated {path} "
                    f"to schema_version {smu_contract.SUPPORTED_SCHEMA_VERSION}"
                )

    if not changed:
        print(f"{COL_GREEN}OK{COL_RESET}   user catalogs already use schema_version {smu_contract.SUPPORTED_SCHEMA_VERSION}")

    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
