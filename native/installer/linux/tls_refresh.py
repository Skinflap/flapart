# SPDX-License-Identifier: GPL-3.0-or-later
"""Refresh the isolated runtime from a hash-pinned Ubuntu security package."""
import ctypes
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

VERSION = '3.0.2-0ubuntu1.30'
URL = 'https://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl3_3.0.2-0ubuntu1.30_amd64.deb'
SHA256 = 'd1b4636e32ac6d3b95d583ac05ac548b1aa248414bae1c51b14f54be0f8fd7bc'
SIZE = 1907006
FILES = {
    'usr/lib/x86_64-linux-gnu/libssl.so.3': '51fc92556f11ddce62f3f988d3fe973fab8fb4742032e61a713688581c924262',
    'usr/lib/x86_64-linux-gnu/libcrypto.so.3': '7cc817ff1841b59516d684f357bc0c3fc2cc52c3fa9b4ffb8ce8bdc215f02915',
    'usr/share/doc/libssl3/copyright': '6a7da622fe0637a334d2a8fc470852d2ffb77d9a2b2f930f854e32a41ad6ef35',
}


def refresh(runtime, cached_package=None):
    """Only mutate a new staging runtime; the caller commits it after success."""
    runtime = Path(runtime).resolve()
    incoming = Path(cached_package).open('rb') if cached_package else urllib.request.urlopen(URL, timeout=60)
    with incoming as stream:
        package = stream.read(SIZE + 1)
    if len(package) != SIZE or hashlib.sha256(package).hexdigest() != SHA256:
        raise ValueError('Ubuntu TLS package verification failed; existing installation is unchanged.')
    if package[:8] != b'!<arch>\n':
        raise ValueError('Invalid pinned Debian archive')
    offset = 8
    compressed = None
    while offset < len(package):
        header = package[offset:offset + 60]
        if len(header) != 60 or header[58:] != b'`\n':
            raise ValueError('Invalid Debian member header')
        size = int(header[48:58].strip())
        name = header[:16].strip().rstrip(b'/')
        offset += 60
        data = package[offset:offset + size]
        if len(data) != size:
            raise ValueError('Truncated Debian member')
        if name == b'data.tar.zst':
            if compressed is not None:
                raise ValueError('Duplicate Debian payload')
            compressed = data
        offset += size + size % 2
    if compressed is None:
        raise ValueError('Pinned Debian payload is missing')

    # Krita's verified AppImage already includes zstd. No system package manager,
    # root access, extra executable or Python module is needed for extraction.
    zstd_path = (runtime / 'usr/lib/libzstd.so.1').resolve()
    if not zstd_path.is_relative_to(runtime) or not zstd_path.is_file():
        raise ValueError('Verified runtime zstd library is unavailable')
    zstd = ctypes.CDLL(str(zstd_path))
    zstd.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    zstd.ZSTD_decompress.restype = ctypes.c_size_t
    zstd.ZSTD_isError.argtypes = [ctypes.c_size_t]
    zstd.ZSTD_isError.restype = ctypes.c_uint
    maximum = 16 * 1024 * 1024
    output = ctypes.create_string_buffer(maximum)
    source = ctypes.create_string_buffer(compressed)
    count = zstd.ZSTD_decompress(output, maximum, source, len(compressed))
    if zstd.ZSTD_isError(count) or count > maximum:
        raise ValueError('Pinned TLS payload could not be decompressed within its limit')
    selected = {}
    with tarfile.open(fileobj=io.BytesIO(output.raw[:count]), mode='r:') as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            if name not in FILES:
                continue
            if name in selected or not member.isfile() or member.size > maximum:
                raise ValueError('Invalid TLS payload member')
            content = archive.extractfile(member).read()
            if hashlib.sha256(content).hexdigest() != FILES[name]:
                raise ValueError('TLS payload file hash mismatch')
            selected[name] = content
    if selected.keys() != FILES.keys():
        raise ValueError('TLS payload is incomplete')
    for name in ('libssl.so.3', 'libcrypto.so.3'):
        target = runtime / 'usr/lib' / name
        if target.is_symlink() or not target.is_file():
            raise ValueError('Unexpected existing TLS runtime layout')
        target.write_bytes(selected['usr/lib/x86_64-linux-gnu/' + name])
    notices = runtime.parent / 'third-party/ubuntu-openssl'
    notices.mkdir(parents=True)
    (notices / 'COPYRIGHT').write_bytes(selected['usr/share/doc/libssl3/copyright'])
    receipt = {'package': 'libssl3', 'version': VERSION, 'source_package': 'openssl',
               'origin': 'Ubuntu jammy-security', 'url': URL, 'sha256': SHA256,
               'files': FILES, 'source_url': 'https://launchpad.net/ubuntu/+source/openssl/' + VERSION}
    (notices / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
