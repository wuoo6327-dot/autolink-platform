"""Round 14 fixed-image release gate and timed production cutover.

Runs only on the AUTOLINK linux/amd64 host. The existing cutover engine handles
single-attempt state, Auth-before-Web switching, rollback, and 30-minute checks.
No database or Docker volume is replaced during cutover or rollback.
"""

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import brand_identity_cutover as engine


BASELINE = Path("/opt/autolink-releases/40d685b-round12-20261012")
STATE_ROOT = Path("/opt/autolink-release-state/round14-20261013")
BACKUP_POINTER = Path("/opt/autolink-backups/round14-latest-path")
EXPECTED_OVERLAY = {
    "admin/app.js", "admin/bootstrap.js", "admin/index.html",
    "assets/business-page-bootstrap.mjs", "buyer/app.js", "buyer/index.html",
    "trade/app.js", "trade/directory-locales.js", "trade/index.html",
    "trade/model-directory.mjs", "trade/model-reference.css",
}
engine.OLD = BASELINE
engine.STATE_ROOT = STATE_ROOT


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_catalog():
    models_status, model_body = engine.http("/autolink/public/models?limit=500")
    brands_status, brand_body = engine.http("/autolink/public/brands")
    if (models_status, brands_status) != (200, 200):
        raise RuntimeError("Public catalog API unavailable")
    return {"models": json.loads(model_body)["data"],
            "brands": json.loads(brand_body)["data"]}


def prepare_backup_manifest():
    if os.geteuid() or platform.machine() != "x86_64":
        raise RuntimeError("Requires root on linux/amd64")
    root = Path(BACKUP_POINTER.read_text().strip())
    if not root.is_dir() or not root.name.startswith("round14-"):
        raise RuntimeError("Unexpected backup root")
    if (root / "backup-manifest.json").exists():
        raise RuntimeError("Backup manifest already exists; do not regenerate it")
    if (Path("/opt/autolink-backups/round14-backup.exit").read_text().strip() != "exit=0"
            or (root / "restore-verify.exit").read_text().strip() != "exit=0"):
        raise RuntimeError("Backup or isolated restore did not pass")
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=root,
                   check=True, capture_output=True, text=True)
    db_path = root / "autolink-auth.sqlite3"
    with sqlite3.connect(db_path) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup database integrity failed")
        counts = (db.execute("SELECT COUNT(*) FROM catalog_models").fetchone()[0],
                  db.execute("SELECT COUNT(*) FROM catalog_brands").fetchone()[0])
    if counts != (270, 60):
        raise RuntimeError(f"Production database totals changed: {counts}; review before release")
    catalog = public_catalog()
    if (len(catalog["models"]), len(catalog["brands"])) != (244, 53):
        raise RuntimeError("Public catalog changed; review before release")
    catalog_path = root / "public-catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True) + "\n")
    catalog_path.chmod(0o600)
    manifest = {
        "createdAtUTC": datetime.fromtimestamp(db_path.stat().st_mtime, timezone.utc).isoformat(),
        "backupRoot": str(root),
        "sqliteSource": "/var/lib/docker/volumes/autolink-demo_auth_data/_data/autolink-auth.sqlite3",
        "sqliteBackup": str(db_path), "sqliteSHA256": sha(db_path),
        "publicCatalog": str(catalog_path), "publicCatalogSHA256": sha(catalog_path),
        "publicModels": 244, "publicBrands": 53,
        "databaseModels": counts[0], "databaseBrands": counts[1],
        "isolatedRestoreVerified": True,
    }
    path = root / "backup-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    print(json.dumps({"manifest": str(path), "publicModels": 244, "publicBrands": 53,
                      "databaseModels": counts[0], "databaseBrands": counts[1]}))


def verify_overlay(release, lock):
    if release != Path("/opt/autolink-releases/ecee142-round14-20261013"):
        raise RuntimeError("Unexpected release directory")
    original = {path.relative_to(BASELINE / "site").as_posix(): sha(path)
                for path in (BASELINE / "site").rglob("*") if path.is_file()}
    current = {path.relative_to(release / "site").as_posix(): sha(path)
               for path in (release / "site").rglob("*") if path.is_file()}
    changed = {name for name in original.keys() | current.keys()
               if original.get(name) != current.get(name)}
    if changed != EXPECTED_OVERLAY:
        raise RuntimeError(f"Unreviewed site difference: {sorted(changed ^ EXPECTED_OVERLAY)}")
    for relative, expected in lock["files"].items():
        if sha(release / relative) != expected:
            raise RuntimeError(f"Locked release file changed: {relative}")
    if original["index.html"] != current["index.html"]:
        raise RuntimeError("Homepage changed in this release")


