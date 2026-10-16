#!/usr/bin/env python3
"""Strictly assemble two staged Qt installations; never adopt or publish them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

MAGIC = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe',
         b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
         b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca', b'!<ar'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Input root must be an actual directory')
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = path.readlink()
            if target.is_absolute() or not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise ValueError('Unsafe or dangling link: ' + name)
            result[name] = {'kind': 'link', 'target': str(target)}
        elif path.is_dir():
            result[name] = {'kind': 'directory'}
        elif path.is_file():
            with path.open('rb') as stream:
                native = stream.read(4) in MAGIC
            result[name] = {'kind': 'native' if native else 'file', 'sha256': sha(path),
                            'mode': path.stat().st_mode & 0o777}
        else:
            raise ValueError('Unsupported filesystem entry: ' + name)
    return result


def archs(lipo, path):
    return set(subprocess.check_output([lipo, '-archs', str(path)], text=True).split())


def merge(arm, intel, output, evidence, lipo, review=None):
    arm, intel, output, evidence = (p.absolute() for p in (arm, intel, output, evidence))
    if output.exists() or output.is_symlink() or evidence.exists() or evidence.is_symlink():
        raise ValueError('Use fresh output and evidence paths')
    if evidence.resolve().is_relative_to(output.resolve()):
        raise ValueError('Evidence must be outside assembled output')
    for root in (arm, intel):
        if output.resolve().is_relative_to(root.resolve()) or evidence.resolve().is_relative_to(root.resolve()):
            raise ValueError('Output/evidence must be outside retained inputs')
    a, b = inventory(arm), inventory(intel)
    reviewed = json.loads(review.read_text()) if review else {}
    used = set()
    conflicts = []
    for name in sorted(a.keys() | b.keys()):
        x, y = a.get(name), b.get(name)
        if not x or not y or x['kind'] != y['kind']:
            conflicts.append({'path': name, 'reason': 'missing entry or different entry type'})
            continue
        if x['kind'] == 'native':
            if x['mode'] != y['mode'] or archs(lipo, arm / name) != {'arm64'} or archs(lipo, intel / name) != {'x86_64'}:
                conflicts.append({'path': name, 'reason': 'native mode or CPU mismatch'})
        elif x != y:
            approval = reviewed.get(name)
            permitted = Path(name).suffix in {'.pri', '.prl', '.pc', '.cmake'} or Path(name).name == 'qconfig.h'
            if (x['kind'] == 'file' and permitted and approval and approval.get('reason')
                and approval.get('arm64_sha256') == x['sha256']
                and approval.get('x86_64_sha256') == y['sha256']
                and approval.get('select') in {'arm64', 'x86_64'} and x['mode'] == y['mode']):
                (arm / name).read_text(); (intel / name).read_text()
                used.add(name)
            else:
                conflicts.append({'path': name, 'reason': 'unreviewed non-native difference', 'arm64': x, 'x86_64': y})
    if used != set(reviewed):
        conflicts.append({'reason': 'unused or stale review entries', 'paths': sorted(set(reviewed) - used)})
    result = {'assembled': False, 'runtime_qualified': False, 'release_qualified': False,
              'conflicts': conflicts, 'review_sha256': sha(review) if review else None,
              'inputs': {'arm64': a, 'x86_64': b}}
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if conflicts:
        evidence.write_text(json.dumps(result, indent=2) + '\n')
        raise ValueError('Assembly refused; inspect conflict evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.qt-universal-', dir=output.parent) as temporary:
            stage = Path(temporary) / 'installation'
            stage.mkdir()
            for name, row in a.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if row['kind'] == 'directory':
                    target.mkdir(exist_ok=True)
                elif row['kind'] == 'link':
                    target.symlink_to(row['target'])
                elif row['kind'] == 'native':
                    subprocess.run([lipo, '-create', str(arm / name), str(intel / name), '-output', str(target)], check=True)
                    if archs(lipo, target) != {'arm64', 'x86_64'}:
                        raise ValueError('Combined architecture mismatch: ' + name)
                    for cpu, original in [('arm64', arm / name), ('x86_64', intel / name)]:
                        thin = Path(temporary) / ('verify-' + cpu)
                        subprocess.run([lipo, str(target), '-thin', cpu, '-output', str(thin)], check=True)
                        if sha(thin) != sha(original):
                            raise ValueError('Combined slice bytes changed: ' + name)
                        thin.unlink()
                    os.chmod(target, row['mode'])
                else:
                    selected = intel if name in used and reviewed[name]['select'] == 'x86_64' else arm
                    shutil.copy2(selected / name, target)
            if inventory(arm) != a or inventory(intel) != b:
                raise ValueError('Inputs changed during assembly')
            result['outputs'] = inventory(stage)
            stage.rename(output)
            result['assembled'] = True
    finally:
        evidence.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('arm64', 'x86-64', 'output', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reviewed-text', type=Path)
    parser.add_argument('--lipo', default='lipo')
    args = parser.parse_args()
    merge(args.arm64, args.x86_64, args.output, args.evidence, args.lipo, args.reviewed_text)
