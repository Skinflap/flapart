#!/usr/bin/env python3
"""Prepare pinned OpenEXR and its upstream checker fix in a new private directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
ARCHIVE_SHA = 'fbe1213a23df988ff4baaa16e6d4576ad6e615fe6eaa6ff607f5a7f1fa13ada1'
PATCH_SHA = 'ffad7e1be2493ff7c5e201f5a2c1240a610bd9b6d09d4ad0237b4d18ea27e6a9'
TARGET = 'src/lib/OpenEXRUtil/ImfCheckFile.cpp'
BEFORE = '745f7377794904fbe362bbd4bdf7bd5527c2de9072da6361e9f78bb2a299f6b4'
AFTER = '48b68e0fbab0644bf027f74251e2113f1ea311f9f6fc665eea964b8c350029ef'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(source):
    entries = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            entries.append({'path': str(path.relative_to(source)), 'link': str(path.readlink())})
        elif path.is_file():
            entries.append({'path': str(path.relative_to(source)), 'sha256': sha(path)})
    return entries


def prepare(archive, work):
    archive, work = archive.absolute(), work.absolute()
    if work.exists() or work.is_symlink():
        raise ValueError('Use a new private work directory')
    if any(p.is_symlink() for p in (archive, *archive.parents, *work.parents)):
        raise ValueError('Symlink input or destination parent refused')
    if sha(archive) != ARCHIVE_SHA or sha(ROOT / 'checker.patch') != PATCH_SHA:
        raise ValueError('Source archive or patch does not match reviewed input')
    work.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(work, filter='data')
    source = work / 'openexr-3.4.16'
    if sha(source / TARGET) != BEFORE:
        raise ValueError('Unexpected original checker source')
    before = inventory(source)
    for args in (['--check'], []):
        subprocess.run(['git', 'apply', *args, str(ROOT / 'checker.patch')], cwd=source, check=True)
    if sha(source / TARGET) != AFTER:
        raise ValueError('Patched checker does not match upstream')
    after = inventory(source)
    changed = [b['path'] for a, b in zip(before, after) if a != b]
    if len(before) != len(after) or changed != [TARGET]:
        raise ValueError('Unexpected source changes')
    manifest = work / 'source-manifest.json'
    manifest.write_text(json.dumps(after, indent=2) + '\n')
    result = {'source': str(source), 'archive_sha256': ARCHIVE_SHA,
              'patch_sha256': PATCH_SHA, 'source_manifest_sha256': sha(manifest),
              'files_and_links': len(after), 'changed_files': changed,
              'prepared': True, 'native_compiled': False, 'release_qualified': False}
    (work / 'preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.archive, args.work), indent=2))
