#!/usr/bin/env python3
"""Install only the pinned, checksum-verified official Linux CI binaries."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        parser.error('This installer is only for the Linux x64 CI runner; use official native installers locally.')
    root = Path(__file__).resolve().parent.parent
    destination = Path(args.destination).resolve()
    if destination == root or root in destination.parents:
        parser.error('Install tools outside the source checkout.')
    manifest = json.loads((root / 'security/tool-versions.json').read_text())
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='autolink-tools-') as temp:
        for name, specification in manifest.items():
            url = specification['linux_x64_url']
            expected_prefix = {'gitleaks':'https://github.com/gitleaks/gitleaks/releases/download/',
                               'trivy':'https://github.com/aquasecurity/trivy/releases/download/'}[name]
            if not url.startswith(expected_prefix):
                raise RuntimeError('Tool download is not an approved official release URL.')
            archive = Path(temp) / (name + '.tar.gz')
            request = urllib.request.Request(url, headers={'User-Agent':'AUTOLINK-security-CI'})
            with urllib.request.urlopen(request, timeout=120) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != specification['sha256']:
                raise RuntimeError('Official binary checksum does not match the reviewed manifest.')
            # Extract exactly one regular binary; never trust arbitrary archive paths.
            with tarfile.open(archive, 'r:gz') as package:
                member = package.getmember(name)
                if not member.isfile():
                    raise RuntimeError('Expected binary is not a regular file.')
                binary = destination / name
                with package.extractfile(member) as source, binary.open('wb') as output:
                    shutil.copyfileobj(source, output)
                os.chmod(binary, 0o700)
            print(name + ' ' + specification['version'] + ': official archive SHA256 verified')


if __name__ == '__main__':
    main()
