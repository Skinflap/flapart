#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mac collector command and optional actual-stage recording orchestration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RECORDER = HERE.parents[1] / 'distribution/provenance/stage_recorder.py'


def validate_evidence(output, evidence, retain):
    if retain and evidence is None:
        raise ValueError('--retain-native-bytes requires --stage-evidence')
    if evidence is None:
        return
    output, evidence = Path(output).resolve(), Path(evidence).absolute()
    resolved = evidence.resolve()
    if resolved.is_relative_to(output) or output.is_relative_to(resolved):
        raise ValueError('Stage evidence must be outside candidate output')
    if evidence.exists() or evidence.is_symlink():
        raise ValueError('Stage evidence directory must be fresh')


def stage_command(stage, command, root, evidence, helpers=(), tools=(), retain=False, env=None, sdk=None):
    if evidence is None:
        if retain: raise ValueError('Byte retention requires stage evidence')
        return list(map(str, command))
    search = (env or os.environ).get('PATH', os.defpath)
    args = [sys.executable, str(RECORDER), '--stage', stage, '--cwd', str(HERE),
            '--tree', 'package=' + str(Path(root).absolute()), '--evidence', str(Path(evidence) / stage)]
    if sdk is not None:
        args.extend(['--tree', 'sdk=' + str(Path(sdk).absolute())])
    for helper in [Path(__file__).resolve(), *helpers]:
        args.extend(['--helper', str(Path(helper).resolve(strict=True))])
    for tool in tools:
        actual = shutil.which(str(tool), path=search)
        if actual is None: raise ValueError('Missing package tool: ' + str(tool))
        args.extend(['--tool', actual])
    if retain: args.append('--retain-native-bytes')
    return args + ['--', *map(str, command)]


def run_stage(stage, command, root, evidence, helpers=(), tools=(), retain=False, env=None, sdk=None):
    subprocess.run(stage_command(stage, command, root, evidence, helpers, tools, retain, env, sdk),
                   env=env, check=True)


def sdk_identity(root):
    rows = []
    if not root.is_dir() or root.is_symlink(): raise ValueError('SDK must be a regular directory')
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink(): rows.append((rel, 'link', os.readlink(path)))
        elif path.is_file():
            with path.open('rb') as stream: value = hashlib.file_digest(stream, 'sha256').hexdigest()
            rows.append((rel, 'file', path.stat().st_size, path.stat().st_mode, value))
        elif path.is_dir(): rows.append((rel, 'directory'))
        else: raise ValueError('Unsupported SDK entry')
    return rows


def collect(source, prefix, output):
    """Recordable collector + application rename/plist update as one actual command."""
    source, prefix, output = map(Path, (source, prefix, output))
    if any(output.iterdir()): raise ValueError('Collector output must be empty')
    before = sdk_identity(prefix)
    subprocess.run([sys.executable, str(source / 'packaging/macos/macos-deploy.py'),
                    '--install-dir', str(prefix), '--output-dir', str(output),
                    '--krita-source', str(source)], check=True)
    after = sdk_identity(prefix)
    if after != before: raise ValueError('Collector changed SDK inputs')
    print(json.dumps({'sdk_unchanged': True, 'sdk_regular_bytes': sum(row[2] for row in before if row[1] == 'file')}))
    apps = list(output.glob('*.app'))
    if len(apps) != 1 or apps[0].is_symlink(): raise ValueError('Expected one regular app bundle')
    root = output / 'Flapart Studio.app'
    if apps[0] != root: apps[0].rename(root)
    plist = root / 'Contents/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(CFBundleIdentifier='com.flaptown.flapart-native', CFBundleName='Flapart Studio', CFBundleDisplayName='Flapart Studio')
    plist.write_bytes(plistlib.dumps(info))
    if not (root / 'Contents/MacOS/krita').is_file(): raise ValueError('Collector omitted executable')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); collect(a.source, a.prefix, a.output)
