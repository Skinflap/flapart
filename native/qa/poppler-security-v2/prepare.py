#!/usr/bin/env python3
"""Prepare pinned Poppler and its reviewed upstream fixes in a new private directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
RECEIPT = json.loads((ROOT / 'receipt.json').read_text())
ARCHIVE_SHA = RECEIPT['archive_sha256']
PATCH_SHA = RECEIPT['patch_sha256']


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
    if sha(archive) != ARCHIVE_SHA or sha(ROOT / 'security.patch') != PATCH_SHA:
        raise ValueError('Source archive or patch does not match reviewed input')
    work.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(work, filter='data')
    source = work / 'poppler-26.04.0'
    for entry in RECEIPT['changes']:
        if sha(source / entry['path']) != entry['before_sha256']:
            raise ValueError('Unexpected original source: ' + entry['path'])
    before = inventory(source)
    for args in (['--check'], []):
        subprocess.run(['git', 'apply', *args, str(ROOT / 'security.patch')], cwd=source, check=True)
    for entry in RECEIPT['changes']:
        if sha(source / entry['path']) != entry['after_sha256']:
            raise ValueError('Unexpected patched source: ' + entry['path'])
    after = inventory(source)
    changed = [b['path'] for a, b in zip(before, after) if a != b]
    if len(before) != len(after) or changed != sorted(entry['path'] for entry in RECEIPT['changes']):
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
