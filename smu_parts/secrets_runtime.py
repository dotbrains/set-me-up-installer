from .core import *


SECRET_NAME_PATTERNS = (".env", "secret", "secrets", "credential", "credentials", "id_rsa", "id_ed25519")
SECRET_SKIP_DIRS = (".git", "__pycache__", ".mypy_cache", "Caches")
SECRET_VALUE_PATTERN = re.compile(r"(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}", re.IGNORECASE)


def _secret_candidate(path):
    name = os.path.basename(path).lower()
    if name.endswith((".pyc", ".pyo")):
        return False
    return any(pattern in name for pattern in SECRET_NAME_PATTERNS)


def secrets_scan(root=None, max_bytes=65536):
    root = root or smu_home_dir
    findings = []
    if not os.path.exists(root):
        return {"root": root, "findings": findings, "ok": True}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [item for item in dirnames if item not in SECRET_SKIP_DIRS]
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root)
            if _secret_candidate(path):
                findings.append({"path": rel, "risk": "secret-like-name"})
                continue
            try:
                if os.path.getsize(path) > max_bytes:
                    continue
                with open(path, errors="ignore") as f:
                    sample = f.read(max_bytes)
            except (IOError, OSError):
                continue
            if SECRET_VALUE_PATTERN.search(sample):
                findings.append({"path": rel, "risk": "secret-like-content"})
    return {"root": root, "findings": findings, "ok": not findings}


def secrets_command(argv):
    json_output = "--json" in argv
    root = _option_value(argv, "--root") or (_option_value(argv, "--repo") or smu_home_dir)
    if argv and argv[0] not in ("doctor", "--json"):
        die("Usage: smu secrets doctor [--root path] [--json]")
    payload = secrets_scan(root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for finding in payload["findings"]:
            print(f"{COL_RED}RISK{COL_RESET}\t{finding['risk']}\t{finding['path']}")
        if payload["ok"]:
            print(f"{COL_GREEN}OK{COL_RESET}   no secret-like files or values found")
    return 0 if payload["ok"] else 1


__all__ = [name for name in globals() if not name.startswith("__")]
