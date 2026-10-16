#!/usr/bin/env python3
"""Archive and relocate a Mac bundle, then probe both actual CPU processes.

Temporary runtime/archive files never enter the evidence directory. Build
prefixes are hidden only during probes, and restored even if a probe fails.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def archive_bundle(bundle, destination):
    """Preserve relative links and executable permissions without dereferencing."""
    bundle = bundle.resolve()
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob('*')):
            if path.is_symlink():
                assert path.resolve().is_relative_to(bundle) and path.exists(), ('Unsafe bundle link', path)
                target = os.readlink(path)
                assert not os.path.isabs(target)
                info = zipfile.ZipInfo(path.relative_to(bundle.parent).as_posix())
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, target.encode())
            elif path.is_file():
                archive.write(path, path.relative_to(bundle.parent).as_posix())

@contextlib.contextmanager
def hidden_prefixes(prefixes, runtime, evidence):
    paths = [Path(p).resolve() for p in prefixes]
    assert len(set(paths)) == len(paths)
    for path in paths:
        assert path.is_dir() and path != Path('/')
        assert not runtime.resolve().is_relative_to(path)
        assert not evidence.resolve().is_relative_to(path)
        assert not Path(sys.executable).resolve().is_relative_to(path)
        assert not any(other != path and (other.is_relative_to(path) or path.is_relative_to(other)) for other in paths)
    moved = []
    try:
        for path in paths:
            hidden = path.with_name(path.name + '-hidden-' + uuid.uuid4().hex)
            assert not hidden.exists()
            path.rename(hidden)
            moved.append((path, hidden))
        yield
    finally:
        conflicts = []
        for original, hidden in reversed(moved):
            if original.exists() or original.is_symlink():
                conflicts.append(str(original))
                continue
            try:
                hidden.rename(original)
            except OSError as error:
                conflicts.append(str(original) + ': ' + str(error))
        if conflicts:
            raise RuntimeError('Refusing to overwrite recreated build prefixes; originals retained under hidden names: ' + ', '.join(conflicts))

def clean_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('DYLD_', 'PYTHON', 'QT_', 'QML', 'CMAKE_', 'OPENSSL_', 'SSL_CERT_', 'FLAPART_')):
            env.pop(key)
    env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    env['QT_QPA_PLATFORM'] = 'offscreen'
    return env

def identities(paths):
    return {str(Path(path).absolute()): (Path(path).stat().st_dev, Path(path).stat().st_ino) for path in paths}

def restored(paths, original):
    try:
        return all(not Path(path).is_symlink() for path in paths) and identities(paths) == original
    except OSError:
        return False

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive-output', type=Path, required=True)
    parser.add_argument('--hide-build-prefix', type=Path, action='append', required=True)
    args = parser.parse_args()
    assert platform.system() == 'Darwin' and os.environ.get('CI') == 'true', 'Disposable native Mac CI required'
    candidate = args.candidate.resolve()
    baseline = args.baseline.resolve()
    output = args.output.resolve()
    archive = args.archive_output.resolve()
    runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()
    assert candidate.is_dir() and candidate.suffix == '.app' and not output.exists()
    assert not output.is_relative_to(candidate), 'Evidence must not enter candidate bundle'
    assert archive.is_relative_to(runner_temp) and not archive.is_relative_to(candidate) and not archive.is_relative_to(output) and not archive.exists()
    assert all(path.resolve().is_relative_to(runner_temp) and path.resolve() != runner_temp for path in args.hide_build_prefix)
    output.mkdir(parents=True)
    helper = Path(__file__).resolve().parents[1] / 'portable/package-runtime-probe.py'
    for prefix in args.hide_build_prefix:
        assert all(not path.resolve().is_relative_to(prefix.resolve()) for path in (archive, baseline, helper)), 'Probe inputs must remain available'
    original_prefixes = identities(args.hide_build_prefix)
    result = {'passed': False, 'release_qualified': False, 'runs': [], 'prefixes_restored': False}
    try:
        with tempfile.TemporaryDirectory(prefix='Flapart runtime relocation ', dir=os.environ.get('RUNNER_TEMP')) as temp:
            root = Path(temp) / 'relocated runtime'
            root.mkdir()
            bundle = root / candidate.name
            shutil.copytree(candidate, bundle, symlinks=True)
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive_bundle(bundle, archive)
            result['payload_sha256'] = digest(archive)
            python = bundle / 'Contents/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python'
            openssl = bundle / 'Contents/MacOS/openssl'
            assert python.is_file() and openssl.is_file()
            with hidden_prefixes(args.hide_build_prefix, root, output):
                for arch in ('arm64', 'x86_64'):
                    command = ['/usr/bin/arch', '-' + arch, str(python), '-I', '-B', str(helper),
                               '--archive', str(archive), '--runtime-root', str(root),
                               '--baseline-extension-manifest', str(baseline), '--baseline-extension-sha256', digest(baseline),
                               '--openssl', str(openssl), '--output', str(output / arch),
                               '--runtime-scope', 'relocated-package', '--target-platform', 'macos-universal2']
                    with (output / (arch + '.log')).open('w') as log:
                        subprocess.run(command, env=clean_environment(), stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
                    proof = json.loads((output / arch / 'python.json').read_text())
                    assert proof['passed'] and proof['process_architecture'] == arch
                    result['runs'].append({'process_architecture': arch, 'execution_mode': proof['execution_mode'], 'passed': True})
            result['prefixes_restored'] = restored(args.hide_build_prefix, original_prefixes)
            assert result['prefixes_restored'] and digest(archive) == result['payload_sha256']
            result['passed'] = True
    finally:
        result['prefixes_restored'] = restored(args.hide_build_prefix, original_prefixes)
        (output / 'qualification.json').write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    main()
