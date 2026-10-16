#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record an actual build/package command and its native-file changes, fail closed."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time

MODULE = Path(__file__).resolve().parents[1] / 'source-qualification/native_metadata.py'
spec = importlib.util.spec_from_file_location('provenance_native_metadata', MODULE)
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)
# Deliberately no arbitrary --env or inherited credential variables.
ENV_KEYS = frozenset('PATH HOME USER LOGNAME TMPDIR TMP TEMP SYSTEMROOT WINDIR COMSPEC PATHEXT LANG LC_ALL LC_CTYPE TZ SDKROOT DEVELOPER_DIR MACOSX_DEPLOYMENT_TARGET QMAKE_MACOSX_DEPLOYMENT_TARGET CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS AR RANLIB RC MAKE MAKEFLAGS CMAKE_PREFIX_PATH CMAKE_BUILD_TYPE PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PYTHONHOME PYTHONPATH DYLD_FRAMEWORK_PATH DYLD_LIBRARY_PATH OPENSSL_MODULES OPENSSL_CONF SSL_CERT_FILE SSL_CERT_DIR SOURCE_DATE_EPOCH ZERO_AR_DATE CI RUNNER_TEMP'.split())
MAGIC = {b'!<ar',b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca', b'\x7fELF'}
SECRET = re.compile(r'(?i)(?:^|[?&\s])(?:--?)?(?:password|passwd|token|access[_-]?token|secret|api[_-]?key|authorization)(?:=|:|\s|$)|://[^/\s]+:[^/\s]+@')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def artifact(path):
    path = Path(path)
    return {'path': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size}

def file_identity(path):
    requested = Path(path).absolute()
    resolved = requested.resolve(strict=True)
    require(resolved.is_file(), 'Expected executable/helper regular file')
    before = resolved.stat()
    value = digest(resolved)
    after = resolved.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns), 'Executable/helper changed while hashing')
    return {'requested_path': str(requested), 'resolved_path': str(resolved), 'sha256': value, 'bytes': after.st_size}

def environment(source):
    result = {key: value for key, value in source.items() if key in ENV_KEYS}
    for value in result.values():
        require(not SECRET.search(value), 'Credential-like build environment value refused')
    return result

def captured_metadata(data):
    """Include static native build inputs without inventing an archive UUID."""
    if data.startswith(b'!<arch>\n'):
        offset = 8
        members = 0
        arches = set()
        identities = set()
        while offset < len(data):
            require(offset + 60 <= len(data), 'Truncated static archive header')
            header = data[offset:offset + 60]
            require(header[58:60] == b'`\n', 'Malformed static archive member')
            size = int(header[48:58].strip())
            require(size >= 0 and offset + 60 + size <= len(data), 'Invalid static archive size')
            body = data[offset + 60:offset + 60 + size]
            name = header[:16].strip()
            if name.startswith(b'#1/'):
                length = int(name[3:])
                require(0 <= length <= len(body), 'Invalid BSD archive filename')
                body = body[length:]
            if body[:4] in MAGIC - {b'!<ar'} or body[:2] == b'MZ':
                info = metadata.parse(body)
                if info:
                    arches.update(info['architectures'])
                    identities.update(info['macho_uuids'])
            members += 1
            offset += 60 + size + (size % 2)
        require(offset == len(data), 'Missing static archive alignment byte')
        return {'format': 'static-archive', 'architectures': sorted(arches), 'macho_uuids': [],
                'slices': [{'architectures': sorted(arches), 'member_count': members, 'member_uuids': sorted(identities)}], 'native_dependencies': []}
    fats = {b'\xca\xfe\xba\xbe': ('>', 20), b'\xbe\xba\xfe\xca': ('<', 20), b'\xca\xfe\xba\xbf': ('>', 32), b'\xbf\xba\xfe\xca': ('<', 32)}
    if data[:4] in fats and len(data) >= 8:
        endian, stride = fats[data[:4]]
        count = struct.unpack_from(endian + 'I', data, 4)[0]
        if 0 < count <= 16 and 8 + count * stride <= len(data):
            first, _ = struct.unpack_from(endian + ('II' if stride == 20 else 'QQ'), data, 16)
            if data[first:first + 8] == b'!<arch>\n':
                slices, spans = [], []
                names = {0x1000007: 'x86_64', 0x100000c: 'arm64'}
                for index in range(count):
                    cpu = struct.unpack_from(endian + 'I', data, 8 + index * stride)[0]
                    offset, size = struct.unpack_from(endian + ('II' if stride == 20 else 'QQ'), data, 16 + index * stride)
                    require(cpu in names and offset >= 8 + count * stride and offset + size <= len(data), 'Invalid fat archive slice')
                    require(all(offset + size <= a or offset >= b for a, b in spans), 'Overlapping fat archive slices')
                    spans.append((offset, offset + size))
                    info = captured_metadata(data[offset:offset + size])
                    require(info and info['format'] == 'static-archive' and set(info['architectures']) <= {names[cpu]}, 'Fat static archive member architecture mismatch')
                    slices.append(dict(info['slices'][0], architecture=names[cpu]))
                require(len({row['architecture'] for row in slices}) == count, 'Duplicate fat static archive architecture')
                return {'format': 'static-archive', 'architectures': sorted(row['architecture'] for row in slices), 'macho_uuids': [], 'slices': slices, 'native_dependencies': []}
    return metadata.parse(data)

