#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete an unsigned collector bundle. Portable planning; Darwin-only mutation.
Not release qualification. Never changes the SDK or system trust store.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import struct
import tempfile

spec = importlib.util.spec_from_file_location('flapart_native_metadata', Path(__file__).resolve().parents[2] / 'distribution/source-qualification/native_metadata.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)
FRAMEWORK = Path('Contents/Frameworks')
VERSION = FRAMEWORK / 'Python.framework/Versions/3.13'
PYTHON_APP = VERSION / 'Resources/Python.app'
PYTHON = PYTHON_APP / 'Contents/MacOS/Python'
CERT = Path('Contents/Resources/openssl/cert.pem')
PROVIDERS = FRAMEWORK / 'ossl-modules'
CLI = Path('Contents/MacOS/openssl')
BOOTSTRAP = '''# Flapart maintained runtime defaults; also executed by Python -I.
import os as _flap_os
from pathlib import Path as _FlapPath
_flap_contents = _FlapPath(__file__).resolve().parents[6]
_flap_cert = _flap_contents / 'Resources/openssl/cert.pem'
_flap_providers = _flap_contents / 'Frameworks/ossl-modules'
_flap_config = _flap_contents / 'Resources/openssl/openssl.cnf'
if not _flap_cert.is_file() or not _flap_providers.is_dir() or not _flap_config.is_file():
    raise SystemExit('Flapart maintained TLS runtime is incomplete')
# Environment customizations remain explicit user choices; QA must clear them.
_flap_os.environ.setdefault('SSL_CERT_FILE', str(_flap_cert))
_flap_os.environ.setdefault('SSL_CERT_DIR', str(_flap_cert.parent / 'certs'))
_flap_os.environ.setdefault('OPENSSL_MODULES', str(_flap_providers))
_flap_os.environ.setdefault('OPENSSL_CONF', str(_flap_config))
del _flap_os, _FlapPath, _flap_contents, _flap_cert, _flap_providers, _flap_config
'''
CONFIG = '# Flapart: default provider auto-loading; no legacy provider activation.\n'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bounded(path, root):
    return path.resolve().is_relative_to(root.resolve())

def check_tree(root):
    for path in root.rglob('*'):
        require(bounded(path, root), 'Escaping bundle symlink: ' + str(path))
        require(not path.is_symlink() or path.exists(), 'Broken bundle symlink: ' + str(path))
        require(path.is_file() or path.is_dir(), 'Unsupported filesystem entry: ' + str(path))

def filetypes(data):
    thin = {b'\xcf\xfa\xed\xfe': '<', b'\xce\xfa\xed\xfe': '<', b'\xfe\xed\xfa\xce': '>', b'\xfe\xed\xfa\xcf': '>'}
    if data[:4] in thin:
        return {struct.unpack_from(thin[data[:4]] + 'I', data, 12)[0]}
    fats = {b'\xca\xfe\xba\xbe': ('>', 20), b'\xbe\xba\xfe\xca': ('<', 20), b'\xca\xfe\xba\xbf': ('>', 32), b'\xbf\xba\xfe\xca': ('<', 32)}
    endian, stride = fats[data[:4]]
    result = set()
    for index in range(struct.unpack_from(endian + 'I', data, 4)[0]):
        offset, size = struct.unpack_from(endian + ('II' if stride == 20 else 'QQ'), data, 16 + index * stride)
        result.update(filetypes(data[offset:offset + size]))
    return result

def native(path):
    with path.open('rb') as stream:
        magic = stream.read(4)
    if magic not in {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca', b'\x7fELF'} and magic[:2] != b'MZ':
        return None
    data = path.read_bytes()
    result = metadata.parse(data)
    require(not result or result['format'] == 'macho', 'Non-Mach-O native payload: ' + str(path))
    if result:
        result['filetypes'] = filetypes(data)
        require(len(result['filetypes']) == 1, 'Inconsistent Mach-O slice file types: ' + str(path))
    return result

def system_dependency(dep):
    return '..' not in Path(dep).parts and dep.startswith(('/usr/lib/', '/System/Library/')) and not any(x in dep.lower() for x in ('libssl', 'libcrypto', 'python.framework', 'qtnetwork.framework'))

def dependency_target(dep, binary, root, files, private_prefixes, aliases=None):
    """Resolve against bundle contents; never use a host file to satisfy an import."""
    require('..' not in Path(dep).parts or dep.startswith(('@loader_path/', '@executable_path/')), 'Unsafe dependency traversal: ' + dep)
    if system_dependency(dep):
        return None
    require(Path(dep).name not in {'libssl.1.1.dylib', 'libcrypto.1.1.dylib'}, 'Obsolete TLS dependency: ' + dep)
    if dep.startswith('@loader_path/'):
        target = binary.parent / dep[len('@loader_path/'):]
    elif dep.startswith('@executable_path/'):
        suffix = dep[len('@executable_path/'):]
        if files[binary]['filetypes'] == {2}:  # MH_EXECUTE has its own executable directory.
            target = binary.parent / suffix
        else:
            contexts = {root / 'Contents/MacOS'} | {p.parent for p, info in files.items() if info['filetypes'] == {2}}
            candidates = {(parent / suffix).resolve() for parent in contexts if (parent / suffix).is_file() and bounded(parent / suffix, root)}
            require(len(candidates) == 1, 'Missing/ambiguous executable-relative dependency: ' + dep)
            target = candidates.pop()
    else:
        if dep.startswith('@rpath/'):
            suffix = dep[len('@rpath/'):]
        elif Path(dep).is_absolute():
            match = next((Path(dep).relative_to(p) for p in private_prefixes if Path(dep).is_relative_to(p)), None)
            require(match is not None, 'Unapproved absolute dependency: ' + dep)
            parts = match.parts
            require(parts and parts[0] in ('lib', 'bin', 'plugins'), 'Unmapped private dependency: ' + dep)
            suffix = Path(*parts[1:]).as_posix()
        else:
            raise ValueError('Unqualified dependency: ' + dep)
        require(suffix and '..' not in Path(suffix).parts, 'Unsafe dependency suffix: ' + dep)
        candidates = {p.resolve() for p in (aliases if aliases is not None else files) if p.as_posix().endswith('/' + suffix)}
        require(len(candidates) == 1, 'Missing/ambiguous bundled dependency: ' + dep)
        target = candidates.pop()
    require(bounded(target, root) and target.is_file(), 'Dependency escapes or is absent: ' + dep)
    require(target.resolve() in {p.resolve() for p in files}, 'Dependency is not Mach-O: ' + dep)
    return target.resolve()

def relocation_plan(root, private_prefixes=(), universal=True):
    root = root.resolve()
    check_tree(root)
    records = {}
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            info = native(path)
            if info:
                require(not universal or set(info['architectures']) == {'arm64', 'x86_64'}, 'Non-universal binary: ' + str(path))
                records[path] = info
    require(records, 'Bundle contains no Mach-O binaries')
    prefixes = tuple(Path(p).resolve() for p in private_prefixes)
    aliases = [p for p in root.rglob('*') if p.is_file() and p.resolve() in records]
    commands = []
    for path, info in sorted(records.items()):
        args = []
        for dep in info['native_dependencies']:
            target = dependency_target(dep, path, root, records, prefixes, aliases)
            if target is not None:
                new = '@loader_path/' + Path(os.path.relpath(target, path.parent)).as_posix()
                if new != dep:
                    args.extend(['-change', dep, new])
        rpaths = [set(s['rpaths']) for s in info['slices']]
        require(all(r == rpaths[0] for r in rpaths), 'Slice-specific rpaths require explicit thinning: ' + str(path))
        for rpath in sorted(rpaths[0]):
            args.extend(['-delete_rpath', rpath])
        # Dylib identity is metadata, not a dependency. Normalize known libraries.
        if info['filetypes'] == {6}:  # MH_DYLIB; never assign IDs to MH_BUNDLE providers.
            args.extend(['-id', '@loader_path/' + path.name])
        if args:
            commands.append({'path': path.relative_to(root).as_posix(), 'args': args})
    return commands

def verify_relocated(root, universal=True):
    plan = relocation_plan(root, (), universal)
    # Idempotent -id assignments are allowed; no dependency/rpath repair may remain.
    require(all(row['args'][:1] == ['-id'] and len(row['args']) == 2 for row in plan), 'Unfinished relocation')

def remove_known_build_dlls(root):
    folder = root / VERSION / 'lib/python3.13/site-packages/pyqtbuild/bundle/dlls'
    if not folder.exists():
        return []
    require(not folder.is_symlink() and bounded(folder, root), 'Unsafe build-time DLL directory')
    expected = {'openssl-32/libssl-1_1.dll', 'openssl-32/libcrypto-1_1.dll',
                'openssl-64/libssl-1_1-x64.dll', 'openssl-64/libcrypto-1_1-x64.dll'}
    for arch in ('32', '64'):
        for name in ('msvcp140_2.dll', 'vcruntime140.dll', 'concrt140.dll', 'msvcp140_1.dll', 'msvcp140.dll'):
            expected.add('msvc-' + arch + '/' + name)
    expected.add('msvc-64/vcruntime140_1.dll')
    files = [p for p in folder.rglob('*') if p.is_file() or p.is_symlink()]
    for path in files:
        require(not path.is_symlink() and path.relative_to(folder).as_posix() in expected,
                'Unreviewed build-time DLL asset: ' + str(path))
        with path.open('rb') as stream:
            require(stream.read(2) == b'MZ', 'Expected PE build-time DLL: ' + str(path))
    removed = [{'path': p.relative_to(root).as_posix(), 'sha256': digest(p),
                'reason': 'Pinned PyQt-builder Windows redistribution assets, unused by macOS'} for p in files]
    for path in files:
        path.unlink()
    return removed

def populate(root, sdk, openssl_license, python_license, certificate_sha256):
    sdk = sdk.resolve()
    removed = remove_known_build_dlls(root)
    sources = [(sdk / 'lib/Python.framework/Versions/3.13/Resources/Python.app', root / PYTHON_APP),
               (sdk / 'bin/openssl', root / CLI),
               (sdk / 'lib/ossl-modules', root / PROVIDERS),
               (sdk / 'ssl/cert.pem', root / CERT)]
    for name in ('libssl.3.dylib', 'libcrypto.3.dylib'):
        sources.append((sdk / 'lib' / name, root / FRAMEWORK / name))
    for src, dst in sources:
        require(src.exists() and bounded(src, sdk), 'Missing/escaping maintained SDK component: ' + str(src))
        if src.is_dir():
            check_tree(src)
        require(bounded(dst, root), 'Escaping collection destination: ' + str(dst))
    certificate = sdk / 'ssl/cert.pem'
    require(len(certificate_sha256) == 64 and digest(certificate) == certificate_sha256, 'Certificate snapshot hash mismatch')
    require(b'-----BEGIN CERTIFICATE-----' in certificate.read_bytes(), 'Missing PEM trust roots')
    for license_path in (openssl_license, python_license):
        require(license_path.is_file() and license_path.stat().st_size > 100, 'Missing complete license: ' + str(license_path))
    copied = []
    for src, dst in sources:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.exists():
            shutil.rmtree(dst)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)
        copied.append(dst.relative_to(root).as_posix())
    require((root / PYTHON).is_file(), 'Restored Python.app has no real interpreter')
    require(any(p.is_file() for p in (root / PROVIDERS).rglob('*')), 'Provider directory is empty')
    for name, src in [('OpenSSL-LICENSE.txt', openssl_license), ('CPython-LICENSE.txt', python_license)]:
        dst = root / 'Contents/Resources/licenses/maintained-runtime' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (root / CERT).with_name('openssl.cnf').write_text(CONFIG)
    (root / CERT).parent.joinpath('certs').mkdir(exist_ok=True)
    custom = root / VERSION / 'lib/python3.13/sitecustomize.py'
    require(custom.parent.is_dir() and bounded(custom, root), 'Missing/escaping Python stdlib')
    original = custom.read_text() if custom.exists() else ''
    require('# Flapart maintained runtime defaults' not in original, 'Runtime completion already applied')
    # Preserve upstream site setup in a separate module to keep __future__ imports legal.
    if original:
        old = custom.with_name('_flapart_original_sitecustomize.py')
        require(not old.exists(), 'Original site module collision')
        old.write_text(original)
    custom.write_text(BOOTSTRAP + ('import _flapart_original_sitecustomize\n' if original else ''))
    for cache in custom.parent.glob('__pycache__/sitecustomize.*.pyc'):
        cache.unlink()
    check_tree(root)
    return copied, removed

def complete(bundle, sdk, openssl_license, python_license, certificate_sha256, private_prefixes=(), apply=False, universal=True):
    require(not bundle.is_symlink(), 'Bundle root must not be a symlink')
    bundle = bundle.resolve()
    require(bundle.is_dir() and bundle.suffix == '.app', 'Expected existing collected .app')
    require(not apply or platform.system() == 'Darwin', 'Native mutation requires macOS')
    check_tree(bundle)
    # Work in a private sibling: failed planning/tools leave collector output intact.
    with tempfile.TemporaryDirectory(prefix='.flapart-runtime-', dir=bundle.parent) as temporary:
        staged = Path(temporary) / bundle.name
        shutil.copytree(bundle, staged, symlinks=True)
        copied, removed = populate(staged, sdk, openssl_license, python_license, certificate_sha256)
        commands = relocation_plan(staged, (sdk, *private_prefixes), universal)
        receipt = {'schema': 1, 'runtime_completed': False, 'native_validated': False, 'publishable': False,
                   'python': PYTHON.as_posix(), 'openssl': CLI.as_posix(), 'certificate_sha256': certificate_sha256,
                   'licenses': {'openssl': digest(openssl_license), 'python': digest(python_license)},
                   'copied': copied, 'removed_build_assets': removed, 'relocations': commands}
        if apply:
            for row in commands:
                subprocess.run(['install_name_tool', *row['args'], str(staged / row['path'])], check=True)
            verify_relocated(staged, universal)
            backup = Path(temporary) / 'original.app'
            bundle.rename(backup)
            try:
                staged.rename(bundle)
            except BaseException:
                backup.rename(bundle)
                raise
            receipt['runtime_completed'] = True
        return receipt

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'sdk', 'openssl-license', 'python-license', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--certificate-sha256', required=True)
    p.add_argument('--private-prefix', type=Path, action='append', default=[])
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    require(not a.output.exists(), 'Use a fresh receipt path')
    result = complete(a.bundle, a.sdk, a.openssl_license, a.python_license, a.certificate_sha256, a.private_prefix, a.apply)
    a.output.write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    main()
