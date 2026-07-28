from .core import *


def _option_value(argv, option):
    if option not in argv:
        return None
    index = argv.index(option)
    if index + 1 >= len(argv):
        die(f"{option} requires a value")
    return argv[index + 1]

def _is_url(source):
    return urllib.parse.urlparse(source).scheme != ""

def _is_https_url(source):
    return urllib.parse.urlparse(source).scheme == "https"

def _url_cache_name(source):
    parsed = urllib.parse.urlparse(source)
    parts = [parsed.netloc] + [part for part in parsed.path.split("/") if part]
    name = "__".join(parts) or "index"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)

def _download_url(source, cache_subdir):
    if not _is_https_url(source):
        raise ValueError(f"Only https:// catalog sources are supported: {source}")
    cache_dir = os.path.join(catalog_cache_path, cache_subdir)
    os.makedirs(cache_dir, exist_ok=True)
    target = os.path.join(cache_dir, _url_cache_name(source))
    with urllib.request.urlopen(source, timeout=30) as response:
        with open(target, "wb") as f:
            shutil.copyfileobj(response, f)
    return target

def _valid_sha256(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Fa-f0-9]{64}", value))

def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _verify_sha256(path, expected):
    if not expected:
        return
    if not _valid_sha256(expected):
        raise ValueError("sha256 must be 64 hexadecimal characters")
    actual = _sha256_file(path)
    if actual.lower() != expected.lower():
        raise ValueError(f"sha256 mismatch for downloaded pack: expected {expected}, got {actual}")

def _unpack_zip_pack(archive_path, cache_subdir):
    target_dir = os.path.join(catalog_cache_path, cache_subdir, os.path.splitext(os.path.basename(archive_path))[0])
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        target_root = os.path.abspath(target_dir)
        for member in archive.infolist():
            member_path = os.path.abspath(os.path.join(target_dir, member.filename))
            if not member_path.startswith(target_root + os.sep) and member_path != target_root:
                raise ValueError(f"Pack archive contains unsafe path: {member.filename}")
        archive.extractall(target_dir)

    if os.path.exists(os.path.join(target_dir, "pack.toml")):
        return target_dir
    children = [
        os.path.join(target_dir, child)
        for child in os.listdir(target_dir)
        if os.path.isdir(os.path.join(target_dir, child))
    ]
    for child in children:
        if os.path.exists(os.path.join(child, "pack.toml")):
            return child
    return target_dir

def _read_catalog_registries():
    manifest = _read_simple_toml(catalog_registries_path)
    registries = manifest.get("registries", {})
    if isinstance(registries, dict):
        return registries
    return {}

def _write_catalog_registries(registries):
    smu_contract.write_manifest(catalog_registries_path, {
        "schema_version": smu_contract.SUPPORTED_SCHEMA_VERSION,
        "registries": registries,
    })

def _catalog_registry_add(name, source):
    if not _valid_catalog_id(name):
        die(f"Registry name must be kebab-case: {name}")
    if _is_url(source) and not _is_https_url(source):
        die(f"Registry URL must use https://: {source}")
    registries = _read_catalog_registries()
    registries[name] = source
    _write_catalog_registries(registries)
    print(f"{COL_GREEN}OK{COL_RESET}   added registry {name}\t{source}")
    return 0

def _catalog_registry_list():
    registries = _read_catalog_registries()
    if not registries:
        print(f"{COL_YELLOW}WARN{COL_RESET}  no catalog registries configured")
        return 0
    for name, source in sorted(registries.items()):
        print(f"{name}\t{source}")
    return 0

def _read_catalog_registry_lock():
    if not os.path.exists(catalog_registry_lock_path):
        return {}
    with open(catalog_registry_lock_path) as f:
        return json.load(f)

def _write_catalog_registry_lock(lock):
    os.makedirs(os.path.dirname(catalog_registry_lock_path), exist_ok=True)
    with open(catalog_registry_lock_path, "w") as f:
        json.dump(lock, f, indent=2, sort_keys=True)
        f.write("\n")

def _catalog_registry_lock_validation_errors(lock):
    errors = []
    if not isinstance(lock, dict):
        return ["registry lock must be an object"]
    errors.extend(
        smu_contract.schema_version_errors(
            "registry lock",
            [lock],
            require_schema_version=True,
        )
    )
    registries = lock.get("registries", {})
    if not isinstance(registries, dict):
        return errors + ["registry lock: registries must be an object"]
    for registry_name, registry in registries.items():
        if not _valid_catalog_id(registry_name):
            errors.append(f"registry lock: registry name {registry_name} must be kebab-case")
            continue
        if not isinstance(registry, dict):
            errors.append(f"registry lock: registry {registry_name} must be an object")
            continue
        if not registry.get("source"):
            errors.append(f"registry lock: registry {registry_name} missing source")
        if not _valid_sha256(registry.get("index_sha256")):
            errors.append(f"registry lock: registry {registry_name} index_sha256 must be 64 hexadecimal characters")
        packs = registry.get("packs", {})
        if not isinstance(packs, dict):
            errors.append(f"registry lock: registry {registry_name} packs must be an object")
            continue
        for pack_id, pack in packs.items():
            if not _valid_catalog_id(pack_id):
                errors.append(f"registry lock: pack id {pack_id} must be kebab-case")
                continue
            if not isinstance(pack, dict):
                errors.append(f"registry lock: pack {pack_id} must be an object")
                continue
            if not pack.get("name"):
                errors.append(f"registry lock: pack {pack_id} missing name")
            if not pack.get("source"):
                errors.append(f"registry lock: pack {pack_id} missing source")
            if pack.get("sha256") and not _valid_sha256(pack["sha256"]):
                errors.append(f"registry lock: pack {pack_id} sha256 must be 64 hexadecimal characters")
    return errors

