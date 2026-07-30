from .core import *


def git_has_worktree_changes(path):
    try:
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, OSError):
        return False


def update_git_repository_ff_only(path, label, force_reset=False):
    before = git_head(path)
    branch = git_branch(path)
    if not branch:
        return {
            "name": label,
            "path": path,
            "before": before,
            "after": before,
            "status": "failed",
            "error": "detached-head",
        }
    if git_has_worktree_changes(path) and not force_reset:
        return {
            "name": label,
            "path": path,
            "branch": branch,
            "before": before,
            "after": before,
            "status": "blocked",
            "error": "local-changes",
        }
    try:
        subprocess.run(["git", "-C", path, "fetch", "--quiet", "origin"], check=True)
        if force_reset:
            subprocess.run(["git", "-C", path, "reset", "--hard", f"origin/{branch}"], check=True)
            status = "reset"
        else:
            subprocess.run(["git", "-C", path, "merge", "--ff-only", f"origin/{branch}"], check=True)
            status = "updated"
    except (subprocess.CalledProcessError, OSError) as e:
        return {
            "name": label,
            "path": path,
            "branch": branch,
            "before": before,
            "after": git_head(path),
            "status": "failed",
            "error": str(e),
        }
    return {
        "name": label,
        "path": path,
        "branch": branch,
        "before": before,
        "after": git_head(path),
        "status": status,
        "force_reset": force_reset,
    }


def update_blueprint(force_reset=False):
    return update_git_repository_ff_only(smu_home_dir, "blueprint", force_reset=force_reset)


def update_installer_repository(force_reset=False):
    return update_git_repository_ff_only(installer_root, "installer", force_reset=force_reset)


def repository_update_doctor():
    repositories = []
    for repo in [
        {"name": "blueprint", "path": smu_home_dir},
        {"name": "installer", "path": installer_root},
    ]:
        status = git_upstream_sync(repo["path"])
        dirty = git_has_worktree_changes(repo["path"])
        repositories.append({
            **repo,
            **status,
            "dirty": dirty,
            "head": git_head(repo["path"]),
            "update_status": "blocked" if dirty else status["status"],
            "force_reset_required": dirty,
        })
    return {
        "repositories": repositories,
        "submodules": {
            "path": smu_home_dir,
            "gitmodules": os.path.exists(os.path.join(smu_home_dir, ".gitmodules")),
        },
    }


def print_repository_update_doctor(json_output=False):
    payload = repository_update_doctor()
    failed = any(repo["update_status"] in ("blocked", "diverged", "detached", "unknown") for repo in payload["repositories"])
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for repo in payload["repositories"]:
            print(f"{repo['update_status']}\t{repo['name']}\tdirty={str(repo['dirty']).lower()}\tbranch={repo.get('branch') or '-'}")
    return 1 if failed else 0


def print_repository_update_results(results, json_output=False):
    exit_code = 0 if all(item["status"] in ("updated", "reset") for item in results) else 1
    if json_output:
        print(json.dumps({"repositories": results, "exit_code": exit_code}, indent=2, sort_keys=True))
        return exit_code
    for item in results:
        detail = item.get("error") or item.get("branch") or "-"
        print(f"{item['status']}\t{item['name']}\t{detail}")
    return exit_code


def update_blueprint_command(json_output=False, force_reset=False, dry_run=False):
    plan = {"actions": ["update-blueprint"], "force_reset": force_reset, "path": smu_home_dir}
    if dry_run:
        if json_output:
            print(json.dumps(plan, indent=2, sort_keys=True))
        else:
            print("plan\tupdate-blueprint")
        return 0
    return print_repository_update_results([update_blueprint(force_reset=force_reset)], json_output=json_output)


def update_installer_command(json_output=False, force_reset=False, dry_run=False):
    plan = {"actions": ["update-installer"], "force_reset": force_reset, "path": installer_root}
    if dry_run:
        if json_output:
            print(json.dumps(plan, indent=2, sort_keys=True))
        else:
            print("plan\tupdate-installer")
        return 0
    return print_repository_update_results([update_installer_repository(force_reset=force_reset)], json_output=json_output)


def update_modules_command(json_output=False, dry_run=False):
    if dry_run:
        if json_output:
            print(json.dumps({"actions": ["update-modules"], "path": smu_home_dir}, indent=2, sort_keys=True))
        else:
            print("plan\tupdate-modules")
        return 0
    update_submodules()
    payload = {"actions": ["update-modules"], "exit_code": 0}
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def update_all_command(json_output=False, force_reset=False, dry_run=False, validate=False):
    if dry_run:
        actions = ["update-blueprint", "update-installer", "update-modules", "resolve-profile", "materialize-adapters"]
        if validate:
            actions.append("doctor")
        if json_output:
            print(json.dumps({"actions": actions, "force_reset": force_reset}, indent=2, sort_keys=True))
        else:
            for action_name in actions:
                print(f"plan\t{action_name}")
        return 0
    results = [
        update_blueprint(force_reset=force_reset),
        update_installer_repository(force_reset=force_reset),
    ]
    if any(item["status"] not in ("updated", "reset") for item in results):
        return print_repository_update_results(results, json_output=json_output)
    update_submodules()
    write_resolved_profile()
    materialize_adapters(current_theme(), current_prompt(), dry_run=False)
    exit_code = doctor() if validate else 0
    if json_output:
        print(json.dumps({"repositories": results, "exit_code": exit_code}, indent=2, sort_keys=True))
    else:
        print_repository_update_results(results, json_output=False)
    return exit_code


__all__ = [name for name in globals() if not name.startswith("__")]
