from ..core import *


def release_notes_from_provenance(payload):
    provenance = payload.get("provenance", {}) if isinstance(payload, dict) else {}
    repositories = payload.get("repositories", []) if isinstance(payload, dict) else []
    lines = [
        "# set-me-up Release Notes",
        "",
        f"Generated: {provenance.get('timestamp') or _utc_timestamp()}",
        "",
        "## Provenance",
        "",
    ]
    for key in ("installer", "blueprint", "tests", "candidate", "tag"):
        value = provenance.get(key)
        if value:
            lines.append(f"- {key}: `{value}`")
    if repositories:
        lines.extend(["", "## Repository State", ""])
        for repo in repositories:
            lines.append(f"- `{repo.get('path')}` `{str(repo.get('head', ''))[:12]}` {repo.get('sync')}")
    return "\n".join(lines) + "\n"


def release_notes_command(argv):
    input_path = _option_value(argv, "--from") or _option_value(argv, "--input")
    output_path = _option_value(argv, "--output")
    if not input_path:
        die("Usage: smu release-notes --from release-readiness.json [--output path]")
    with open(os.path.abspath(os.path.expanduser(input_path)), encoding="utf-8") as handle:
        payload = json.load(handle)
    content = release_notes_from_provenance(payload)
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        print(output_path)
    else:
        print(content, end="")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
