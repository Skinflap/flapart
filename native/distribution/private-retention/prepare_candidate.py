#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare and verify explicit private candidate retention inputs; never encrypt/upload."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
chain = load('private_candidate_chain', HERE.parent / 'provenance/verify_chain.py')
retention = load('private_candidate_retention', HERE / 'retain.py')
LIMIT = retention.LIMIT
MAX_FILES = retention.MAX_FILES
GENERATED = ('chain-manifest.json', 'chain-result.json', 'preparation.json')


def check(ok, message):
    if not ok:
        raise ValueError(message)


def regular(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        check(not part.is_symlink(), 'Input/output symlink forbidden')
    check(path.is_file() and stat.S_ISREG(path.stat().st_mode), 'Expected regular input file')
    return path


def identity(path):
    path = regular(path)
    before = path.stat()
    value = chain.sha(path)
    after = path.stat()
    key = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    check(key(before) == key(after), 'Input changed while hashing')
    return {'bytes': after.st_size, 'sha256': value}, key(after)


def overlaps(left, right):
    left, right = left.resolve(), right.resolve()
    return left.is_relative_to(right) or right.is_relative_to(left)


def inputs(candidate, inventory, stages, qualifications, output):
    candidate, inventory = regular(candidate), regular(inventory)
    stages = Path(stages).absolute()
    output = Path(output).absolute()
    check(stages.is_dir() and not stages.is_symlink(), 'Expected stage evidence directory')
    for part in (stages, *stages.parents, output, *output.parents):
        check(not part.is_symlink(), 'Input/output symlink forbidden')
    check(not output.exists(), 'Output must be fresh')
    check(output.parent.is_dir(), 'Output parent must exist')
    check(not overlaps(output, stages), 'Output overlaps stage inputs')
    children = list(stages.iterdir())
    check({p.name for p in children} == set(chain.STAGES) and all(p.is_dir() and not p.is_symlink() for p in children), 'Expected exactly four known stage directories')
    result = [('candidate.zip', candidate), ('candidate-inventory.json', inventory)]
    for stage in chain.STAGES:
        folder = stages / stage
        entries = list(folder.iterdir())
        check({p.name for p in entries} == {'receipt.json', 'before.json', 'stdout.log', 'stderr.log', 'native-bytes'}, 'Unexpected or missing stage evidence entry')
        blobs = folder / 'native-bytes'
        check(blobs.is_dir() and not blobs.is_symlink(), 'Expected retained native-byte directory')
        for file in sorted(folder.rglob('*')):
            check(not file.is_symlink(), 'Stage evidence symlink forbidden')
            if file.is_dir():
                check(file == blobs, 'Unexpected nested stage directory')
                continue
            regular(file)
            rel = file.relative_to(folder)
            check(len(rel.parts) == 1 or len(rel.parts) == 2 and rel.parts[0] == 'native-bytes' and re.fullmatch('[a-f0-9]{64}', rel.name), 'Unexpected stage evidence path')
            result.append(('stages/' + stage + '/' + rel.as_posix(), file))
    for name, path in qualifications.items():
        check(chain.safe(name) and '/' not in name and Path(name).suffix in ('.json', '.log'), 'Qualification needs a simple .json/.log name')
        path = regular(path)
        check(path.suffix in ('.json', '.log'), 'Qualification input must be JSON/log')
        result.append(('qualification/' + name, path))
    for _, file in result:
        check(not overlaps(output, file), 'Output overlaps input file')
    check(len({name.casefold() for name, _ in result}) == len(result), 'Case-colliding retention paths')
    check(len(result) + len(GENERATED) <= MAX_FILES, 'Retention file-count limit exceeded')
    check(sum(path.stat().st_size for _, path in result) <= LIMIT, 'Retention logical-byte limit exceeded')
    return result


def prepare(candidate, inventory, stages, qualifications, output):
    output = Path(output).absolute()
    selected = inputs(candidate, inventory, stages, qualifications, output)
    baseline = {}
    total = 0
    for name, path in selected:
        metadata, stamp = identity(path)
        baseline[name] = {'source': str(path), **metadata, 'stamp': stamp}
        total += metadata['bytes']
        check(total <= LIMIT, 'Retention logical-byte limit exceeded')
    with tempfile.TemporaryDirectory(prefix='.prepare-candidate-', dir=output.parent) as temp:
        temp = Path(temp)
        temp.chmod(0o700)
        root = temp / 'input'
        root.mkdir(mode=0o700)
        copies = {}
        for name, source in selected:
            expected = baseline[name]
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            prior = copies.get((expected['sha256'], expected['bytes']))
            if prior is None:
                shutil.copyfile(source, target)
                target.chmod(0o600)
                check(target.stat().st_size == expected['bytes'] and chain.sha(target) == expected['sha256'], 'Input changed while staging')
                copies[(expected['sha256'], expected['bytes'])] = target
            else:
                # Only link private copies, never the caller's mutable source.
                os.link(prior, target)
        def ref(name):
            return {'path': name, 'sha256': chain.sha(root / name)}
        manifest = {'schema': 1, 'platform': 'macos-universal2', 'tree': 'package',
                    'archive_prefix': 'Flapart Studio.app',
                    'stages': [{'stage': stage, 'receipt': ref('stages/' + stage + '/receipt.json')} for stage in chain.STAGES],
                    'archive': ref('candidate.zip'), 'inventory': ref('candidate-inventory.json'), 'tool_artifacts': []}
        write_json(root / 'chain-manifest.json', manifest)
        result = chain.verify(manifest, root)
        write_json(root / 'chain-result.json', result)
        # Retain observed inputs and preparer/verifier identity, never global env.
        preparation = {'schema': 1, 'prepared': True, 'source_closure_complete': False, 'release_qualified': False,
                       'candidate_sha256': manifest['archive']['sha256'],
                       'chain_manifest_sha256': chain.sha(root / 'chain-manifest.json'),
                       'inputs': [{'path': name, 'source_path': row['source'], 'bytes': row['bytes'], 'sha256': row['sha256']} for name, row in baseline.items()],
                       'helpers': {str(path.relative_to(HERE.parent)): chain.sha(path) for path in (Path(__file__).resolve(), HERE / 'retain.py', HERE.parent / 'provenance/verify_chain.py', HERE.parent / 'provenance/stage_recorder.py', HERE.parent / 'source-qualification/native_metadata.py')}}
        write_json(root / 'preparation.json', preparation)
        # Re-check actual originals after copy+verification. No success if the
        # caller edited even an otherwise identical-hash input during staging.
        check([(name, str(path)) for name, path in inputs(candidate, inventory, stages, qualifications, output)] == [(name, str(path)) for name, path in selected], 'Input file set changed')
        for name, source in selected:
            metadata, stamp = identity(source)
            row = baseline[name]
            check(metadata == {'bytes': row['bytes'], 'sha256': row['sha256']} and stamp == row['stamp'], 'Input changed during preparation')
        rows = []
        for path in sorted(root.rglob('*')):
            if path.is_dir():
                continue
            check(not path.is_symlink() and path.is_file(), 'Unexpected staged filesystem entry')
            rows.append({'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': chain.sha(path)})
        retained = {'schema': 1, 'candidate': 'candidate.zip', 'files': rows}
        retention.validate_inventory(retained)  # includes generated bytes/count
        write_json(root / 'inventory.json', retained)
        check((root / 'inventory.json').stat().st_size <= 2 * 1024**2, 'Retention inventory exceeds decryption limit')
        # Fresh mkdir is exclusive; never replace a concurrently created output.
        output.mkdir(mode=0o700)
        try:
            for child in root.iterdir():
                child.rename(output / child.name)
        except BaseException:
            shutil.rmtree(output)
            raise
    return {'prepared': True, 'candidate_sha256': manifest['archive']['sha256'],
            'inventory_sha256': chain.sha(output / 'inventory.json'), 'files': len(rows),
            'logical_bytes': sum(row['bytes'] for row in rows), 'source_closure_complete': False, 'release_qualified': False}


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--stage-evidence', type=Path, required=True)
    parser.add_argument('--qualification', action='append', default=[], metavar='NAME=PATH')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qualifications = {}
    for item in args.qualification:
        name, equal, value = item.partition('=')
        check(equal and value and name not in qualifications, 'Expected unique qualification NAME=PATH')
        qualifications[name] = Path(value)
    result = prepare(args.candidate, args.inventory, args.stage_evidence, qualifications, args.output)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
