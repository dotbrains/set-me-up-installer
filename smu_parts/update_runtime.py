from .client_update import *


def client_identity():
    if os.path.exists(update_client_id_path):
        with open(update_client_id_path) as f:
            client_id = f.read().strip()
    else:
        os.makedirs(os.path.dirname(update_client_id_path), exist_ok=True)
        client_id = hashlib.sha256(f"{platform.node()}:{smu_home_dir}".encode()).hexdigest()[:16]
        with open(update_client_id_path, "w") as f:
            f.write(f"{client_id}\n")
    return {
        "client_id": client_id,
        "hostname": platform.node() if os.getenv("SMU_REPORT_HOSTNAME") == "1" else None,
        "platform": str(sys.platform),
        "machine": str(platform.machine()),
        "version": "1.0.0",
    }


def update_channel_ref(policy=None):
    policy = policy or read_update_policy()
    channel = policy.get("channel", "stable")
    channels = policy.get("channels", {})
    return policy.get("ref") or channels.get(channel), channel


def fetch_update_manifest(policy=None):
    policy = policy or read_update_policy()
    url = policy.get("manifest_url")
    if not url:
        return {"status": "disabled"}
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = response.read()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as e:
        return {"status": "failed", "error": str(e)}
    digest = hashlib.sha256(data).hexdigest()
    expected = policy.get("manifest_sha256")
    if expected and digest != expected:
        return {"status": "failed", "sha256": digest, "error": "manifest sha256 mismatch"}
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return {"status": "failed", "sha256": digest, "error": str(e)}
    return {"status": "verified" if expected else "unverified", "sha256": digest, "manifest": manifest}


def client_update_preflight(ref=None):
    policy = read_update_policy()
    channel_ref, channel = update_channel_ref(policy)
    ref = ref if ref is not None else channel_ref
    report = client_update_status(ref=ref)
    manifest = fetch_update_manifest(policy)
    failed = bool(report["policy_errors"])
    failed = failed or report["rate_limit"]["status"] == "waiting"
    failed = failed or manifest["status"] == "failed"
    report.update({
        "client": client_identity(),
        "channel": channel,
        "resolved_ref": ref,
        "manifest": manifest,
        "preflight": "failed" if failed else "passed",
    })
    return report


def print_client_update_preflight(json_output=False, ref=None):
    report = client_update_preflight(ref=ref)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{report['preflight']}\tpreflight")
        print(f"{report['rate_limit']['status']}\trate_limit")
        print(f"{report['manifest']['status']}\tmanifest")
    return 1 if report["preflight"] == "failed" else 0


def rollback_client_update_repositories():
    last = read_update_lock()
    repos = last.get("repositories", [])
    results = []
    for repo in repos:
        before = repo.get("before")
        if not before:
            continue
        try:
            subprocess.run(["git", "-C", repo["path"], "checkout", before], check=True)
            status = "rolled-back"
        except (subprocess.CalledProcessError, OSError):
            status = "failed"
        results.append({"name": repo.get("name"), "path": repo.get("path"), "ref": before, "status": status})
    return results


def update_schedule_payload():
    policy = read_update_policy()
    return {
        "path": update_schedule_path,
        "command": [sys.executable, os.path.join(installer_root, "smu.py"), "update", "preflight", "--json"],
        "apply_command": [sys.executable, os.path.join(installer_root, "smu.py"), "update", "--yes", "--json"],
        "schedule": policy.get("schedule"),
        "auto_apply": policy.get("auto_apply"),
        "min_interval_seconds": policy.get("min_interval_seconds"),
        "backoff_seconds": policy.get("backoff_seconds"),
    }


def update_schedule_files(payload):
    smu_path = os.path.join(installer_root, "smu.py")
    interval = str(max(60, payload.get("min_interval_seconds") or 3600))
    if sys.platform == "darwin":
        return [{
            "path": update_launchd_path,
            "content": "\n".join([
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0"><dict>',
                '<key>Label</key><string>com.dotbrains.smu-update</string>',
                '<key>ProgramArguments</key><array>',
                f"<string>{sys.executable}</string><string>{smu_path}</string><string>update</string><string>preflight</string><string>--json</string>",
                '</array>',
                f"<key>StartInterval</key><integer>{interval}</integer>",
                '<key>RunAtLoad</key><true/>',
                '</dict></plist>',
                "",
            ]),
        }]
    service_path = os.path.join(update_systemd_dir, "smu-update.service")
    timer_path = os.path.join(update_systemd_dir, "smu-update.timer")
    return [
        {
            "path": service_path,
            "content": "\n".join([
                "[Unit]",
                "Description=set-me-up client update preflight",
                "",
                "[Service]",
                "Type=oneshot",
                f"ExecStart={sys.executable} {smu_path} update preflight --json",
                "",
            ]),
        },
        {
            "path": timer_path,
            "content": "\n".join([
                "[Unit]",
                "Description=Run set-me-up client update preflight",
                "",
                "[Timer]",
                "OnBootSec=5m",
                f"OnUnitActiveSec={interval}s",
                "",
                "[Install]",
                "WantedBy=timers.target",
                "",
            ]),
        },
    ]


def update_schedule(action_name, json_output=False):
    payload = update_schedule_payload()
    files = update_schedule_files(payload)
    if action_name == "install":
        write_json_file(update_schedule_path, payload)
        for item in files:
            os.makedirs(os.path.dirname(item["path"]), exist_ok=True)
            with open(item["path"], "w") as f:
                f.write(item["content"])
        payload["status"] = "installed"
    elif action_name == "remove":
        for path in [update_schedule_path, *(item["path"] for item in files)]:
            if os.path.exists(path):
                os.unlink(path)
        payload["status"] = "removed"
    else:
        payload["status"] = "installed" if os.path.exists(update_schedule_path) else "missing"
    payload["scheduler_files"] = [{"path": item["path"], "exists": os.path.exists(item["path"])} for item in files]
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['status']}\tschedule\t{update_schedule_path}")
    return 0


__all__ = [name for name in globals() if not name.startswith("__")]
