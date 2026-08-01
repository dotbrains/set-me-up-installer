from ..core import *


REDACT_KEYS = re.compile(r"(token|secret|password|credential|api[_-]?key|private[_-]?key)", re.IGNORECASE)
REDACT_VALUES = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(token|secret|password|api[_-]?key)=([^\\s]+)"),
)


def _redact(value):
    if isinstance(value, dict):
        return {key: ("<redacted>" if REDACT_KEYS.search(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in REDACT_VALUES:
            redacted = pattern.sub(lambda match: match.group(1) + "=<redacted>" if match.lastindex and match.lastindex >= 2 else "<redacted>", redacted)
        if redacted != value or SECRET_VALUE_PATTERN.search(value):
            return redacted if redacted != value else "<redacted>"
    return value


def support_bundle(redact=True):
    payload = {
        "generated_at": _utc_timestamp(),
        "versions": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "installer": git_head(installer_root),
            "blueprint": git_head(smu_home_dir),
        },
        "health": health_report(),
        "plan": {
            "machine_profiles": [machine_profile(name) for name in supported_machine_profiles()],
            "coverage": provisioning_adapter_dashboard(),
        },
        "secrets": secrets_scan(smu_home_dir),
        "status": status_report(show_all=True, verbose=True),
    }
    return _redact(payload) if redact else payload


def support_command(argv):
    if not argv or argv[0] != "bundle":
        die("Usage: smu support bundle [--redact] [--json] [--output path]")
    payload = support_bundle(redact="--no-redact" not in argv)
    output = _option_value(argv, "--output")
    if output:
        write_json_file(output, payload)
        print(output)
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
