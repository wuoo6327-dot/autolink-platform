"""Create and restore-check a complete private brand SEO cutover backup.

Reads the running production mounts instead of guessing Docker volume paths.
Never edits the live database or volumes. Run as root on the AMD64 host.
"""

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backup_production_sqlite import verify as verify_sqlite


BASE = Path("/opt/autolink-backups/brand-identity-20261012")
OLD = Path("/opt/autolink-releases/5725b8b-seo-20261012")
OLD_AUTH = "sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815"
WEB = "sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb"


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def command(*args, timeout=120):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def inspect(name):
    data = json.loads(command("docker", "inspect", name, timeout=15))
    if len(data) != 1:
        raise RuntimeError(f"Missing production container {name}")
    return data[0]


def mount(container, destination):
    matches = [Path(item["Source"]) for item in container["Mounts"] if item["Destination"] == destination]
    if len(matches) != 1 or not matches[0].exists():
        raise RuntimeError(f"Expected one live mount at {destination}")
    return matches[0]


def members(root, exclude=()):
    if root.is_file():
        return {root.name: ("file", sha(root))}
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(relative == name or relative.startswith(name + "/") for name in exclude):
            continue
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", sha(path))
    return result


def save_tree(root, output, exclude=()):
    before = members(root, exclude)
    with tarfile.open(output, "w:gz") as archive:
        if root.is_file():
            archive.add(root, arcname=root.name, recursive=False)
        else:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root).as_posix()
                if any(relative == name or relative.startswith(name + "/") for name in exclude):
                    continue
                archive.add(path, arcname=relative, recursive=False)
    with tempfile.TemporaryDirectory(prefix="autolink-restore-", dir=output.parent) as location:
        with tarfile.open(output, "r:gz") as archive:
            archive.extractall(location, filter="data")
        restored = members(Path(location))
    after = members(root, exclude)
    if before != restored or before != after:
        raise RuntimeError(f"Isolated restore differs from live source: {root}")
    return {"archive": str(output), "sha256": sha(output), "files": len(before), "restored": True}


def public_catalog():
    def fetch(path):
        raw = command("curl", "-fsS", "--max-time", "10", "--resolve",
                      "autolinkglobal.com:443:127.0.0.1", "https://autolinkglobal.com" + path, timeout=12)
        return json.loads(raw)["data"]
    models = fetch("/autolink/public/models?limit=500")
    brands = fetch("/autolink/public/brands")
    if not models or not brands:
        raise RuntimeError("Current public catalog is empty")
    return models, brands


def main():
    if os.geteuid() != 0 or platform.machine() != "x86_64":
        raise RuntimeError("Requires root on the reviewed linux/amd64 production host")
    os.umask(0o077)
    BASE.mkdir(parents=True, mode=0o700, exist_ok=True)
    if BASE.stat().st_mode & 0o077:
        raise RuntimeError("Private backup root must be root-only")
    if shutil.disk_usage("/").free < 2 * 1024**3:
        raise RuntimeError("Less than 2 GiB available for full backup")
    auth = inspect("autolink-demo-auth-1")
    web = inspect("autolink-demo-web-1")
    if auth["Image"] != OLD_AUTH or web["Image"] != WEB:
        raise RuntimeError("Production image IDs changed before backup")
    if auth["State"].get("Health", {}).get("Status") != "healthy":
        raise RuntimeError("Production auth is not healthy")
    auth_data = mount(auth, "/data")
    caddy_data = mount(web, "/data")
    caddy_config = mount(web, "/config")
    if mount(web, "/srv") != OLD / "site" or mount(web, "/etc/caddy/Caddyfile") != OLD / "Caddyfile":
        raise RuntimeError("Production site/config mounts differ from baseline")
    source = auth_data / "autolink-auth.sqlite3"
    if not source.is_file():
        raise RuntimeError("True production SQLite source is missing")
    models, brands = public_catalog()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BASE / ("final-" + timestamp)
    destination.mkdir(mode=0o700)
    sqlite_result = json.loads(command("python3", str(Path(__file__).with_name("backup_production_sqlite.py")),
                                       str(source), str(destination), timeout=60))
    snapshot = Path(sqlite_result["backup"])
    if not sqlite_result["isolatedRestoreVerified"] or verify_sqlite(snapshot)["integrity"] != "ok":
        raise RuntimeError("SQLite isolated restore did not pass")
    if sqlite_result["sqlite"]["models"] < len(models) or sqlite_result["sqlite"]["brands"] < len(brands):
        raise RuntimeError("Database totals are smaller than the public catalog")
    files = {
        "authNonDatabase": save_tree(auth_data, destination / "auth-data-nondb.tar.gz",
                                     exclude=("autolink-auth.sqlite3", "autolink-auth.sqlite3-wal", "autolink-auth.sqlite3-shm")),
        "caddyData": save_tree(caddy_data, destination / "caddy-data.tar.gz"),
        "caddyConfig": save_tree(caddy_config, destination / "caddy-config.tar.gz"),
        "oldRelease": save_tree(OLD, destination / "old-release.tar.gz"),
    }
    images = {}
    for label, image_id in (("oldAuth", OLD_AUTH), ("oldWeb", WEB)):
        archive = destination / (label + ".tar")
        command("docker", "save", "--output", str(archive), image_id, timeout=180)
        images[label] = {"imageID": image_id, "archive": str(archive), "sha256": sha(archive)}
        if not archive.is_file() or archive.stat().st_size < 1024:
            raise RuntimeError("Old image archive is incomplete")
    catalog = destination / "current-public-catalog.json"
    catalog.write_text(json.dumps({"models": models, "brands": brands}, sort_keys=True) + "\n")
    state = destination / "production-state.json"
    state.write_text(json.dumps({
        "auth": {"imageID": auth["Image"], "status": auth["State"]["Status"],
                 "health": auth["State"].get("Health", {}).get("Status"),
                 "readOnlyRootfs": auth["HostConfig"].get("ReadonlyRootfs"),
                 "capDrop": auth["HostConfig"].get("CapDrop")},
        "web": {"imageID": web["Image"], "status": web["State"]["Status"],
                "readOnlyRootfs": web["HostConfig"].get("ReadonlyRootfs"),
                "capDrop": web["HostConfig"].get("CapDrop")},
    }, sort_keys=True, indent=2) + "\n")
    result = {
        "createdAtUTC": datetime.now(timezone.utc).isoformat(),
        "sqliteSource": str(source), "sqliteBackup": str(snapshot),
        "sqliteSHA256": sha(snapshot), "databaseModels": sqlite_result["sqlite"]["models"],
        "databaseBrands": sqlite_result["sqlite"]["brands"],
        "publicModels": len(models), "publicBrands": len(brands), "publicCatalog": str(catalog),
        "publicCatalogSHA256": sha(catalog), "productionState": str(state),
        "files": files, "images": images, "isolatedRestoreVerified": True,
    }
    manifest = destination / "release-backup-manifest.json"
    manifest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    with manifest.open("rb") as handle:
        os.fsync(handle.fileno())
    print(json.dumps({"manifest": str(manifest), "sqliteBackup": str(snapshot),
                      "sqliteSHA256": result["sqliteSHA256"], "publicModels": len(models),
                      "publicBrands": len(brands), "databaseModels": result["databaseModels"],
                      "databaseBrands": result["databaseBrands"],
                      "isolatedRestoreVerified": True}, sort_keys=True))


if __name__ == "__main__":
    main()