def snapshot(root, blob_dir=None):
    root = Path(root).absolute()
    require(not root.is_symlink(), 'Captured tree root is a symlink')
    canonical = root.resolve()
    if not root.exists():
        return {'root': str(canonical), 'exists': False, 'files': []}
    require(root.is_dir(), 'Captured tree must be a directory')
    rows = []
    for path in sorted(root.rglob('*')):
        resolved = path.resolve()
        require(resolved.is_relative_to(canonical), 'Captured tree contains an escaping symlink')
        require(path.exists(), 'Captured tree contains a broken symlink')
        mode = path.lstat().st_mode
        require(stat.S_ISLNK(mode) or stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'Unsupported filesystem entry in captured tree')
        if path.is_dir():
            if path.is_symlink():
                rows.append({'path': path.relative_to(root).as_posix(), 'kind': 'directory-alias', 'target': os.readlink(path)})
            continue
        if path.is_symlink():
            rows.append({'path': path.relative_to(root).as_posix(), 'kind': 'file-alias', 'target': os.readlink(path), 'resolved_path': resolved.relative_to(canonical).as_posix()})
            continue
        # Open without following a swapped final-component symlink. Check stable
        # inode/size/mtime around reads; this is not a hostile filesystem sandbox.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            first = stream.read(4)
            if first not in MAGIC and first[:2] != b'MZ':
                continue
            require(before.st_size <= 2 * 1024**3, 'Oversized native file')
            data = first + stream.read()
            after = os.fstat(stream.fileno())
        current = path.stat()
        require((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns) == (current.st_ino, current.st_size, current.st_mtime_ns), 'Native file changed while capturing')
        info = captured_metadata(data)
        if info is None:  # e.g. Java CAFEBABE, not Mach-O.
            continue
        value = hashlib.sha256(data).hexdigest()
        row = {'path': path.relative_to(root).as_posix(), 'kind': 'native', 'mode': stat.S_IMODE(current.st_mode), 'bytes': len(data), 'sha256': value, **info}
        if blob_dir is not None:
            blob_dir.mkdir(mode=0o700, exist_ok=True)
            blob = blob_dir / value
            if blob.exists():
                require(not blob.is_symlink() and digest(blob) == value, 'Native byte evidence collision')
            else:
                with blob.open('xb') as stream:
                    stream.write(data)
                blob.chmod(0o600)
            row['retained_bytes'] = 'native-bytes/' + value
        rows.append(row)
    return {'root': str(canonical), 'exists': True, 'files': rows}

def differences(before, after):
    rows = []
    for label in sorted(set(before) & set(after)):
        left = {r['path']: r for r in before.get(label, {}).get('files', [])}
        right = {r['path']: r for r in after.get(label, {}).get('files', [])}
        for name in sorted(set(left) | set(right)):
            if left.get(name) != right.get(name):
                rows.append({'tree': label, 'path': name, 'change': 'added' if name not in left else 'removed' if name not in right else 'modified', 'before': left.get(name), 'after': right.get(name)})
    return rows

def validate_layout(trees, evidence):
    require(trees, 'At least one named native tree is required')
    destination = evidence.resolve()
    for label, root in trees.items():
        require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', label), 'Invalid tree label')
        require(not root.is_symlink(), 'Captured tree root is a symlink')
        resolved = root.resolve()
        require(not destination.is_relative_to(resolved) and not resolved.is_relative_to(destination), 'Evidence and captured trees must not contain one another')
    require(len({p.resolve() for p in trees.values()}) == len(trees), 'Duplicate captured tree')