def preflight(release, backup_path):
    if os.geteuid() or platform.machine() != "x86_64":
        raise RuntimeError("Requires root on linux/amd64")
    lock = json.loads((release / "round14-release-lock.json").read_text())
    if lock["applicationCommit"] != "ecee142" or lock["architecture"] != "amd64":
        raise RuntimeError("Release commit or architecture changed")
    verify_overlay(release, lock)
    archive = release / "round14-evidence/auth-amd64.tar"
    if sha(archive) != lock["authArchiveSHA256"]:
        raise RuntimeError("Candidate image archive hash mismatch")
    image = json.loads(engine.run(["docker", "image", "inspect", lock["authImageId"]],
                                  output=False).stdout)[0]
    if image["Id"] != lock["authImageId"] or image["Architecture"] != "amd64":
        raise RuntimeError("Candidate Auth image identity mismatch")
    for filename in ("app.py", "buyer_service.py", "trade_service.py", "seo_service.py", "catalog.json"):
        actual = engine.run(["docker", "run", "--rm", "--network", "none", "--read-only",
                             lock["authImageId"], "sha256sum", "/app/" + filename],
                            output=False).stdout.split()[0]
        if actual != sha(release / "round14-evidence/auth-source" / filename):
            raise RuntimeError(f"Image source mismatch: {filename}")
    engine.compose(release, "config", "-q")
    engine.compose(BASELINE, "config", "-q")
    refs = engine.compose(release, "config", "--images").stdout.splitlines()
    if lock["authImageId"] not in refs or not any(lock["webImageId"] in ref for ref in refs):
        raise RuntimeError("Candidate Compose does not pin tested images")
    auth, web = engine.container("autolink-demo-auth-1"), engine.container("autolink-demo-web-1")
    if (auth["Image"], web["Image"]) != (lock["baselineAuthImageId"], lock["webImageId"]):
        raise RuntimeError("Production image changed")
    auth_mounts = {mount["Destination"]: mount["Source"] for mount in auth["Mounts"]}
    web_mounts = {mount["Destination"]: mount["Source"] for mount in web["Mounts"]}
    if (auth_mounts.get("/srv") != str(BASELINE / "site")
            or web_mounts.get("/srv") != str(BASELINE / "site")
            or web_mounts.get("/etc/caddy/Caddyfile") != str(BASELINE / "Caddyfile")):
        raise RuntimeError("Production site or Caddy mount changed")
    engine.health("autolink-demo-auth-1", lock["baselineAuthImageId"], time.monotonic() + 10)
    engine.health("autolink-demo-web-1", lock["webImageId"], time.monotonic() + 10)
    backup = json.loads(backup_path.read_text())
    if (backup.get("backupRoot") != BACKUP_POINTER.read_text().strip()
            or not backup.get("isolatedRestoreVerified")):
        raise RuntimeError("Backup pointer or restore proof differs")
    root = Path(backup["backupRoot"])
    age = time.time() - datetime.fromisoformat(backup["createdAtUTC"]).timestamp()
    if age < 0 or age > 15 * 60:
        raise RuntimeError("Production backup is older than 15 minutes")
    if (backup["sqliteSource"] != auth_mounts.get("/data") + "/autolink-auth.sqlite3"
            or sha(backup["sqliteBackup"]) != backup["sqliteSHA256"]
            or sha(backup["publicCatalog"]) != backup["publicCatalogSHA256"]):
        raise RuntimeError("Production backup source or hash mismatch")
    if (root / "restore-verify.exit").read_text().strip() != "exit=0":
        raise RuntimeError("Backup restore verification failed")
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=root,
                   check=True, capture_output=True, text=True)
    for filename in ("native-backend-tests.log", "native-rollback-rehearsal.jsonl",
                     "native-image-scan.json", "browser-qa-chrome.json", "browser-qa-webkit.json",
                     "native-catalog-http-qa.json", "native-home-integration.log"):
        if not (release / "round14-evidence" / filename).is_file():
            raise RuntimeError(f"Missing QA evidence: {filename}")
    if not json.loads((release / "round14-evidence/native-catalog-http-qa.json").read_text())["pass"]:
        raise RuntimeError("297-page isolated HTTP QA failed")
    scan = json.loads((release / "round14-evidence/native-image-scan.json").read_text())
    blocking = [finding for result in scan.get("Results", [])
                for finding in result.get("Vulnerabilities", [])
                if finding.get("Severity") in ("HIGH", "CRITICAL")]
    secrets = [finding for result in scan.get("Results", [])
               for finding in result.get("Secrets", [])]
    if blocking or secrets:
        raise RuntimeError("Candidate image security scan has blocking findings")
    for browser in ("chrome", "webkit"):
        checks = json.loads((release / "round14-evidence" / f"browser-qa-{browser}.json").read_text())
        if len(checks) != 5 or any(item.get("jsErrors", 0) for item in checks):
            raise RuntimeError(f"Isolated {browser} browser QA incomplete")
    if (release / "round14-evidence/native-home-integration.log").read_text().splitlines()[-1] != "ROUND11_HOME_INTEGRATION_OK":
        raise RuntimeError("Native homepage regression QA failed")
    phases = [json.loads(line) for line in
              (release / "round14-evidence/native-rollback-rehearsal.jsonl").read_text().splitlines()]
    if ([item["phase"] for item in phases] != ["candidate", "rollback", "restored_candidate"]
            or any(item["sqliteIntegrity"] != "ok" or item["databaseModels"] != 270
                   or item["databaseBrands"] != 60 for item in phases)):
        raise RuntimeError("Native rollback rehearsal incomplete")
    if "OK (skipped=5)" not in (release / "round14-evidence/native-backend-tests.log").read_text():
        raise RuntimeError("Native backend suite incomplete")
    current = public_catalog()
    saved = json.loads(Path(backup["publicCatalog"]).read_text())
    if current != saved:
        raise RuntimeError("Public catalog changed since fresh backup")
    engine.run(["docker", "run", "--rm", "--entrypoint", "caddy", "-e", "SITE_ADDRESS=localhost",
                "-v", str(release / "Caddyfile") + ":/etc/caddy/Caddyfile:ro", lock["webImageId"],
                "validate", "--config", "/etc/caddy/Caddyfile"], timeout=20)
    print(engine.now(), "ROUND14_PREFLIGHT_OK", json.dumps({"publicModels": 244,
          "publicBrands": 53, "authImage": lock["authImageId"]}), flush=True)
    return {"authImageID": lock["authImageId"], "oldAuthImageID": lock["baselineAuthImageId"],
            "webImageID": lock["webImageId"]}, backup


