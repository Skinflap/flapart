#!/usr/bin/env python3
"""Prepare/build isolated Qt and retain diagnostics even when no SDK is produced.

No workflow dispatch, SDK adoption, application packaging, or publication.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(args):
    if not args.prepare_only and platform.system() != 'Darwin':
        raise ValueError('Native macOS required for compilation')
    work, evidence = args.work.absolute(), args.evidence.absolute()
    if any(p.exists() or p.is_symlink() for p in (work, evidence)):
        raise ValueError('Use fresh work/evidence directories')
    if evidence.resolve().is_relative_to(work.resolve()) or work.resolve().is_relative_to(evidence.resolve()):
        raise ValueError('Work and retained evidence must be separate')
    work.mkdir(parents=True); evidence.mkdir(parents=True)
    env = os.environ.copy(); env['GIT_TERMINAL_PROMPT'] = '0'
    result = {'prepared': False, 'compiled': False, 'universal_assembled': False,
              'runtime_qualified': False, 'release_qualified': False, 'stages': []}

    def command(name, argv):
        row = {'name': name, 'argv': [str(x) for x in argv]}
        result['stages'].append(row)
        with (evidence / (name + '.log')).open('x') as log:
            proc = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=18000)
        row['returncode'] = proc.returncode
        if proc.returncode:
            raise RuntimeError('Stage failed: ' + name)

    try:
        source = args.original_source.absolute() if args.original_source else work / 'upstream'
        if not args.original_source:
            pins = json.loads((ROOT / 'macos-source-pins.json').read_text())
            command('source-init', ['git', 'init', str(source)])
            command('source-remote', ['git', '-C', str(source), 'remote', 'add', 'origin', 'https://invent.kde.org/szaman/qt5.git'])
            command('source-fetch', ['git', '-C', str(source), 'fetch', '--depth=1', 'origin', pins['superproject']])
            command('source-checkout', ['git', '-C', str(source), 'checkout', '--detach', pins['superproject']])
            command('source-modules', ['git', '-C', str(source), '-c', 'protocol.file.allow=never',
                    'submodule', 'update', '--init', '--depth=1', '--', *[r['module'] for r in pins['modules']]])
        command('source-prepare', [sys.executable, str(ROOT / 'prepare-macos.py'),
                '--original-source', str(source), '--work', str(work / 'prepared')])
        result['prepared'] = True
        if not args.prepare_only:
            argv = [sys.executable, str(ROOT / 'build-macos.py'),
                    '--prepared', str(work / 'prepared'), '--maintained-sdk', str(args.maintained_sdk.absolute()),
                    '--work', str(work / 'build'), '--jobs', str(args.jobs)]
            if args.reviewed_text:
                argv += ['--reviewed-text', str(args.reviewed_text.absolute())]
            command('qt-build', argv)
            built = json.loads((work / 'build/evidence/result.json').read_text())
            result.update(compiled=built['compiled'], universal_assembled=built['universal_assembled'])
    finally:
        build_result = work / 'build/evidence/result.json'
        if build_result.is_file() and not build_result.is_symlink():
            observed = json.loads(build_result.read_text())
            result.update(compiled=observed['compiled'], universal_assembled=observed['universal_assembled'])
        # Explicit diagnostic roots only: never sweep build trees or native payloads.
        for source_root, target_root, names in (
            (work / 'prepared', evidence / 'source', ('preparation.json', 'security-application.json', 'prepared-source-manifest.json')),
            (work / 'build/evidence', evidence / 'build', None),
        ):
            if not source_root.exists():
                continue
            if source_root.is_symlink():
                raise ValueError('Unsafe evidence root')
            selected = [source_root / name for name in names] if names else list(source_root.iterdir())
            for path in selected:
                if not path.exists():
                    continue
                if path.is_symlink() or not path.is_file() or path.suffix not in {'.json', '.log'}:
                    raise ValueError('Unexpected diagnostic entry')
                target_root.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target_root / path.name)
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--maintained-sdk', type=Path)
    parser.add_argument('--original-source', type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--reviewed-text', type=Path,
                        help='Exact-hash reviewed architecture metadata differences, never inferred automatically')
    args = parser.parse_args()
    if not args.prepare_only and not args.maintained_sdk:
        parser.error('--maintained-sdk is required for native builds')
    print(json.dumps(run(args), indent=2))
