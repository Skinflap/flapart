#!/usr/bin/env python3
"""Promote a passed private TLS workspace into a consistent application-build SDK.

Changes only WORK/sdk; the downloaded original SDK stays untouched. This is a
build preparation step, not packaged runtime or release qualification.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import platform
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_metadata', ROOT / 'distribution/source-qualification/native_metadata.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)
MAGIC = {b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def native(path):
    with path.open('rb') as stream:
        if stream.read(4) not in MAGIC:
            return None
    return metadata.parse(path.read_bytes())

def old_ssl(name):
    return pathlib.PurePosixPath(name).name in {'libssl.1.1.dylib', 'libcrypto.1.1.dylib'}

def promote(work, evidence, output):
    work = work.resolve()
    sdk = work / 'sdk'
    ssl = work / 'openssl'
    assert sdk.is_dir() and not sdk.is_symlink()
    assert not output.exists(), 'Use a new promotion receipt'
    receipt = json.loads((evidence / 'native-ci-receipt.json').read_text())
    assert receipt['passed'] and receipt['stage'] == 'native-tls-probe-passed'
    assert json.loads((evidence / 'tls-validation.json').read_text())['passed']
    assert json.loads((evidence / 'python-build.json').read_text())['compiled']
    for local, retained in (
        ('openssl-build/openssl-build-receipt.json', 'openssl-build.json'),
        ('network-build/receipt.json', 'network-build.json'),
        ('bearer-build/receipt.json', 'bearer-build.json'),
        ('python-build/python-build-receipt.json', 'python-build.json'),
    ):
        assert digest(work / local) == digest(evidence / retained), ('Workspace receipt mismatch', local)
    assert json.loads((work / 'openssl-build/openssl-build-receipt.json').read_text())['compiled']
    assert '3.5.9' in (ssl / 'include/openssl/opensslv.h').read_text()
    result = {'schema': 1, 'promoted': False, 'runtime_qualified': False,
              'release_qualified': False, 'sdk': str(sdk), 'copied': [], 'removed': []}
    plan = []
    # Both variants are needed: a remaining debug framework still loads old TLS.
    for name in ('QtNetwork', 'QtNetwork_debug'):
        matches = [p for base in (work / 'network-build', work / 'qtbase')
                   for p in base.rglob(name) if p.is_file() and not p.is_symlink()
                   and p.parent.name == '5' and p.parent.parent.name == 'Versions'
                   and p.parent.parent.parent.name == 'QtNetwork.framework']
        assert len(matches) == 1, ('Expected one newly built variant', name, matches)
        source = matches[0]
        info = native(source)
        assert info and set(info['architectures']) == {'arm64', 'x86_64'}
        assert not any(old_ssl(dep) for dep in info['native_dependencies'])
        assert any(pathlib.PurePosixPath(dep).name == 'libssl.3.dylib' for dep in info['native_dependencies'])
        target = sdk / 'lib/QtNetwork.framework/Versions/5' / name
        plan.append((source, target))
        prl = source.parent / 'Resources' / (name + '.prl')
        assert prl.is_file(), ('Missing new module link metadata', prl)
        plan.append((prl, target.parent / 'Resources' / prl.name))
    for directory in ('include', 'lib', 'ssl'):
        assert (ssl / directory).is_dir(), ('Missing maintained OpenSSL component', directory)
        for source in (ssl / directory).rglob('*'):
            if source.is_file() or source.is_symlink():
                plan.append((source, sdk / source.relative_to(ssl)))
    plan.append((ssl / 'bin/openssl', sdk / 'bin/openssl'))
    for source, target in plan:
        assert source.resolve().is_relative_to(work) and source.is_file()
        assert target.parent.resolve().is_relative_to(sdk)
        if source.is_symlink():
            assert not pathlib.Path(source.readlink()).is_absolute()
            assert (target.parent / source.readlink()).resolve().is_relative_to(sdk), ('Promoted link escapes SDK', source, target)
        if target.is_symlink():
            assert target.resolve().is_relative_to(sdk)
        info = native(source)
        if info:
            assert set(info['architectures']) == {'arm64', 'x86_64'}, ('Non-universal promoted binary', source)
            assert not any(old_ssl(dep) for dep in info['native_dependencies']), ('Old SSL dependency in promoted binary', source)
    # Reject old consumers before removing the old providers. Account for the
    # two framework binaries that the validated copy plan replaces.
    replacements = {target: source for source, target in plan}
    scanned = []
    for path in sdk.rglob('*'):
        if not path.is_file() or path.is_symlink() or old_ssl(path.name):
            continue
        info = native(replacements.get(path, path))
        if info:
            assert not any(old_ssl(dep) for dep in info['native_dependencies']), ('Old SSL consumer', path, info['native_dependencies'])
            scanned.append(str(path.relative_to(sdk)))
    try:
        # Remove obsolete headers too, so deleted upstream APIs cannot survive.
        include = sdk / 'include/openssl'
        assert include.is_dir() and not include.is_symlink()
        shutil.rmtree(include)
        for source, target in sorted(plan, key=lambda pair: pair[0].is_symlink()):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                target.unlink()
            if source.is_symlink():
                if target.exists():
                    target.unlink()
                target.symlink_to(source.readlink())
            else:
                shutil.copy2(source, target)
                if target.suffix in {'.pc', '.cmake', '.prl'}:
                    target.write_text(target.read_text().replace(str(ssl), str(sdk)))
        # Record hashes only after all link referents and link chains exist.
        for source, target in plan:
            result['copied'].append({'path': str(target.relative_to(sdk)), 'source_sha256': digest(source), 'sha256': digest(target)})
        for name in ('libssl.1.1.dylib', 'libcrypto.1.1.dylib'):
            path = sdk / 'lib' / name
            if path.exists():
                result['removed'].append({'path': str(path.relative_to(sdk)), 'sha256': digest(path)})
                path.unlink()
        assert '3.5.9' in (sdk / 'include/openssl/opensslv.h').read_text()
        result.update(promoted=True, checked_native_consumers=scanned)
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + '\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=pathlib.Path, required=True)
    parser.add_argument('--evidence', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    assert platform.system() == 'Darwin', 'Native Mac SDK promotion only'
    promote(args.work, args.evidence, args.output)

if __name__ == '__main__':
    main()