def record_stage(stage, argv, cwd, trees, evidence, helpers=(), tools=(), source_env=None, timeout=None, retain_native_bytes=False):
    """Always return a durable failed receipt after execution/setup begins.

    Layout/credential checks happen before creating evidence or spawning anything.
    No shell expansion; no historic/provided output hashes are accepted.
    """
    evidence = Path(evidence).absolute()
    trees = {label: Path(root).absolute() for label, root in trees.items()}
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,95}', stage), 'Invalid stage label')
    require(argv and all(isinstance(a, str) and '\x00' not in a for a in argv), 'Expected explicit argument array')
    require(not any(SECRET.search(a) for a in argv), 'Credential-like command argument refused')
    validate_layout(trees, evidence)
    require(not evidence.exists() and not evidence.is_symlink(), 'Evidence directory must be fresh')
    env = environment(os.environ if source_env is None else source_env)
    evidence.mkdir(parents=True, mode=0o700)
    receipt = {'schema': 1, 'stage': stage, 'started_utc': timestamp(), 'passed': False,
               'historical_reconstruction': False, 'source_closure_complete': False, 'release_qualified': False,
               'requested_argv': list(argv), 'cwd': str(Path(cwd).resolve()), 'environment': env,
               'returncode': None, 'before': {}, 'after': {}, 'errors': [], 'tools': [], 'helpers': [],
               'native_byte_retention': bool(retain_native_bytes)}
    blob_dir = evidence / 'native-bytes' if retain_native_bytes else None
    stdout = evidence / 'stdout.log'
    stderr = evidence / 'stderr.log'
    stdout.touch()
    stderr.touch()
    start = time.monotonic()
    try:
        require(Path(cwd).is_dir(), 'Command working directory missing')
        requested_executable = str(Path(cwd) / argv[0]) if ('/' in argv[0] or '\\' in argv[0]) and not Path(argv[0]).is_absolute() else argv[0]
        executable = shutil.which(requested_executable, path=env.get('PATH', os.defpath))
        require(executable is not None, 'Command executable not found')
        executable = str(Path(executable).resolve())
        receipt['argv'] = [executable, *argv[1:]]
        receipt['tools'] = [file_identity(executable)] + [file_identity(p) for p in tools]
        receipt['helpers'] = [file_identity(Path(__file__)), file_identity(MODULE)] + [file_identity(p) for p in helpers]
        for label, root in trees.items():
            receipt['before'][label] = snapshot(root, blob_dir)
        # Persist before-images before starting the child; capture is not retroactive.
        (evidence / 'before.json').write_text(json.dumps(receipt['before'], indent=2) + '\n')
        receipt['before_snapshot'] = artifact(evidence / 'before.json')
        with stdout.open('wb') as out, stderr.open('wb') as err:
            process = subprocess.Popen(receipt['argv'], cwd=cwd, env=env, stdout=out, stderr=err, start_new_session=os.name == 'posix')
            try:
                process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                receipt['returncode'] = process.returncode
                raise
        receipt['returncode'] = process.returncode
        if process.returncode:
            receipt['errors'].append('Command exited unsuccessfully')
    except subprocess.TimeoutExpired:
        receipt['errors'].append('Command timed out; POSIX process group or Windows direct child was terminated')
        receipt['timed_out'] = True
    except Exception as error:
        # Do not include exception repr: third-party exceptions may expose inputs.
        receipt['errors'].append(str(error) if isinstance(error, ValueError) else type(error).__name__ + ': stage setup/execution failed')
    finally:
        for label, root in trees.items():
            try:
                receipt['after'][label] = snapshot(root, blob_dir)
            except Exception as error:
                receipt['errors'].append(type(error).__name__ + ': after snapshot failed for ' + label)
        receipt['comparison_complete'] = set(receipt['before']) == set(trees) == set(receipt['after'])
        receipt['changed_files'] = differences(receipt['before'], receipt['after'])
        for row in receipt['tools'] + receipt['helpers']:
            try:
                row['sha256_after'] = digest(row['resolved_path'])
                if row['sha256_after'] != row['sha256']:
                    receipt['errors'].append('Recorded tool/helper changed during stage')
            except OSError:
                receipt['errors'].append('Recorded tool/helper missing after stage')
        receipt['stdout'] = artifact(stdout)
        receipt['stderr'] = artifact(stderr)
        receipt['finished_utc'] = timestamp()
        receipt['duration_seconds'] = round(time.monotonic() - start, 6)
        receipt['passed'] = receipt['returncode'] == 0 and not receipt['errors']
        temporary = evidence / 'receipt.json.tmp'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(evidence / 'receipt.json')
    return receipt

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', required=True)
    p.add_argument('--cwd', type=Path, required=True)
    p.add_argument('--tree', action='append', required=True, metavar='LABEL=PATH')
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--helper', type=Path, action='append', default=[])
    p.add_argument('--tool', type=Path, action='append', default=[])
    p.add_argument('--timeout', type=float)
    p.add_argument('--retain-native-bytes', action='store_true', help='Explicit local private input/output byte retention; never uploads')
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    trees = {}
    for item in args.tree:
        label, sep, value = item.partition('=')
        require(sep and value and label not in trees, 'Expected unique LABEL=PATH trees')
        trees[label] = Path(value)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    result = record_stage(args.stage, command, args.cwd, trees, args.evidence, args.helper, args.tool, timeout=args.timeout, retain_native_bytes=args.retain_native_bytes)
    print('Stage evidence: ' + str(args.evidence / 'receipt.json'))
    raise SystemExit(0 if result['passed'] else 1)

if __name__ == '__main__':
    main()
