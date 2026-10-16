"""Bind package inputs to maintained TLS and optional rebuilt Qt receipts."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def contained(root, name):
    part = PurePosixPath(name)
    if not name or part.is_absolute() or '..' in part.parts or '\\' in name:
        raise ValueError('Unsafe SDK receipt path')
    path = root / part
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('SDK path escapes its root')
    return path


def validate(prefix, maintained, tls_path, qt_path=None):
    prefix, maintained = prefix.resolve(), maintained.resolve()
    baseline = maintained / 'sdk'
    tls = json.loads(tls_path.read_text())
    if not tls.get('promoted') or Path(tls['sdk']).resolve() != baseline:
        raise ValueError('Incorrect maintained TLS SDK receipt')
    qt_entries = {}
    if qt_path:
        qt = json.loads(qt_path.read_text())
        if (not qt.get('promoted') or Path(qt['sdk']).resolve() != prefix
                or Path(qt['baseline_sdk']).resolve() != baseline or prefix == baseline):
            raise ValueError('Incorrect rebuilt Qt SDK receipt')
        build_path = prefix.parent / 'evidence/result.json'
        assembly_path = prefix.parent / 'evidence/assembly.json'
        if (digest(build_path) != qt['build_receipt_sha256']
                or digest(assembly_path) != qt['assembly_receipt_sha256']):
            raise ValueError('Qt build provenance changed')
        build, assembly = json.loads(build_path.read_text()), json.loads(assembly_path.read_text())
        if (not build['compiled'] or not build['universal_assembled']
                or not assembly['assembled'] or assembly['conflicts']):
            raise ValueError('Incomplete Qt build provenance')
        if Path(build['baseline_sdk']).resolve() != baseline:
            raise ValueError('Qt build used a different baseline')
        for row in qt['copied']:
            name = row['path']
            if name in qt_entries:
                raise ValueError('Duplicate Qt receipt entry')
            qt_entries[name] = {k: v for k, v in row.items() if k != 'path'}
        expected = {name: row for name, row in assembly['outputs'].items() if row['kind'] != 'directory'}
        if qt_entries != expected:
            raise ValueError('Qt promotion does not cover exact assembled output')
        for name, row in qt_entries.items():
            path = contained(prefix, name)
            if row['kind'] == 'link':
                if not path.is_symlink() or str(path.readlink()) != row['target'] or not path.exists():
                    raise ValueError('Promoted Qt link changed: ' + name)
            elif row['kind'] in ('file', 'native'):
                if (path.is_symlink() or not path.is_file() or digest(path) != row['sha256']
                        or path.stat().st_mode & 0o777 != row['mode']):
                    raise ValueError('Promoted Qt component changed: ' + name)
            else:
                raise ValueError('Unknown Qt receipt entry')
    elif prefix != baseline:
        raise ValueError('New SDK requires its Qt promotion receipt')
    checked = []
    for row in tls['copied']:
        name = row['path']
        original = contained(baseline, name)
        if not original.is_file() or digest(original) != row['sha256']:
            raise ValueError('Original maintained component changed: ' + name)
        current = contained(prefix, name)
        # A changed maintained QtNetwork binary must be covered by the complete
        # new assembly, rather than silently weakening the TLS receipt check.
        if name not in qt_entries and (not current.is_file() or digest(current) != row['sha256']):
            raise ValueError('Maintained component changed in final SDK: ' + name)
        checked.append(name)
    if not checked:
        raise ValueError('Empty maintained TLS receipt')
    return {'validated': True, 'tls_receipt_sha256': digest(tls_path),
            'qt_receipt_sha256': digest(qt_path) if qt_path else None,
            'maintained_components': checked, 'rebuilt_qt_entries': len(qt_entries),
            'runtime_qualified': False, 'release_qualified': False}
