from ..core import *


def provisioning_adapter_dashboard(adapter_id="home-manager", profile=None, modules=None):
    modules = list(modules or blueprint_profile_modules(profile))
    if not modules:
        modules = [row["name"] for row in module_provisioning_adapter_report(show_all=True)]
    rows = [resolve_module_provisioning_adapter(module, adapter_id) for module in modules]
    blocking = [row for row in rows if row["state"] != "ready"]
    next_port = blocking[0]["module"] if blocking else None
    percent = round(((len(rows) - len(blocking)) / len(rows)) * 100, 2) if rows else 0
    issue_lines = [
        f"## Port modules to {adapter_id}",
        "",
        f"Profile: `{profile or 'default'}`",
        f"Nix-ready: {percent}%",
        "",
        "### Blocking modules",
    ]
    for row in blocking:
        issue_lines.append(f"- [ ] `{row['module']}` ({row['state']})")
    if next_port:
        issue_lines.extend(["", f"Suggested next module: `{next_port}`"])
    return {
        "adapter": adapter_id,
        "profile": profile or "default",
        "nix_ready_percent": percent,
        "blocking_modules": blocking,
        "suggested_next_port": next_port,
        "github_issue": "\n".join(issue_lines),
    }


def print_provisioning_adapter_dashboard(adapter_id="home-manager", profile=None, modules=None, json_output=False):
    payload = provisioning_adapter_dashboard(adapter_id=adapter_id, profile=profile, modules=modules)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"adapter\t{payload['adapter']}")
        print(f"profile\t{payload['profile']}")
        print(f"nix_ready_percent\t{payload['nix_ready_percent']}")
        print(f"suggested_next_port\t{payload['suggested_next_port'] or '-'}")
        for row in payload["blocking_modules"]:
            print(f"blocking\t{row['module']}\t{row['state']}")
    return 0


def write_provisioning_adapter_issue(adapter_id="home-manager", profile=None, modules=None, output_path=None):
    payload = provisioning_adapter_dashboard(adapter_id=adapter_id, profile=profile, modules=modules)
    content = payload["github_issue"] + "\n"
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        print(output_path)
    else:
        print(content, end="")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
