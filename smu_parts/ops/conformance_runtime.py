from ..core import *


def blueprint_conformance(root=None):
    root = root or smu_home_dir
    dotfiles = dotfiles_compatibility_contract(root)
    with contextlib.redirect_stdout(io.StringIO()):
        ci = blueprint_ci_contract(root=root, json_output=True, check_docs=False)
    readiness = dotfiles.get("readiness", {})
    checks = {
        "install_surface_ready": readiness.get("install_shim", False),
        "rcm_ready": readiness.get("adapter") in ("rcm", "hybrid"),
        "nix_ready": readiness.get("adapter") in ("home-manager", "nixos", "hybrid"),
        "hybrid_ready": readiness.get("adapter") == "hybrid",
        "vps_ready": readiness.get("vps_ready", False),
        "rollback_ready": bool(read_state_ledger()) or os.path.exists(os.path.join(root, "set-me-up-installer")),
        "ci_validated": ci == 0,
    }
    total = len(checks)
    passed = sum(1 for ok in checks.values() if ok)
    score = int(round((passed / total) * 100)) if total else 0
    return {
        "root": root,
        "checks": checks,
        "score": score,
        "passed": passed,
        "total": total,
        "grade": "ready" if score == 100 else "partial" if score >= 50 else "blocked",
        "ready": all(checks.values()),
    }


def _badge_markdown(payload):
    lines = ["# set-me-up Conformance", "", "| Check | Status |", "| --- | --- |"]
    for key, ok in payload["checks"].items():
        lines.append(f"| `{key}` | {'OK' if ok else 'TODO'} |")
    lines.append("")
    lines.append(f"Score: {payload['score']}% ({payload['passed']}/{payload['total']})")
    lines.append(f"Overall: {'ready' if payload['ready'] else 'not ready'}")
    lines.append("")
    return "\n".join(lines)


def conformance_command(argv):
    json_output = "--json" in argv
    markdown = "--markdown" in argv
    root = _option_value(argv, "--repo") or _option_value(argv, "--root") or smu_home_dir
    output = _option_value(argv, "--output")
    payload = blueprint_conformance(root)
    content = _badge_markdown(payload) if markdown else json.dumps(payload, indent=2, sort_keys=True)
    if output:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w") as f:
            f.write(content)
            f.write("\n")
        print(output)
    else:
        print(content)
    return 0 if payload["ready"] or not json_output else 1


__all__ = [name for name in globals() if not name.startswith("__")]
