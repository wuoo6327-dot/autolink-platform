"""One-shot AUTOLINK SEO cutover with a persistent state file and rollback.

Run only on the reviewed AMD64 production host from a detached tmux session.
The preflight command never switches containers. The cutover command refuses
to run twice and uses only already-loaded images with pulling/building off.
"""

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


NEW = Path("/opt/autolink-releases/5725b8b-seo-20261012")
OLD = Path("/opt/autolink-releases/a38664fc9bf2be639cbcb65dce4b57ef5b94170c")
BACKUPS = Path("/opt/autolink-backups/seo-cutover-20261012")
OVERRIDE = BACKUPS / "rollback-compose-override.yaml"
STATE_DIR = Path("/opt/autolink-release-state/seo-20261012")
STAGE = Path("/home/admin/autolink-final-seo-qa-20261012")
AUTH_ID = "sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815"
WEB_ID = "sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb"
OLD_AUTH_ID = "sha256:328ad2e7f193d924d8adc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80"
CATALOG_SHA = "3c7bdf436bff712c0c50b249cf93c4c0bfda8d030133ccaf0532f2096734676b"
DOMAIN = "autolinkglobal.com"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def tree_fingerprint(root):
    value = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        value.update(path.relative_to(root).as_posix().encode() + b"\0")
        value.update(sha(path).encode() + b"\n")
    return len(files), value.hexdigest()


def run(args, timeout=30, check=True, log_output=True):
    print(now(), "RUN", " ".join(map(str, args)), flush=True)
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if log_output and result.stdout:
        print(result.stdout.strip(), flush=True)
    if log_output and result.stderr:
        print(result.stderr.strip(), file=sys.stderr, flush=True)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args[0]}")
    return result


def compose(root, *args, override=False, timeout=60):
    command = ["docker", "compose", "-p", "autolink-demo", "--project-directory", str(root),
               "-f", str(root / "compose.yaml")]
    if override:
        command += ["-f", str(OVERRIDE)]
    return run(command + list(args), timeout=timeout)


def container(name):
    # Docker inspect contains secret environment values; never print its body.
    data = json.loads(run(["docker", "inspect", name], timeout=10, log_output=False).stdout)
    if len(data) != 1:
        raise RuntimeError(f"Missing container: {name}")
    return data[0]


def health(name, expected_id, deadline):
    while time.monotonic() < deadline:
        item = container(name)
        if item["Image"] != expected_id:
            raise RuntimeError(f"Unexpected running image for {name}")
        state = item["State"]
        if state["Status"] == "running" and state.get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(2)
    raise TimeoutError(f"Health timeout: {name}")


def http(path):
    response = run([
        "curl", "-sS", "--max-time", "4", "--resolve", f"{DOMAIN}:443:127.0.0.1",
        "--write-out", "\n__AUTOLINK_STATUS__%{http_code}", f"https://{DOMAIN}{path}",
    ], timeout=5, log_output=False).stdout
    body, status = response.rsplit("\n__AUTOLINK_STATUS__", 1)
    return int(status), body


def core_probe(candidate):
    status, _ = http("/healthz")
    if status != 200:
        raise RuntimeError("Health HTTP status is not 200")
    status, models = http("/autolink/public/models?limit=500")
    status_b, brands = http("/autolink/public/brands")
    if (status, status_b) != (200, 200):
        raise RuntimeError("Public catalog unavailable")
    models_json, brands_json = json.loads(models), json.loads(brands)
    if (len(models_json["data"]), len(brands_json["data"])) != (244, 53):
        raise RuntimeError("Public catalog differs from verified 244/53")
    status, _ = http("/autolink/admin/users")
    if status != 401:
        raise RuntimeError("Private admin endpoint is not protected")
    status, _ = http("/buyer/login")
    if status != 200:
        raise RuntimeError("Buyer login route failed")
    status, _ = http("/")
    if status != 200:
        raise RuntimeError("Homepage failed")
    if candidate:
        status, detail = http("/trade/models/geely-monjaro-2026")
        if status != 200 or "Geely Monjaro" not in detail or "index, follow" not in detail:
            raise RuntimeError("English model SSR or index marker failed")
        if 'rel="canonical"' not in detail or 'hreflang="' not in detail:
            raise RuntimeError("Canonical or hreflang missing")
        status, brand = http("/trade/brands/geely")
        if status != 200 or "Geely" not in brand:
            raise RuntimeError("English brand SSR failed")
        status, robots = http("/robots.txt")
        if status != 200 or "Sitemap:" not in robots:
            raise RuntimeError("robots.txt failed")
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        status, sitemap = http("/sitemaps/models-1.xml")
        if status != 200 or len(list(ElementTree.fromstring(sitemap).iter(namespace))) != 227:
            raise RuntimeError("Model Sitemap URL count differs from 227")
        status, brand_sitemap = http("/sitemaps/brands-1.xml")
        if status != 200 or len(list(ElementTree.fromstring(brand_sitemap).iter(namespace))) != 10:
            raise RuntimeError("Brand Sitemap URL count differs from 10")
        status, _ = http("/trade/models/not-a-model")
        if status != 404:
            raise RuntimeError("Unknown model does not return 404")
        status, noindex = http("/trade/models/aeolus-catalog-1")
        if status != 200 or "noindex" not in noindex:
            raise RuntimeError("Unreviewed model is not noindex")
    print(now(), "CORE_PROBE_OK", json.dumps({"candidate": candidate, "models": 244, "brands": 53}), flush=True)


