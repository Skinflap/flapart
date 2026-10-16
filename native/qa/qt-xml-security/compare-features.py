#!/usr/bin/env python3
"""Report literal Qt5 feature changes; never approve a changed SDK automatically."""
import argparse
import hashlib
import json
from pathlib import Path
import re

KEY = re.compile(r'^(QT_CONFIG|QT\.[A-Za-z0-9_]+\.(?:enabled_features|disabled_features))\s*(\+=|-=|=)\s*(.*?)\s*$')
FEATURE = re.compile(r'^[A-Za-z0-9_+.-]+$')


def parse(text):
    values = {}
    logical = ''
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        continuation = line.endswith('\\')
        logical += ' ' + (line[:-1] if continuation else line)
        if continuation:
            continue
        match = KEY.fullmatch(logical.strip())
        if match:
            key, op, content = match.groups()
            tokens = content.split()
            if any(not FEATURE.fullmatch(token) for token in tokens):
                raise ValueError('Nonliteral feature expression: ' + key)
            if op == '=':
                values[key] = set(tokens)
            elif op == '+=':
                values.setdefault(key, set()).update(tokens)
            else:
                values.setdefault(key, set()).difference_update(tokens)
        elif re.search(r'\b(enabled_features|disabled_features|QT_CONFIG)\b', logical):
            raise ValueError('Conditional or unsupported feature assignment')
        logical = ''
    if logical.strip():
        raise ValueError('Unterminated continuation')
    return values


def snapshot(root, modules_dir, modules):
    root = Path(root)
    selected = [root / 'qconfig.pri']
    for module in modules:
        for suffix in ('', '_private'):
            selected.append(root / modules_dir / ('qt_lib_' + module + suffix + '.pri'))
    values, inputs = {}, []
    for path in selected:
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing or symlinked feature input: ' + str(path))
        data = path.read_bytes()
        local = {path.name + ":" + key: value for key, value in parse(data.decode()).items()}
        if values.keys() & local.keys():
            raise ValueError('Duplicate feature keys across input files')
        values.update(local)
        inputs.append({'path':str(path), 'sha256':hashlib.sha256(data).hexdigest()})
    for module in modules:
        if not any((':QT.' + module + '.') in key for key in values):
            raise ValueError('Module has no literal feature metadata: ' + module)
    return values, inputs


def compare(before, after):
    return [{'key':key, 'before_present':key in before, 'after_present':key in after,
             'removed':sorted(before.get(key,set()) - after.get(key,set())),
             'added':sorted(after.get(key,set()) - before.get(key,set()))}
            for key in sorted(before.keys() | after.keys())
            if key not in before or key not in after or before[key] != after[key]]


def partition_host_mode(changes):
    """Only global cross_compile bookkeeping may differ across build hosts."""
    capability, host = [], []
    for row in changes:
        if (row['key'] in {'qconfig.pri:QT.global.enabled_features',
                           'qconfig.pri:QT.global.disabled_features'}
                and row['before_present'] and row['after_present']
                and set(row['removed'] + row['added']) <= {'cross_compile'}):
            host.append(row)
        else:
            capability.append(row)
    return capability, host


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--before-modules', choices=['modules','modules-inst'], default='modules')
    parser.add_argument('--after-modules', choices=['modules','modules-inst'], default='modules-inst')
    parser.add_argument('--module', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-host-build-mode-change', action='store_true',
                        help='Record global cross_compile-only differences separately; all capability changes still fail')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[a-z0-9_]+', module) for module in args.module):
        parser.error('Invalid module name')
    before, bi = snapshot(args.before, args.before_modules, args.module)
    after, ai = snapshot(args.after, args.after_modules, args.module)
    changes = compare(before, after)
    capability_changes, host_changes = partition_host_mode(changes) if args.allow_host_build_mode_change else (changes, [])
    result = {'scope':'Literal feature declarations only; not ABI, binary or runtime qualification',
              'modules':args.module, 'inputs':{'before':bi,'after':ai}, 'changes':changes,
              'same_features':not changes, 'release_qualified':False}
    result.update(same_capabilities=not capability_changes, host_build_mode_changes=host_changes,
                  capability_changes=capability_changes)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'same_features':not changes, 'changes':changes},indent=2))
    raise SystemExit(bool(capability_changes))
