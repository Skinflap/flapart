"""Real disposable-key encryption of harmless fixtures; no API/native claims."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import protocol as p

RETENTION = Path(__file__).resolve().parents[3] / 'distribution/private-retention/retain.py'
spec = importlib.util.spec_from_file_location('exchange_retention', RETENTION)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


@unittest.skipUnless(shutil.which('gpg') and shutil.which('gpgconf'), 'GnuPG required')
class EncryptedExchange(unittest.TestCase):
    def test_actual_encryption_reconstruction_and_tamper_refusal(self):
        # Canonical short path works with macOS /tmp aliases and GPG sockets.
        with tempfile.TemporaryDirectory(prefix='flpex-', dir=Path('/tmp').resolve()) as tmp:
            base = Path(tmp).resolve()
            home = base / 'key'
            home.mkdir(mode=0o700)
            try:
                r.gpg(home, '--pinentry-mode', 'loopback', '--passphrase', '',
                      '--quick-generate-key', 'Disposable exchange fixture',
                      'rsa2048', 'encr', '1d')
                listing = r.gpg(home, '--with-colons', '--list-keys').stdout.decode()
                fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
                key = r.gpg(home, '--armor', '--export', fingerprint).stdout
                public = base / 'public.asc'
                public.write_bytes(key)
                src = base / 'source'
                src.mkdir(mode=0o700)
                values = {name: b'Harmless exact exchange fixture: ' + name.encode() for name in p.FILES}
                paths = {name: src / name for name in p.FILES}
                for name, path in paths.items():
                    path.write_bytes(values[name])
                binding = dict(repository='owner/repo', workflow='.github/workflows/fixture.yml',
                               run_id=10, attempt=1, commit='a'*40, job_id=20,
                               architecture='arm64', operator_id=30,
                               candidate_sha256=p.digest(values[p.FILES[0]]),
                               candidate_bytes=len(values[p.FILES[0]]),
                               inventory_sha256=p.digest(values[p.FILES[1]]),
                               manifest_sha256=p.digest(values[p.FILES[2]]))
                request = p.request(binding, key, fingerprint, 'b'*64, 100, 1000)
                packed = p.pack(request, paths, base / 'packed', 200)
                cipher = base / 'candidate.gpg'
                encrypted = r.encrypt(packed, packed / 'inventory.json', public, fingerprint, cipher)
                response = p.response(request, cipher, 40, 50, 200)
                self.assertEqual(response['sha256'], encrypted['encrypted_sha256'])
                restored = base / 'restored'
                decrypted = r.decrypt(cipher, response['sha256'], home, fingerprint, restored)
                p.validate_pack(restored, request, 200)
                for name, value in values.items():
                    self.assertEqual((restored / name).read_bytes(), value)
                self.assertFalse(encrypted['release_qualified'])
                self.assertFalse(decrypted['release_qualified'])
                self.assertFalse(p.decode((restored / 'exchange.json').read_bytes())['native_executed'])
                damaged = base / 'damaged.gpg'
                data = bytearray(cipher.read_bytes())
                data[len(data)//2] ^= 1
                damaged.write_bytes(data)
                with self.assertRaises(ValueError):
                    r.decrypt(damaged, response['sha256'], home, fingerprint, base / 'bad')
                self.assertFalse((base / 'bad').exists())
                with self.assertRaises(ValueError):
                    r.decrypt(damaged, r.digest(damaged), home, fingerprint, base / 'bad-auth')
                self.assertFalse((base / 'bad-auth').exists())
                with self.assertRaisesRegex(ValueError, 'expired'):
                    p.validate_pack(restored, request, 1000)
            finally:
                subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'gpg-agent'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