def preflight(lock):
    if os.geteuid() != 0 or platform.machine() != "x86_64":
        raise RuntimeError("Requires root on linux/amd64 host")
    for path in (NEW / "compose.yaml", NEW / "Caddyfile", NEW / ".env", NEW / "site",
                 OLD / "compose.yaml", OLD / "Caddyfile", OLD / "site", OVERRIDE):
        if not path.exists():
            raise RuntimeError(f"Missing release file: {path}")
    if (NEW / ".env").stat().st_mode & 0o077:
        raise RuntimeError("Candidate runtime config is not root-only")
    if sha(NEW / "compose.yaml") != sha(STAGE / "compose.yaml"):
        raise RuntimeError("Candidate Compose file differs from tested source")
    if sha(NEW / "Caddyfile") != sha(STAGE / "Caddyfile"):
        raise RuntimeError("Candidate Caddyfile differs from tested source")
    if tree_fingerprint(NEW / "site") != tree_fingerprint(STAGE / "release-public" / "site"):
        raise RuntimeError("Candidate public site differs from tested overlay")
    if sha(BACKUPS / "rollback-catalog.json") != CATALOG_SHA:
        raise RuntimeError("Rollback catalog no longer matches verified public directory")
    for filename, image_id in (("auth-local-image-evidence-v2.json", AUTH_ID),
                               ("web-local-image-evidence.json", WEB_ID)):
        evidence = json.loads((STAGE / filename).read_text())
        if evidence["dockerImageID"] != image_id or evidence["architecture"] != "amd64":
            raise RuntimeError("Image evidence differs from candidate lock")
        if evidence["archiveSHA256"] != "sha256:" + sha(Path(evidence["archive"])):
            raise RuntimeError("Image archive changed after verification")
    compose(NEW, "config", "-q")
    compose(OLD, "config", "-q", override=True)
    if set(compose(NEW, "config", "--images").stdout.splitlines()) != {
        "autolink-final-seo-auth@" + AUTH_ID,
        "autolink-round3-caddy@" + WEB_ID,
    }:
        raise RuntimeError("Candidate Compose images differ from approved fixed IDs")
    if container("autolink-demo-auth-1")["Image"] != OLD_AUTH_ID:
        raise RuntimeError("Production auth baseline changed")
    if container("autolink-demo-web-1")["Image"] != WEB_ID:
        raise RuntimeError("Production web baseline changed")
    health("autolink-demo-auth-1", OLD_AUTH_ID, time.monotonic() + 5)
    if not lock.exists():
        raise RuntimeError("Fresh, restored production backup manifest is missing")
    backup = json.loads(lock.read_text())
    if not backup.get("isolatedRestoreVerified") or backup.get("publicModels") != 244 or backup.get("publicBrands") != 53:
        raise RuntimeError("Production backup or public catalog verification is incomplete")
    if (backup.get("databaseModels"), backup.get("databaseBrands")) != (270, 60):
        raise RuntimeError("Production database totals differ from verified baseline")
    if time.time() - datetime.fromisoformat(backup["createdAtUTC"]).timestamp() > 15 * 60:
        raise RuntimeError("Production backup is older than 15 minutes")
    if not Path(backup["sqliteBackup"]).is_file() or sha(Path(backup["sqliteBackup"])) != backup["sqliteSHA256"]:
        raise RuntimeError("Latest SQLite snapshot changed")
    actual_source = Path(next(item["Source"] for item in container("autolink-demo-auth-1")["Mounts"]
                              if item["Destination"] == "/data")) / "autolink-auth.sqlite3"
    if Path(backup["sqliteSource"]) != actual_source:
        raise RuntimeError("SQLite backup source differs from the running Auth mount")
    if sha(Path(backup["publicCatalog"])) != backup["publicCatalogSHA256"]:
        raise RuntimeError("Saved public catalog changed")
    saved_catalog = json.loads(Path(backup["publicCatalog"]).read_text())
    _, current_models = http("/autolink/public/models?limit=500")
    _, current_brands = http("/autolink/public/brands")
    if (saved_catalog["models"] != json.loads(current_models)["data"] or
            saved_catalog["brands"] != json.loads(current_brands)["data"]):
        raise RuntimeError("Public catalog changed after the final backup")
    for item in backup["files"].values():
        if not item.get("restored") or sha(Path(item["archive"])) != item["sha256"]:
            raise RuntimeError("A restored production archive changed")
    for item in backup["images"].values():
        if sha(Path(item["archive"])) != item["sha256"]:
            raise RuntimeError("A saved production image changed")
    core_probe(False)
    print(now(), "PREFLIGHT_OK", flush=True)


