#!/usr/bin/env python3
"""Private unqualified candidate retention using GnuPG, never a release gate."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

LIMIT = 8 * 1024**3
MAX_FILES = 4096

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def safe_name(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('unsafe member')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')) or value == 'inventory.json':
        raise ValueError('unsafe member')
    return value

def fingerprint(value):
    if not re.fullmatch(r'[A-Fa-f0-9]{40}', value):
        raise ValueError('full v4 recipient fingerprint required')
    return value.upper()

def validate_inventory(obj):
    if set(obj) != {'schema', 'candidate', 'files'} or obj['schema'] != 1:
        raise ValueError('invalid inventory')
    rows = obj['files']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError('invalid file count')
    names = set(); total = 0
    for row in rows:
        if set(row) != {'path', 'bytes', 'sha256'}:
            raise ValueError('invalid file entry')
        name = safe_name(row['path'])
        if name in names or type(row['bytes']) is not int or not 0 <= row['bytes'] <= LIMIT or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('invalid file metadata')
        names.add(name); total += row['bytes']
    if total > LIMIT or obj['candidate'] not in names or len(names) < 2:
        raise ValueError('candidate and stage evidence required within size bound')
    for name in names:
        if any(str(p) in names for p in PurePosixPath(name).parents):
            raise ValueError('file-parent collision')
    return rows

def regular(root, name):
    p = root
    for part in PurePosixPath(name).parts:
        p = p / part
        if p.is_symlink():
            raise ValueError('input symlink forbidden')
    if not p.is_file():
        raise ValueError('missing regular input')
    return p

def gpg(home, *args, **kwargs):
    # No personal config, keyserver discovery, or inherited default recipients.
    result = subprocess.run(['gpg', '--no-options', '--homedir', str(home), '--batch',
        '--no-auto-key-retrieve', *args], check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        # Expose only bounded IPC diagnostics, not imported identities or key data.
        terms = (b'socket', b'ipc', b'keyboxd', b'agent', b'connect')
        diagnostic = b'\n'.join(line for line in result.stderr.splitlines()
                                if any(term in line.lower() for term in terms))[:1024]
        raise RuntimeError('GnuPG failed (exit %s): %s' %
                           (result.returncode, diagnostic.decode('utf-8', errors='replace') or 'no IPC diagnostic'))
    return result

@contextlib.contextmanager
def ephemeral_gpg_home():
    # macOS temporary payload paths can exceed AF_UNIX's socket-name bound.
    # Keep daemon sockets in a separate, short, private directory. Never use
    # the caller's personal keyring or put private keys in the payload tree.
    parent = Path('/tmp').resolve(strict=True) if os.name == 'posix' else None
    with tempfile.TemporaryDirectory(prefix='flpg-', dir=parent) as name:
        home = Path(name).resolve()
        home.chmod(0o700)
        if os.name == 'posix' and len(os.fsencode(home / 'S.keyboxd')) >= 90:
            raise ValueError('Temporary GnuPG socket path is too long')
        try:
            yield home
        finally:
            # Stop only daemons belonging to this disposable home, before its
            # files disappear. The local release key home is never affected.
            subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'all'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False)

def encrypt(root, inventory_path, public_key, recipient, output):
    recipient = fingerprint(recipient)
    inventory = json.loads(inventory_path.read_text()); rows = validate_inventory(inventory)
    root = root.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError('output already exists')
    with tempfile.TemporaryDirectory(prefix='.retention-', dir=output.parent) as tmp, ephemeral_gpg_home() as home:
        tmp = Path(tmp); os.chmod(tmp, 0o700)
        gpg(home, '--import', str(public_key.resolve(strict=True)))
        if b'sec:' in gpg(home, '--with-colons', '--list-secret-keys').stdout:
            raise ValueError('encryption input must contain public keys only')
        listing = gpg(home, '--with-colons', '--list-keys').stdout.decode()
        primary = []; pending = False
        for line in listing.splitlines():
            fields = line.split(':')
            if fields[0] == 'pub': pending = True
            elif fields[0] == 'fpr' and pending:
                primary.append(fields[9]); pending = False
        if primary != [recipient]:
            raise ValueError('public key primary fingerprint mismatch or extra keys')
        payload = tmp / 'payload.tar'
        with tarfile.open(payload, 'w') as tar:
            manifest = tmp / 'inventory.json'; manifest.write_text(json.dumps(inventory, sort_keys=True))
            tar.add(manifest, arcname='inventory.json', recursive=False)
            for row in rows:
                src = regular(root, row['path'])
                # Snapshot each input privately, then verify the exact bytes archived.
                staged = tmp / 'snapshot'; shutil.copyfile(src, staged)
                if staged.stat().st_size != row['bytes'] or digest(staged) != row['sha256']:
                    raise ValueError('input size/hash mismatch')
                tar.add(staged, arcname=row['path'], recursive=False); staged.unlink()
        encrypted = tmp / 'retained.gpg'
        gpg(home, '--trust-model', 'always', '--recipient', recipient,
            '--output', str(encrypted), '--encrypt', str(payload))
        os.chmod(encrypted, 0o600)
        os.link(encrypted, output)  # atomic publication, never replace an existing path
    return {'encrypted_sha256': digest(output), 'encrypted_bytes': output.stat().st_size,
            'recipient': recipient, 'release_qualified': False}

def decrypt(encrypted, expected_sha, home, recipient, output):
    recipient = fingerprint(recipient)
    if digest(encrypted) != expected_sha or output.exists() or output.is_symlink():
        raise ValueError('ciphertext mismatch or output exists')
    with tempfile.TemporaryDirectory(prefix='.retention-', dir=output.parent) as tmp:
        tmp = Path(tmp); os.chmod(tmp, 0o700)
        payload = tmp / 'payload.tar'; status = tmp / 'status'
        with open(status, 'wb') as statusfile, open(payload, 'wb') as out:
            process = subprocess.Popen(['gpg', '--no-options', '--homedir', str(home), '--batch',
                '--no-auto-key-retrieve', '--status-fd', str(statusfile.fileno()), '--decrypt', str(encrypted)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=(statusfile.fileno(),))
            try:
                total = 0
                while True:
                    block = process.stdout.read(1024**2)
                    if not block: break
                    total += len(block)
                    if total > LIMIT + 16 * 1024**2: raise ValueError('decrypted payload exceeds bound')
                    out.write(block)
                if process.wait() != 0: raise ValueError('GPG authentication/decryption failed')
            finally:
                if process.poll() is None: process.kill(); process.wait()
                process.stdout.close()
        lines = status.read_text().splitlines()
        keys = [x.split() for x in lines if x.startswith('[GNUPG:] DECRYPTION_KEY ')]
        if len(keys) != 1 or keys[0][3] != recipient or '[GNUPG:] DECRYPTION_OKAY' not in lines or '[GNUPG:] GOODMDC' not in lines:
            raise ValueError('wrong recipient or missing authenticated decryption')
        unpack = tmp / 'unpacked'; unpack.mkdir(mode=0o700)
        with tarfile.open(payload, 'r:') as tar:
            members = []
            for member in tar:
                if len(members) >= MAX_FILES + 1 or not member.isfile() or member.sparse is not None or member.size > LIMIT:
                    raise ValueError('unsafe tar member')
                members.append(member)
            names = [x.name for x in members]
            if len(set(names)) != len(names) or names.count('inventory.json') != 1:
                raise ValueError('duplicate or missing inventory')
            manifest = next(x for x in members if x.name == 'inventory.json')
            if manifest.size > 2 * 1024**2: raise ValueError('inventory too large')
            inventory = json.loads(tar.extractfile(manifest).read()); rows = validate_inventory(inventory)
            if set(names) != {'inventory.json', *(r['path'] for r in rows)}:
                raise ValueError('unlisted or missing members')
            by_name = {m.name: m for m in members}
            for row in rows:
                member = by_name[row['path']]
                if member.size != row['bytes']: raise ValueError('member size mismatch')
                dest = unpack / row['path']; dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tar.extractfile(member) as src, open(dest, 'xb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o600)
                if digest(dest) != row['sha256']: raise ValueError('member digest mismatch')
            (unpack / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
        output.mkdir(mode=0o700)  # never replace or merge prior directories
        try:
            for child in unpack.iterdir(): shutil.move(str(child), output / child.name)
        except BaseException:
            shutil.rmtree(output); raise
    return {'candidate': inventory['candidate'], 'files': len(rows), 'release_qualified': False}

def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('encrypt'); e.add_argument('--root', type=Path, required=True); e.add_argument('--inventory', type=Path, required=True); e.add_argument('--public-key', type=Path, required=True)
    d = sub.add_parser('decrypt'); d.add_argument('--encrypted', type=Path, required=True); d.add_argument('--sha256', required=True); d.add_argument('--gnupg-home', type=Path, required=True)
    for parser in (e, d): parser.add_argument('--recipient', required=True); parser.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'encrypt': result = encrypt(a.root, a.inventory, a.public_key, a.recipient, a.output)
    else: result = decrypt(a.encrypted, a.sha256, a.gnupg_home, a.recipient, a.output)
    print(json.dumps(result))

if __name__ == '__main__': main()