def core_probe(backup, candidate):
    if engine.http("/healthz")[0] != 200:
        raise RuntimeError("Public HTTPS health failed")
    current = public_catalog()
    saved = json.loads(Path(backup["publicCatalog"]).read_text())
    for kind in ("models", "brands"):
        original = {item["id"] for item in saved[kind]}
        latest = {item["id"] for item in current[kind]}
        if (not candidate and current[kind] != saved[kind]) or (candidate and not original <= latest):
            raise RuntimeError(f"Production {kind} lost backed-up records")
    for path, expected in (("/", 200), ("/buyer/login", 200), ("/trade/models", 200),
                           ("/trade/brands", 200), ("/supplier", 200), ("/admin", 200),
                           ("/robots.txt", 200), ("/autolink/admin/users", 401),
                           ("/autolink/buyer/requests?page=1", 401),
                           ("/trade/models/not-a-current-model", 404)):
        if engine.http(path)[0] != expected:
            raise RuntimeError(f"Core HTTP route failed: {path}")
    status, detail = engine.http("/trade/models/geely-monjaro-2026?lang=en")
    if status != 200 or "Geely Monjaro" not in detail or "index, follow" not in detail:
        raise RuntimeError("English model SSR or index failed")
    status, brand = engine.http("/trade/brands/geely?lang=en")
    if status != 200 or "<h1>Geely</h1>" not in brand:
        raise RuntimeError("English brand SSR failed")
    if "noindex" not in engine.http("/trade/models/aeolus-catalog-1?lang=en")[1]:
        raise RuntimeError("Unreviewed model lost noindex")
    for child, minimum in (("models-1.xml", 227), ("brands-1.xml", 10)):
        status, xml = engine.http("/sitemaps/" + child)
        urls = list(ElementTree.fromstring(xml).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}url"))
        if status != 200 or len(urls) < minimum:
            raise RuntimeError(f"Sitemap regressed: {child}")
    print(engine.now(), "ROUND14_CORE_PROBE_OK", json.dumps({"candidate": candidate,
          "publicModels": len(current["models"]), "publicBrands": len(current["brands"])}), flush=True)


engine.preflight = preflight
engine.core_probe = core_probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare-backup", "preflight", "cutover", "status"))
    parser.add_argument("--release", type=Path,
                        default=Path("/opt/autolink-releases/ecee142-round14-20261013"))
    parser.add_argument("--backup-manifest", type=Path)
    args = parser.parse_args()
    release = args.release.resolve()
    if args.mode == "prepare-backup":
        prepare_backup_manifest()
    elif args.mode == "status":
        path = STATE_ROOT / release.name / "status.json"
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if not args.backup_manifest:
            parser.error("--backup-manifest is required")
        if args.mode == "preflight":
            preflight(release, args.backup_manifest)
        else:
            engine.cutover(release, args.backup_manifest)


if __name__ == "__main__":
    main()