def state_write(name, **extra):
    payload = {"state": name, "atUTC": now(), **extra}
    path = STATE_DIR / "status.json"
    temporary = STATE_DIR / ".status.json.tmp"
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    print(now(), "STATE", name, flush=True)


def rollback(reason):
    state_write("rolling_back", reason=reason)
    compose(OLD, "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "--no-build", "auth", override=True, timeout=50)
    health("autolink-demo-auth-1", OLD_AUTH_ID, time.monotonic() + 40)
    compose(OLD, "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "--no-build", "web", override=True, timeout=50)
    if container("autolink-demo-web-1")["Image"] != WEB_ID:
        raise RuntimeError("Rollback web image mismatch")
    core_probe(False)
    state_write("rolled_back", reason=reason)


def cutover(lock):
    os.umask(0o077)
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / "lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status_path = STATE_DIR / "status.json"
        if status_path.exists():
            raise RuntimeError("A cutover attempt already exists; inspect status and log, do not repeat")
        with (STATE_DIR / "cutover.log").open("a", buffering=1) as log:
            original_stdout, original_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            started = False
            try:
                def interrupted(signum, _frame):
                    raise InterruptedError(f"Received signal {signum}")
                signal.signal(signal.SIGTERM, interrupted)
                signal.signal(signal.SIGHUP, interrupted)
                preflight(lock)
                state_write("cutover_started")
                started = True
                deadline = time.monotonic() + 120  # Begin rollback while recovery time remains.
                compose(NEW, "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "--no-build", "auth", timeout=45)
                health("autolink-demo-auth-1", AUTH_ID, min(deadline, time.monotonic() + 35))
                if time.monotonic() > deadline:
                    raise TimeoutError("Cutover budget expired after auth")
                compose(NEW, "up", "-d", "--no-deps", "--force-recreate", "--pull", "never", "--no-build", "web", timeout=45)
                if container("autolink-demo-web-1")["Image"] != WEB_ID:
                    raise RuntimeError("Candidate web image mismatch")
                core_probe(True)
                if time.monotonic() > deadline:
                    raise TimeoutError("Cutover budget expired after core probes")
                state_write("live_core_verified", authImage=AUTH_ID, webImage=WEB_ID)
                failures = 0
                for minute in range(30):
                    time.sleep(60)
                    try:
                        health("autolink-demo-auth-1", AUTH_ID, time.monotonic() + 5)
                        if container("autolink-demo-web-1")["Image"] != WEB_ID:
                            raise RuntimeError("Web image changed during monitoring")
                        core_probe(True)
                        disk = shutil.disk_usage("/")
                        if disk.free < 1024 * 1024 * 1024:
                            raise RuntimeError("Root filesystem has less than 1 GiB free")
                        if minute % 5 == 0:
                            db_path = json.loads(lock.read_text())["sqliteSource"]
                            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                                    raise RuntimeError("Production SQLite quick check failed")
                            stats = run(["docker", "stats", "--no-stream", "--format",
                                         "{{.Name}} {{.CPUPerc}} {{.MemUsage}}",
                                         "autolink-demo-auth-1", "autolink-demo-web-1"], timeout=10)
                            print(now(), "RESOURCE_CHECK", stats.stdout.strip(), "diskFreeBytes", disk.free, flush=True)
                        failures = 0
                    except Exception as issue:
                        failures += 1
                        print(now(), "MONITOR_FAILURE", repr(issue), flush=True)
                        if failures >= 2:
                            raise
                    state_write("monitoring", minute=minute + 1, probeFailures=failures)
                state_write("completed", authImage=AUTH_ID, webImage=WEB_ID)
            except BaseException as issue:
                print(now(), "CUTOVER_FAILURE", repr(issue), flush=True)
                if started:
                    try:
                        rollback(repr(issue))
                    except BaseException as rollback_issue:
                        state_write("rollback_failed", error=repr(rollback_issue))
                        print(now(), "ROLLBACK_FAILURE", repr(rollback_issue), flush=True)
                raise
            finally:
                sys.stdout, sys.stderr = original_stdout, original_stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "cutover", "status"))
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    if args.mode == "status":
        path = STATE_DIR / "status.json"
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
        return
    if not args.backup_manifest:
        parser.error("--backup-manifest is required")
    if args.mode == "preflight":
        preflight(args.backup_manifest)
    else:
        cutover(args.backup_manifest)


if __name__ == "__main__":
    main()
