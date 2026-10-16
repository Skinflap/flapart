# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply a verified CPython refresh only to the installer's new staging runtime."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import urllib.request
import zipfile

VERSION = '3.13.16'
URL = 'https://accounts.flaptown.com/flapsoft/downloads/flapart-python-3.13.16-linux-x86_64.zip'
SHA256 = '04e4be4f38749d1ba9f0286d6d1ff8ff51d709cb94cafd736fcde730392cc843'
SIZE = 34595559
SOURCE_URL = 'https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tar.xz'
SOURCE_SHA256 = 'f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d'
SOURCE_PACKAGE_URL = 'https://accounts.flaptown.com/flapsoft/downloads/flapart-python-3.13.16-linux-source.zip'
SOURCE_PACKAGE_SHA256 = 'cede11dd3f397a4e1ac9f8fc8d7b78b3572419bac7f1842ec1ed15f63dc12c4e'
STDLIB = 'usr/lib/python3.13/'
EXACT = {'usr/lib/libpython3.13.so.1.0', 'usr/lib/libpython3.so', 'usr/bin/python3.13', 'third-party/cpython/LICENSE'}
MAX_EXPANDED = 128 * 1024 * 1024
MAX_FILE = 33 * 1024 * 1024


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate Python manifest key')
        result[key] = value
    return result


def safe_path(name):
    if not isinstance(name, str) or len(name) > 240 or not re.fullmatch(r'[A-Za-z0-9_./@+ -]+', name):
        raise ValueError('Unsafe Python payload path')
    parts = name.split('/')
    if any(part in ('', '.', '..', 'site-packages', '__pycache__') for part in parts) or name.endswith(('.pyc', '.pyo')):
        raise ValueError('Unexpected Python payload path')
    if name not in EXACT and not (name.startswith(STDLIB) and len(name) > len(STDLIB)):
        raise ValueError('Python payload is outside the interpreter scope')


def validate(package):
    """Check every path/member/hash before any staging runtime change."""
    archive = zipfile.ZipFile(io.BytesIO(package))
    entries = archive.infolist()
    if not 1 <= len(entries) <= 3000:
        raise ValueError('Python archive entry limit exceeded')
    names = set()
    total = 0
    for entry in entries:
        if entry.filename in names or entry.is_dir() or entry.flag_bits & 1 or entry.compress_type != zipfile.ZIP_DEFLATED:
            raise ValueError('Invalid or duplicate Python archive entry')
        names.add(entry.filename)
        if entry.create_system != 3 or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG:
            raise ValueError('Python archive contains a non-regular file')
        if entry.file_size < 0 or entry.file_size > MAX_FILE:
            raise ValueError('Python archive file exceeds its limit')
        total += entry.file_size
        if total > MAX_EXPANDED:
            raise ValueError('Python archive expansion limit exceeded')
        if entry.filename != 'PYTHON-REFRESH.json':
            safe_path(entry.filename)
    if 'PYTHON-REFRESH.json' not in names or archive.getinfo('PYTHON-REFRESH.json').file_size > 1024 * 1024:
        raise ValueError('Python archive manifest is missing or too large')
    manifest = json.loads(archive.read('PYTHON-REFRESH.json'), object_pairs_hook=unique)
    if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in {
        'format': 'flapart-python-refresh', 'version': 1, 'python_version': VERSION,
        'platform': 'linux-x86_64', 'soabi': 'cpython-313-x86_64-linux-gnu',
        'source_sha256': SOURCE_SHA256, 'source_url': SOURCE_URL,
        'glibc_maximum': '2.35', 'sigstore_verified': True,
    }.items()):
        raise ValueError('Unexpected Python source/runtime manifest')
    files = manifest.get('files')
    if not isinstance(files, dict) or len(files) != 2406 or names != set(files) | {'PYTHON-REFRESH.json'} or not EXACT <= set(files):
        raise ValueError('Python manifest file set differs')
    for name, item in files.items():
        safe_path(name)
        if any(str(parent) in files for parent in PurePosixPath(name).parents):
            raise ValueError('Python archive file/folder collision')
        mode = 0o755 if name == 'usr/bin/python3.13' else 0o644
        if not isinstance(item, dict) or set(item) != {'size', 'sha256', 'mode'} or type(item['size']) is not int or not 0 <= item['size'] <= MAX_FILE or item['mode'] != mode or not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
            raise ValueError('Invalid Python file manifest')
        entry = archive.getinfo(name)
        if entry.file_size != item['size'] or stat.S_IMODE(entry.external_attr >> 16) != mode:
            raise ValueError('Python file metadata differs')
        if hashlib.sha256(archive.read(name)).hexdigest() != item['sha256']:
            raise ValueError('Python payload file verification failed')
    return archive, manifest


def no_links(path, root):
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError('Unexpected link in staged Python runtime')
        current = current.parent
    if root.is_symlink():
        raise ValueError('Unexpected staged runtime link')


def refresh(runtime, cached_package=None):
    runtime = Path(runtime).resolve()
    incoming = Path(cached_package).open('rb') if cached_package else urllib.request.urlopen(urllib.request.Request(URL, headers={'User-Agent': 'Flapart-Studio/0.1.3 (+https://flaptown.com/flapsoft/)'}), timeout=60)
    with incoming as stream:
        package = stream.read(SIZE + 1)
    if len(package) != SIZE or hashlib.sha256(package).hexdigest() != SHA256:
        raise ValueError('Python package verification failed; existing installation is unchanged.')
    archive, manifest = validate(package)
    with archive:
        stdlib = runtime / STDLIB
        site = stdlib / 'site-packages'
        no_links(site, runtime)
        if not site.is_dir():
            raise ValueError('Original Krita Python site-packages are missing')
        for name in manifest['files']:
            target = (runtime.parent if name.startswith('third-party/') else runtime) / name
            no_links(target, runtime.parent)
        saved_site = runtime.parent / '.python-site-packages-preserved'
        if saved_site.exists() or saved_site.is_symlink():
            raise ValueError('Unexpected Python staging directory')
        # All archive checks finished. Only this new install staging tree changes.
        site.rename(saved_site)
        shutil.rmtree(stdlib)
        stdlib.mkdir()
        saved_site.rename(site)
        for name, item in manifest['files'].items():
            target = (runtime.parent if name.startswith('third-party/') else runtime) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('wb') as output:
                output.write(archive.read(name))
            target.chmod(item['mode'])
        receipt = {'version': VERSION, 'url': URL, 'sha256': SHA256, 'bytes': SIZE,
                   'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
                   'source_package_url': SOURCE_PACKAGE_URL, 'source_package_sha256': SOURCE_PACKAGE_SHA256,
                   'sigstore_verified_at_build': True, 'glibc_floor': '2.35',
                   'whole_stdlib_replaced': True, 'original_site_packages_preserved': True}
        notice = runtime.parent / 'third-party/cpython'
        (notice / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt
