#!/usr/bin/env python3
"""Adopt assembled Qt only inside its disposable build SDK, retaining the baseline.

This prepares application build inputs. It is not runtime/release qualification.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


assembly = module('assembly', ROOT / 'merge-macos.py')
metadata = module('native_metadata', ROOT.parents[1] / 'distribution/source-qualification/native_metadata.py')


def check_runtime_links(qt):
    checked = []
    for relative, required in (
        ('lib/QtNetwork.framework/Versions/5/QtNetwork', {'libssl.3.dylib', 'libcrypto.3.dylib'}),
        ('lib/QtNetwork.framework/Versions/5/QtNetwork_debug', {'libssl.3.dylib', 'libcrypto.3.dylib'}),
        ('plugins/imageformats/libqwebp.dylib', {'libwebp.7.2.0.dylib', 'libwebpmux.3.1.2.dylib', 'libwebpdemux.2.0.17.dylib'}),
        ('plugins/imageformats/libqwebp_debug.dylib', {'libwebp.7.2.0.dylib', 'libwebpmux.3.1.2.dylib', 'libwebpdemux.2.0.17.dylib'}),
    ):
        path = qt / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing rebuilt runtime: ' + relative)
        info = metadata.parse(path.read_bytes())
        if not info or info['format'] != 'macho' or set(info['architectures']) != {'arm64', 'x86_64'}:
            raise ValueError('Rebuilt runtime must contain both CPUs: ' + relative)
        for part in info['slices']:
            names = {Path(dep).name for dep in part['dependencies']}
            if not required <= names or names & {'libssl.1.1.dylib', 'libcrypto.1.1.dylib'}:
                raise ValueError('Maintained dependencies missing in CPU slice: ' + relative)
        checked.append({'path': relative, 'sha256': assembly.sha(path), 'metadata': info})
    return checked


def promote(work, receipt_path):
    work, receipt_path = work.absolute(), receipt_path.absolute()
    sdk, qt = work / 'sdk', work / 'qt-universal'
    saved, pending = work / 'sdk-before-qt', work / 'sdk-with-qt'
    if any(p.exists() or p.is_symlink() for p in (saved, pending, receipt_path)):
        raise ValueError('Use fresh promotion destinations')
    if receipt_path.resolve().is_relative_to(sdk.resolve()):
        raise ValueError('Receipt must be outside SDK')
    build = json.loads((work / 'evidence/result.json').read_text())
    receipt = json.loads((work / 'evidence/assembly.json').read_text())
    if not build['compiled'] or not build['universal_assembled'] or not receipt['assembled'] or receipt['conflicts']:
        raise ValueError('Incomplete Qt build or assembly')
    original, new = assembly.inventory(sdk), assembly.inventory(qt)
    if new != receipt['outputs']:
        raise ValueError('Assembled Qt changed')
    # Existing Qt framework binaries must all be replaced, including debug and
    # secondary modules; a successful Core-only overlay is insufficient.
    expected = {name for name, row in original.items()
                if row['kind'] == 'native' and name.startswith('lib/Qt') and '.framework/' in name}
    if not expected or any(name not in new or new[name]['kind'] != 'native' for name in expected):
        raise ValueError('Incomplete baseline Qt framework replacement')
    if 'bin/qmake' not in new:
        raise ValueError('Missing rebuilt qmake')
    checked = check_runtime_links(qt)
    result = {'promoted': False, 'runtime_qualified': False, 'release_qualified': False,
              'baseline_sdk': build['baseline_sdk'],
              'sdk': str(sdk), 'preserved_sdk': str(saved),
              'build_receipt_sha256': assembly.sha(work / 'evidence/result.json'),
              'assembly_receipt_sha256': assembly.sha(work / 'evidence/assembly.json'),
              'checked_runtime_links': checked, 'replaced_framework_binaries': sorted(expected),
              'copied': [], 'baseline_entries': original}
    shutil.copytree(sdk, pending, symlinks=True)
    for name, row in new.items():
        source, target = qt / name, pending / name
        if not target.parent.resolve().is_relative_to(pending.resolve()):
            raise ValueError('Overlay parent escapes SDK: ' + name)
        if row['kind'] == 'directory':
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise ValueError('Directory overlay mismatch: ' + name)
            target.mkdir(exist_ok=True, parents=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        elif target.exists() and not target.is_file():
            raise ValueError('File overlay mismatch: ' + name)
        if row['kind'] == 'link':
            if target.exists():
                target.unlink()
            target.symlink_to(row['target'])
        else:
            shutil.copy2(source, target)
        result['copied'].append({'path': name, **row})
    final = assembly.inventory(pending)
    if any(final.get(name) != row for name, row in new.items()):
        raise ValueError('Overlay output mismatch')
    if any(final.get(name) != row for name, row in original.items() if name not in new):
        raise ValueError('Unrelated SDK dependency changed')
    if assembly.inventory(sdk) != original or assembly.inventory(qt) != new:
        raise ValueError('Inputs changed during promotion')
    sdk.rename(saved)
    try:
        pending.rename(sdk)
    except Exception:
        saved.rename(sdk)
        raise
    result['promoted'] = True
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    promote(args.build_work, args.output)
