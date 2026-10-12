"""Verify a local Docker save archive against its loaded image and source commit.

This is a same-host, archive-based identity check. It does not produce or claim
a remote registry manifest digest and never pulls or rebuilds an image.
"""

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def digest_stream(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return "sha256:" + result.hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def copied_source_files(dockerfile):
    files = []
    for raw in dockerfile.read_text().splitlines():
        parts = raw.strip().split()
        if parts[:1] != ["COPY"] or any(part.startswith("--from=") for part in parts):
            continue
        if parts[-1] != "./":
            raise ValueError(f"Unreviewed Docker COPY form: {raw}")
        files.extend(parts[1:-1])
    if not files or len(files) != len(set(files)):
        raise ValueError("Expected a nonempty, unique list of application files")
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("image_reference")
    parser.add_argument("expected_archive_sha256")
    parser.add_argument("expected_image_id")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    if not archive.is_file():
        raise ValueError("Archive is not a regular file")
    with archive.open("rb") as handle:
        archive_digest = digest_stream(handle)
    if archive_digest != "sha256:" + args.expected_archive_sha256.removeprefix("sha256:"):
        raise ValueError("Archive SHA-256 differs from the approved value")

    with tarfile.open(archive, "r:") as image_archive:
        manifest = json.load(image_archive.extractfile("manifest.json"))
        if len(manifest) != 1:
            raise ValueError("Expected exactly one image in the archive")
        item = manifest[0]
        config_bytes = image_archive.extractfile(item["Config"]).read()
        config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        config = json.loads(config_bytes)
        layers = item["Layers"]
        diff_ids = config["rootfs"]["diff_ids"]
        if len(layers) != len(diff_ids) or not layers:
            raise ValueError("Layer list does not match config diff IDs")
        for member, expected in zip(layers, diff_ids):
            if digest_stream(image_archive.extractfile(member)) != expected:
                raise ValueError(f"Layer checksum mismatch: {member}")
        if (config["os"], config["architecture"]) != ("linux", "amd64"):
            raise ValueError("Archive is not linux/amd64")

    inspected = json.loads(run("docker", "image", "inspect", args.image_reference))
    if len(inspected) != 1:
        raise ValueError("Expected one loaded Docker image")
    loaded = inspected[0]
    if loaded["Id"] != args.expected_image_id:
        raise ValueError("Loaded image ID differs from archive")
    if (loaded["Os"], loaded["Architecture"]) != ("linux", "amd64"):
        raise ValueError("Loaded Docker image is not linux/amd64")
    descriptor = loaded.get("Descriptor") or {}
    if descriptor.get("digest") != args.expected_image_id:
        raise ValueError("Loaded image descriptor differs from approved local digest")
    if not descriptor.get("mediaType", "").endswith(".image.manifest.v1+json"):
        raise ValueError("Loaded image descriptor is not an OCI image manifest")
    if loaded.get("RootFS", {}).get("Layers") != diff_ids:
        raise ValueError("Loaded image rootfs differs from archive layers")
    manifest_bytes = subprocess.check_output([
        "ctr", "-n", "moby", "content", "get", args.expected_image_id,
    ])
    if "sha256:" + hashlib.sha256(manifest_bytes).hexdigest() != args.expected_image_id:
        raise ValueError("Local OCI manifest bytes differ from descriptor digest")
    local_manifest = json.loads(manifest_bytes)
    if local_manifest["config"]["digest"] != config_digest:
        raise ValueError("Local OCI manifest config differs from saved archive")
    if len(local_manifest["layers"]) != len(layers):
        raise ValueError("Local OCI manifest layers differ in count from archive")
    for layer in local_manifest["layers"]:
        blob = subprocess.check_output([
            "ctr", "-n", "moby", "content", "get", layer["digest"],
        ])
        if "sha256:" + hashlib.sha256(blob).hexdigest() != layer["digest"]:
            raise ValueError("Local OCI layer blob checksum mismatch")

    source_hashes = {}
    if args.source_root or args.source_commit:
        if not (args.source_root and args.source_commit):
            raise ValueError("Source root and commit must be given together")
        root = args.source_root.resolve(strict=True)
        files = copied_source_files(root / "auth" / "Dockerfile")
        code = (
            "import hashlib,json; "
            "from pathlib import Path; "
            "names=" + repr(files) + "; "
            "print(json.dumps({name:hashlib.sha256((Path('/app')/name).read_bytes()).hexdigest() "
            "for name in names},sort_keys=True))"
        )
        in_image = json.loads(run(
            "docker", "run", "--rm", "--pull", "never", "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--entrypoint", "python", args.image_reference, "-c", code,
        ))
        for name in files:
            expected = hashlib.sha256(subprocess.check_output([
                "git", "-C", str(root), "show", f"{args.source_commit}:auth/{name}",
            ])).hexdigest()
            if in_image[name] != expected:
                raise ValueError(f"Application file differs from source commit: {name}")
            source_hashes[name] = expected

    evidence = {
        "verifiedAtUTC": datetime.now(timezone.utc).isoformat(),
        "deliveryMode": "same-host-local-archive",
        "registryManifestDigest": None,
        "archive": str(archive),
        "archiveSHA256": archive_digest,
        "dockerImageID": loaded["Id"],
        "localOCIManifestDigest": descriptor["digest"],
        "localOCIManifestMediaType": descriptor["mediaType"],
        "dockerRepoDigestsLocalObservation": loaded.get("RepoDigests", []),
        "archiveConfigDigest": config_digest,
        "os": "linux",
        "architecture": "amd64",
        "verifiedLayers": len(layers),
        "sourceCommit": args.source_commit,
        "applicationFilesSHA256": source_hashes,
        "noPullOrRebuild": True,
    }
    if args.output:
        output = args.output.resolve()
        if output.exists():
            raise ValueError("Evidence output already exists")
        output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
