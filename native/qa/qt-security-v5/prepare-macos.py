#!/usr/bin/env python3
"""Export pinned Qt source and apply reviewed fixes in a fresh private directory.

Uses git archives, never a working-tree copy: untracked/generated files cannot
silently become build inputs. No SDK changes, build dispatch, or release action.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
PLATFORM_SHA = '3030bd3a0043924b269c465372ab115330c9819e355c7f3bec34146ceb60fcda'
PINS_SHA = '283dec8fc2fa1e68cab5d5db3522134302d1ed6c2514580f259b280e3b43ec14'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(original, work):
    original = Path(original).resolve(strict=True)
    work = Path(work).absolute()
    if work.exists() or work.is_symlink():
        raise ValueError('Use a fresh private work directory')
    if work.resolve().is_relative_to(original):
        raise ValueError('Work must be outside retained source')
    if sha(ROOT / 'macos-source-pins.json') != PINS_SHA:
        raise ValueError('Source pins changed')
    pins = json.loads((ROOT / 'macos-source-pins.json').read_text())
    if pins['superproject'] != '2d0ea49d3428d639d45e7b1a32bbe0d096ed8b8e':
        raise ValueError('Unexpected source root pin')
    platform_patch = ROOT / 'macos-platform.patch'
    if sha(platform_patch) != PLATFORM_SHA:
        raise ValueError('Platform patch changed')
    repositories = [('', pins['superproject'])] + [(r['module'], r['gitlink']) for r in pins['modules']]
    for module, revision in repositories:
        repo = original / module
        if git(repo, 'rev-parse', 'HEAD') != revision:
            raise ValueError('Unexpected source revision: ' + module)
        if git(repo, 'status', '--porcelain', '--untracked-files=no'):
            raise ValueError('Tracked source changes: ' + module)
        if module and git(original, 'ls-tree', 'HEAD', module).split()[2] != revision:
            raise ValueError('Module differs from pinned superproject')
    work.mkdir(parents=True)
    source = work / 'source'
    source.mkdir()
    archives = work / 'input-archives'
    archives.mkdir()
    inputs = []
    for module, revision in repositories:
        archive = archives / ((module or 'qt5') + '.tar')
        subprocess.run(['git', '-C', str(original / module), 'archive', '--format=tar',
                        '--output=' + str(archive), revision], check=True)
        destination = source / module
        destination.mkdir(exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(destination, filter='data')
        inputs.append({'module': module or 'qt5', 'revision': revision,
                       'archive_sha256': sha(archive)})
    spec = importlib.util.spec_from_file_location('reviewed_source', ROOT / 'apply.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.apply(source, work / 'security-application.json')
    mac_conf = source / 'qtbase/mkspecs/common/mac.conf'
    before = sha(mac_conf)
    subprocess.run(['git', 'apply', '--check', str(platform_patch)], cwd=source / 'qtbase', check=True)
    subprocess.run(['git', 'apply', str(platform_patch)], cwd=source / 'qtbase', check=True)
    manifest = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            manifest.append({'path': str(path.relative_to(source)), 'link': str(path.readlink())})
        elif path.is_file():
            manifest.append({'path': str(path.relative_to(source)), 'sha256': sha(path),
                             'executable': bool(path.stat().st_mode & 0o111)})
    manifest_path = work / 'prepared-source-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    result = {'prepared': True, 'compiled': False, 'release_qualified': False,
              'prepared_source_manifest_sha256': sha(manifest_path),
              'inputs': inputs, 'security_receipt_sha256': helper.RECEIPT_SHA,
              'platform_patch_sha256': PLATFORM_SHA,
              'platform_source_before': before, 'platform_source_after': sha(mac_conf),
              'source': str(source), 'architectures': ['arm64', 'x86_64']}
    (work / 'preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.original_source, args.work), indent=2))