def _catalog_registry_lock_snapshot():
    errors = _catalog_registry_errors()
    if errors:
        return None, errors

    lock = {
        "schema_version": smu_contract.SUPPORTED_SCHEMA_VERSION,
        "registries": {},
    }
    for registry_name, source in sorted(_read_catalog_registries().items()):
        index_path = _registry_index_path(source, download_remote=True)
        index = _read_simple_toml(index_path)
        packs = {}
        for pack_id, pack in sorted(index.get("packs", {}).items()):
            locked_pack = {
                "name": pack["name"],
                "source": _registry_pack_source(source, pack["source"]),
            }
            if pack.get("description"):
                locked_pack["description"] = pack["description"]
            if pack.get("sha256"):
                locked_pack["sha256"] = pack["sha256"]
            packs[pack_id] = locked_pack
        lock["registries"][registry_name] = {
            "source": source,
            "index_sha256": _sha256_file(index_path),
            "packs": packs,
        }
    return lock, []

def _catalog_registry_lock():
    lock, errors = _catalog_registry_lock_snapshot()
    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1
    _write_catalog_registry_lock(lock)
    registry_count = len(lock["registries"])
    pack_count = sum(len(registry["packs"]) for registry in lock["registries"].values())
    print(f"{COL_GREEN}OK{COL_RESET}   locked {pack_count} pack(s) from {registry_count} registry(s)")
    return 0

def _catalog_registry_lock_entries():
    try:
        lock = _read_catalog_registry_lock()
    except (OSError, json.JSONDecodeError) as e:
        warn(f"Registry lock could not be loaded: {e}")
        return []
    if not lock:
        return []
    errors = _catalog_registry_lock_validation_errors(lock)
    if errors:
        for error in errors:
            warn(error)
        return []
    entries = []
    for registry_name, registry in sorted(lock.get("registries", {}).items()):
        for pack_id, pack in sorted(registry.get("packs", {}).items()):
            entry = dict(pack)
            entry["id"] = pack_id
            entry["registry"] = registry_name
            entry["locked"] = True
            entries.append(entry)
    return entries

def _catalog_locked_entry(pack_id):
    for entry in _catalog_registry_lock_entries():
        if entry["id"] == pack_id:
            return entry
    return None

def _catalog_registry_lock_errors():
    if not os.path.exists(catalog_registry_lock_path):
        return []
    try:
        current_lock = _read_catalog_registry_lock()
    except (OSError, json.JSONDecodeError) as e:
        return [f"registry lock could not be loaded: {e}"]
    errors = _catalog_registry_lock_validation_errors(current_lock)
    if errors:
        return errors
    expected_lock, snapshot_errors = _catalog_registry_lock_snapshot()
    if snapshot_errors:
        return snapshot_errors
    if current_lock != expected_lock:
        return ["registry lock is stale; run smu catalog registry lock"]
    return []

def _catalog_registry_status():
    if not os.path.exists(catalog_registry_lock_path):
        print(f"{COL_YELLOW}WARN{COL_RESET}  registry lock does not exist; run smu catalog registry lock")
        return 1
    errors = _catalog_registry_lock_errors()
    if errors:
        for error in errors:
            print(f"{COL_RED}FAIL{COL_RESET} {error}")
        return 1
    print(f"{COL_GREEN}OK{COL_RESET}   registry lock is up to date")
    return 0

def handle_catalog_registry_command(argv):
    command = argv[0] if argv else "list"
    if command == "list":
        raise SystemExit(_catalog_registry_list())
    if command == "add":
        if len(argv) < 3:
            die("Usage: smu catalog registry add <name> <path>")
        raise SystemExit(_catalog_registry_add(argv[1], argv[2]))
    if command == "lock":
        raise SystemExit(_catalog_registry_lock())
    if command == "status":
        raise SystemExit(_catalog_registry_status())
    die("Usage: smu catalog registry [add <name> <path>|list|lock|status]")

def _registry_index_path(source, download_remote=False):
    if _is_url(source):
        if not _is_https_url(source):
            raise ValueError(f"Registry URL must use https://: {source}")
        if download_remote:
            return _download_url(source, "registries")
        return None
    source = os.path.abspath(os.path.expanduser(source))
    if os.path.isdir(source):
        return os.path.join(source, "index.toml")
    return source

