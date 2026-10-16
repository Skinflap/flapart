#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify pinned actual Mac stage receipts and final archive; never qualifies release."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import zipfile

spec = importlib.util.spec_from_file_location('chain_stage_recorder', Path(__file__).with_name('stage_recorder.py'))
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)
STAGES = ('collector', 'completion', 'codesign', 'verify')


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe(name):
    return (isinstance(name, str) and bool(name) and not name.startswith('/') and '\\' not in name
            and not any(ord(c) < 32 for c in name) and '..' not in PurePosixPath(name).parts
            and posixpath.normpath(name) == name and ':' not in name)


def reference(root, ref):
    check(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and safe(ref['path']), 'Invalid pinned reference')
    check(re.fullmatch('[a-f0-9]{64}', ref['sha256']) is not None, 'Invalid reference hash')
    path = root / ref['path']
    check(path.resolve().is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(), 'Missing/escaping evidence artifact')
    check(sha(path) == ref['sha256'], 'Altered evidence artifact: ' + ref['path'])
    return path


def read_json(path):
    check(path.stat().st_size <= 128 * 1024**2, 'Oversized evidence JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def artifact(root, ref):
    check(set(ref) == {'path', 'sha256', 'bytes'}, 'Malformed recorded artifact')
    path = reference(root, {key: ref[key] for key in ('path', 'sha256')})
    check(path.stat().st_size == ref['bytes'], 'Recorded artifact size mismatch')
    return path


def snapshot(root, snap):
    check(isinstance(snap, dict) and set(snap) == {'root', 'exists', 'files'} and isinstance(snap['exists'], bool), 'Invalid native snapshot')
    check(Path(snap['root']).is_absolute(), 'Snapshot root is not absolute')
    check(snap['exists'] or not snap['files'], 'Absent tree has files')
    rows = {}
    for row in snap['files']:
        name = row.get('path')
        check(safe(name) and name not in rows, 'Duplicate/unsafe snapshot path')
        rows[name] = row
        if row.get('kind') == 'native':
            check(row.get('retained_bytes') == 'native-bytes/' + row['sha256'], 'Native bytes were not retained')
            blob = reference(root, {'path': row['retained_bytes'], 'sha256': row['sha256']})
            check(blob.stat().st_size == row['bytes'] and isinstance(row['mode'], int), 'Native size/mode mismatch')
            info = recorder.captured_metadata(blob.read_bytes())
            check(info and all(row.get(key) == value for key, value in info.items()), 'Native metadata differs from actual bytes')
        else:
            check(row.get('kind') in ('file-alias', 'directory-alias'), 'Unknown snapshot row')
            target = row.get('target')
            check(isinstance(target, str) and target and not target.startswith('/') and '\\' not in target,
                  'Unsafe snapshot alias')
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            check(safe(resolved), 'Escaping snapshot alias')
            if row['kind'] == 'file-alias':
                check(safe(row.get('resolved_path')), 'Unsafe resolved alias path')
    return rows


def canonical_state(rows):
    # Blob paths are stage-local evidence locations, not runtime state.
    return {name: {key: value for key, value in row.items() if key != 'retained_bytes'} for name, row in rows.items()}


def verify_receipt(path, expected_stage, tree, tool_blobs):
    root = path.parent
    receipt = read_json(path)
    check(receipt.get('schema') == 1 and receipt.get('stage') == expected_stage, 'Stage name/schema mismatch')
    check(receipt.get('passed') is True and receipt.get('comparison_complete') is True
          and receipt.get('returncode') == 0 and receipt.get('errors') == []
          and not receipt.get('timed_out') and receipt.get('historical_reconstruction') is False,
          'Failed/incomplete stage receipt')
    check(receipt.get('native_byte_retention') is True, 'Stage lacks native input/output bytes')
    check(receipt.get('argv') and receipt.get('requested_argv') and receipt.get('cwd'), 'Missing actual command')
    check(set(receipt.get('environment', {})) <= recorder.ENV_KEYS, 'Unapproved recorded environment')
    check(set(receipt['before']) == set(receipt['after']) and tree in receipt['before'], 'Missing/mismatched tree label')
    check(read_json(artifact(root, receipt['before_snapshot'])) == receipt['before'], 'Before snapshot differs from persisted evidence')
    artifact(root, receipt['stdout'])
    artifact(root, receipt['stderr'])
    check(receipt.get('tools') and receipt.get('helpers'), 'Missing tool/helper identities')
    check(receipt['tools'][0]['resolved_path'] == receipt['argv'][0], 'Executed tool identity mismatch')
    for row in receipt['tools'] + receipt['helpers']:
        check(row.get('sha256_after') == row['sha256'], 'Tool/helper changed during stage')
        check(re.fullmatch('[a-f0-9]{64}', row['sha256']) is not None and isinstance(row['bytes'], int) and row['bytes'] >= 0, 'Invalid recorded tool/helper identity')
        if row['sha256'] in tool_blobs:
            check(tool_blobs[row['sha256']].stat().st_size == row['bytes'], 'Tool/helper size mismatch')
    states = {}
    for phase in ('before', 'after'):
        states[phase] = {}
        for label, snap in receipt[phase].items():
            states[phase][label] = snapshot(root, snap)
            check(receipt['before'][label]['root'] == receipt['after'][label]['root'], 'Tree root changed within stage')
    check(receipt['changed_files'] == recorder.differences(receipt['before'], receipt['after']), 'Changed-file ledger mismatch')
    return receipt, states['before'][tree], states['after'][tree]


def archive_state(archive, inventory, prefix):
    check(inventory.get('platform') == 'macos-universal2', 'Wrong final inventory platform')
    index = {}
    for row in inventory['files']:
        check(safe(row['path']) and row['path'] not in index, 'Unsafe/duplicate inventory path')
        index[row['path']] = row
    native, aliases, all_names, directories = {}, {}, set(), set()
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        check(len(entries) <= 100000 and sum(i.file_size for i in entries) <= 8 * 1024**3, 'Oversized final archive')
        folded = set()
        for info in entries:
            name = info.filename[:-1] if info.is_dir() else info.filename
            check(safe(name) and (name == prefix or name.startswith(prefix + '/')), 'Unsafe/outside-prefix ZIP path')
            check(name not in all_names and name.casefold() not in folded, 'Duplicate/colliding ZIP path')
            all_names.add(name); folded.add(name.casefold())
            check(not info.flag_bits & 1, 'Encrypted ZIP members unsupported')
            mode = (info.external_attr >> 16) & 0o170000
            if info.is_dir():
                check(mode in (0, stat.S_IFDIR), 'ZIP directory type mismatch')
                directories.add(name)
                continue
            check(name in index, 'Archive member absent from final inventory')
            row = index[name]
            data = zipped.read(info)
            if mode == stat.S_IFLNK:
                check(len(data) <= 4096, 'Oversized archive symlink')
                target = data.decode('utf-8')
                check(row.get('symlink') == target and target and not target.startswith('/') and '\\' not in target,
                      'Archive symlink mismatch/unsafe target')
                aliases[name] = target
            else:
                check(mode in (0, stat.S_IFREG) and 'symlink' not in row, 'Unsupported ZIP file type')
                check(row.get('sha256') == hashlib.sha256(data).hexdigest() and row.get('bytes') == len(data), 'ZIP inventory byte mismatch')
                info_native = recorder.captured_metadata(data)
                if info_native:
                    check(info_native['format'] == 'macho' and set(info_native['architectures']) == {'arm64', 'x86_64'}, 'Final Mac native format/architecture mismatch')
                    native[name[len(prefix) + 1:]] = {'sha256': row['sha256'], 'bytes': len(data), 'mode': (info.external_attr >> 16) & 0o7777, **info_native}
        actual_files = all_names - directories
        check(actual_files == set(index), 'Final archive/inventory file-set mismatch')
        for name in all_names:
            parent = posixpath.dirname(name)
            while parent:
                check(parent not in actual_files, 'ZIP member descends through a file or symlink')
                directories.add(parent)
                parent = posixpath.dirname(parent)
        def resolve(name):
            seen = set()
            for _ in range(len(aliases) + 1):
                check(name not in seen, 'Cyclic archive symlink')
                seen.add(name)
                parts = name.split('/')
                alias = next(('/'.join(parts[:i]) for i in range(1, len(parts) + 1) if '/'.join(parts[:i]) in aliases), None)
                if alias is None:
                    check(name in actual_files or name in directories, 'Dangling archive symlink')
                    return name
                tail = name[len(alias):].lstrip('/')
                name = posixpath.normpath(posixpath.join(posixpath.dirname(alias), aliases[alias], tail))
                check(safe(name) and (name == prefix or name.startswith(prefix + '/')), 'Escaping archive symlink')
            raise ValueError('Cyclic archive symlink')
        alias_state = {}
        for name, target in aliases.items():
            resolved = resolve(name)
            row = {'target': target, 'kind': 'directory-alias' if resolved in directories else 'file-alias'}
            if row['kind'] == 'file-alias':
                row['resolved_path'] = resolved[len(prefix) + 1:]
            alias_state[name[len(prefix) + 1:]] = row
    return native, alias_state


def verify(manifest, root):
    root = Path(root).resolve()
    check(manifest.get('schema') == 1 and manifest.get('platform') == 'macos-universal2', 'Unsupported chain schema/platform')
    check([s.get('stage') for s in manifest['stages']] == list(STAGES), 'Missing/reordered/duplicate required stages')
    tree, prefix = manifest['tree'], manifest['archive_prefix']
    check(re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', tree) and safe(prefix) and '/' not in prefix and prefix.endswith('.app'), 'Invalid tree/archive mapping')
    blobs = {}
    for ref in manifest.get('tool_artifacts', []):
        check(ref['sha256'] not in blobs, 'Duplicate tool artifact hash')
        blobs[ref['sha256']] = reference(root, ref)
    previous, previous_root, receipts, final = None, None, [], None
    tool_hashes = set()
    for row in manifest['stages']:
        check(set(row) == {'stage', 'receipt'}, 'Unreviewed per-stage path mapping')
        path = reference(root, row['receipt'])
        receipt, before, after = verify_receipt(path, row['stage'], tree, blobs)
        tool_hashes.update(r['sha256'] for r in receipt['tools'] + receipt['helpers'])
        current_root = receipt['after'][tree]['root']
        check(receipt['after'][tree]['exists'] and any(r['kind'] == 'native' for r in after.values()), 'Stage has no native package output')
        if previous is not None:
            check(current_root == previous_root, 'Adjacent package tree roots differ')
            check(canonical_state(before) == canonical_state(previous), 'Broken adjacent native-byte/alias chain')
        if row['stage'] == 'verify':
            check(canonical_state(before) == canonical_state(after), 'Verification stage mutated package')
        previous, previous_root, final = after, current_root, after
        receipts.append(row['receipt'])
    archive = reference(root, manifest['archive'])
    inventory = read_json(reference(root, manifest['inventory']))
    native, aliases = archive_state(archive, inventory, prefix)
    expected_native = {name: row for name, row in final.items() if row['kind'] == 'native'}
    expected_aliases = {name: {key: row[key] for key in ('kind', 'target', 'resolved_path') if key in row} for name, row in final.items() if row['kind'] in ('file-alias', 'directory-alias')}
    check(set(native) == set(expected_native), 'Final ZIP native set differs from verified output')
    for name, actual in native.items():
        check(all(expected_native[name].get(key) == value for key, value in actual.items()), 'Final ZIP native bytes/metadata/mode differ from signed output')
    check(aliases == expected_aliases, 'Final ZIP aliases differ from verified output')
    check(sha(archive) == manifest['archive']['sha256'], 'Archive changed during verification')
    return {'schema': 1, 'chain_verified': True, 'source_closure_complete': False, 'release_qualified': False,
            'payload_sha256': manifest['archive']['sha256'], 'target_platform': 'macos-universal2',
            'stages': receipts, 'native_files': len(native), 'aliases': len(aliases),
            'recorded_tool_helper_hashes': sorted(tool_hashes),
            'independently_retained_tool_hashes': sorted(tool_hashes & set(blobs)),
            'recorded_only_tool_hashes': sorted(tool_hashes - set(blobs))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check(not args.output.exists(), 'Output must be new')
    check(sha(args.manifest) == args.manifest_sha256, 'Manifest pin mismatch')
    result = verify(read_json(args.manifest), args.evidence_root)
    args.output.write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    main()
