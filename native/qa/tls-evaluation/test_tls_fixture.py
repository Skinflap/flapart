import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tls_fixture import command, CONFIG

class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.openssl = shutil.which('openssl')
        self.assertIsNotNone(self.openssl)

    def test_real_certificate_generation_with_missing_host_configuration(self):
        missing = str(self.root / 'missing-host.cnf')
        with patch.dict(os.environ, {'OPENSSL_CONF': missing}):
            raw = subprocess.run([self.openssl, 'req', '-new', '-subj', '/CN=fixture'],
                                 cwd=self.root, capture_output=True)
            self.assertNotEqual(raw.returncode, 0)
            command(self.openssl, self.root, 'req', '-x509', '-newkey', 'rsa:2048',
                    '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem', '-days', '2',
                    '-subj', '/CN=Flapart disposable QA CA', '-addext',
                    'basicConstraints=critical,CA:TRUE', '-addext',
                    'keyUsage=critical,keyCertSign,cRLSign')
            self.assertEqual(os.environ['OPENSSL_CONF'], missing)
        self.assertIn('BEGIN CERTIFICATE', (self.root / 'ca.pem').read_text())
        self.assertEqual((self.root / 'openssl-fixture.cnf').read_text(), CONFIG)

    def test_errors_retain_actual_cli_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, 'OpenSSL fixture invalid-flapart-command failed') as error:
            command(self.openssl, self.root, 'invalid-flapart-command')
        self.assertIn('Invalid command', str(error.exception))

    def test_unexpected_config_refused(self):
        (self.root / 'openssl-fixture.cnf').write_text('unexpected')
        with self.assertRaises(ValueError):
            command(self.openssl, self.root, 'version')

if __name__ == '__main__':
    unittest.main()