def _registry_pack_source(index_source, pack_source):
    if _is_url(pack_source):
        if not _is_https_url(pack_source):
            raise ValueError(f"Pack URL must use https://: {pack_source}")
        return pack_source
    if _is_url(index_source):
        return urllib.parse.urljoin(index_source, pack_source)
    expanded = os.path.expanduser(pack_source)
    if os.path.isabs(expanded):
        return expanded
    index_path = _registry_index_path(index_source)
    return os.path.abspath(os.path.join(os.path.dirname(index_path), expanded))

def _registry_source_exists(source):
    if _is_url(source):
        return _is_https_url(source)
    return os.path.exists(source)

def _registry_index_errors(registry_name, source, index):
    errors = []
    errors.extend(
        smu_contract.schema_version_errors(
            f"registry {registry_name}",
            [index],
            require_schema_version=True,
        )
    )
    packs = index.get("packs", {})
    if not isinstance(packs, dict):
        errors.append(f"registry {registry_name}: [packs] must be a table")
        return errors
    for pack_id, pack in packs.items():
        if not _valid_catalog_id(pack_id):
            errors.append(f"registry {registry_name}: pack id {pack_id} must be kebab-case")
            continue
        if not isinstance(pack, dict):
            errors.append(f"registry {registry_name}: pack {pack_id} must be a table")
            continue
        if not pack.get("name"):
            errors.append(f"registry {registry_name}: pack {pack_id} missing name")
        if not pack.get("source"):
            errors.append(f"registry {registry_name}: pack {pack_id} missing source")
        elif not _registry_source_exists(_registry_pack_source(source, pack["source"])):
            errors.append(f"registry {registry_name}: pack {pack_id} source does not exist")
        if pack.get("sha256") and not _valid_sha256(pack["sha256"]):
            errors.append(f"registry {registry_name}: pack {pack_id} sha256 must be 64 hexadecimal characters")
    return errors

def _catalog_registry_entries():
    entries = []
    for registry_name, source in sorted(_read_catalog_registries().items()):
        try:
            index_path = _registry_index_path(source, download_remote=True)
        except (OSError, ValueError) as e:
            warn(f"Registry {registry_name} could not be loaded: {e}")
            continue
        if not index_path or not os.path.exists(index_path):
            warn(f"Registry {registry_name} index does not exist: {index_path}")
            continue
        index = _read_simple_toml(index_path)
        errors = _registry_index_errors(registry_name, source, index)
        if errors:
            for error in errors:
                warn(error)
            continue
        for pack_id, pack in sorted(index.get("packs", {}).items()):
            entry = dict(pack)
            entry["id"] = pack_id
            entry["registry"] = registry_name
            entry["source"] = _registry_pack_source(source, pack["source"])
            entries.append(entry)
    return entries

def _catalog_registry_errors():
    errors = []
    for registry_name, source in sorted(_read_catalog_registries().items()):
        if not _valid_catalog_id(registry_name):
            errors.append(f"registry {registry_name} name must be kebab-case")
            continue
        try:
            index_path = _registry_index_path(source, download_remote=True)
        except (OSError, ValueError) as e:
            errors.append(f"registry {registry_name} could not be loaded: {e}")
            continue
        if not index_path or not os.path.exists(index_path):
            errors.append(f"registry {registry_name} index does not exist: {index_path}")
            continue
        errors.extend(_registry_index_errors(registry_name, source, _read_simple_toml(index_path)))
    return errors

def _catalog_registry_entry(pack_id):
    for entry in _catalog_registry_entries():
        if entry["id"] == pack_id:
            return entry
    return None

def _resolve_pack_source(source, sha256=None):
    if not _is_url(source):
        resolved = os.path.abspath(os.path.expanduser(source))
        _verify_sha256(resolved, sha256)
        if zipfile.is_zipfile(resolved):
            return _unpack_zip_pack(resolved, "packs")
        return resolved
    downloaded = _download_url(source, "packs")
    _verify_sha256(downloaded, sha256)
    if zipfile.is_zipfile(downloaded):
        return _unpack_zip_pack(downloaded, "packs")
    return downloaded

def catalog_search(query=""):
    query = query.lower()
    entries = [
        entry for entry in _catalog_registry_entries()
        if not query
        or query in entry["id"].lower()
        or query in str(entry.get("name", "")).lower()
        or query in str(entry.get("description", "")).lower()
    ]
    if not entries:
        print(f"{COL_YELLOW}WARN{COL_RESET}  no catalog packs found")
        return 0
    for entry in entries:
        description = entry.get("description")
        source = entry.get("source")
        pinned = "pinned" if entry.get("sha256") else "unpinned"
        if description:
            print(f"{entry['id']}\t{entry.get('name')}\t{entry['registry']}\t{pinned}\t{description}\t{source}")
        else:
            print(f"{entry['id']}\t{entry.get('name')}\t{entry['registry']}\t{pinned}\t{source}")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
