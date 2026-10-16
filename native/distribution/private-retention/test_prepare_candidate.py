# SPDX-License-Identifier: GPL-3.0-or-later
"""Real local record/copy/ZIP fixtures; never native release evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

p = load('prepare_private_test', HERE / 'prepare_candidate.py')
fixtures = load('chain_retention_fixtures', HERE.parent / 'provenance/test_verify_chain.py')

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ChainTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # macOS tempfile paths can use /var -> /private/var. Canonicalize
        # our test inputs; production helper deliberately rejects symlinks.
        for attr in ('base', 'root', 'archive', 'inventory', 'package', 'binary'):
            setattr(self.fixture, attr, getattr(self.fixture, attr).resolve())
        self.base = self.fixture.base
        self.stages = self.base / 'stage-input'
        self.stages.mkdir()
        for stage in p.chain.STAGES:
            shutil.copytree(self.fixture.root / stage, self.stages / stage)
        self.output = self.base / 'prepared-private'
        self.qualification = self.base / 'qualification.json'
        self.qualification.write_text('{"fixture": true, "release_qualified": false}')
    def prepare(self):
        return p.prepare(self.fixture.archive, self.fixture.inventory, self.stages,
                         {'runtime.json': self.qualification}, self.output)
    def test_actual_chain_verified_and_every_retained_file_inventoried(self):
        before = {file: p.chain.sha(file) for file in self.stages.rglob('*') if file.is_file()}
        result = self.prepare()
        self.assertTrue(result['prepared'])
        self.assertFalse(result['release_qualified']); self.assertFalse(result['source_closure_complete'])
        self.assertTrue(json.loads((self.output / 'chain-result.json').read_text())['chain_verified'])
        inventory = json.loads((self.output / 'inventory.json').read_text())
        rows = p.retention.validate_inventory(inventory)
        self.assertEqual({row['path'] for row in rows}, {file.relative_to(self.output).as_posix() for file in self.output.rglob('*') if file.is_file()} - {'inventory.json'})
        for row in rows:
            self.assertEqual(p.chain.sha(self.output / row['path']), row['sha256'])
        self.assertEqual(before, {file: p.chain.sha(file) for file in before})
        self.assertEqual((self.output / 'candidate.zip').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
    @unittest.skipUnless(shutil.which('gpg') and shutil.which('gpgconf'), 'GnuPG required for private envelope bridge')
    def test_prepare_encrypt_decrypt_reverify_actual_envelope(self):
        prepared = self.prepare()
        # A short canonical path also avoids macOS Unix-domain socket limits.
        with tempfile.TemporaryDirectory(prefix='fgpg-', dir=(Path('/tmp') if Path('/tmp').is_dir() else Path(tempfile.gettempdir())).resolve()) as temp:
            base = Path(temp).resolve()
            home = base / 'keys'; home.mkdir(mode=0o700)
            try:
                p.retention.gpg(home, '--pinentry-mode', 'loopback', '--passphrase', '',
                    '--quick-generate-key', 'Disposable preparation bridge fixture', 'rsa2048', 'encr', '1d')
                listing = p.retention.gpg(home, '--with-colons', '--list-keys').stdout.decode()
                fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
                public = base / 'public.asc'
                public.write_bytes(p.retention.gpg(home, '--armor', '--export', fingerprint).stdout)
                encrypted = base / 'candidate.gpg'
                encrypted_receipt = p.retention.encrypt(self.output, self.output / 'inventory.json', public, fingerprint, encrypted)
                recovered = base / 'recovered'
                decrypted_receipt = p.retention.decrypt(encrypted, encrypted_receipt['encrypted_sha256'], home, fingerprint, recovered)
                self.assertFalse(encrypted_receipt['release_qualified'])
                self.assertFalse(decrypted_receipt['release_qualified'])
                self.assertEqual(p.chain.sha(recovered / 'candidate.zip'), prepared['candidate_sha256'])
                manifest = json.loads((recovered / 'chain-manifest.json').read_text())
                verified = p.chain.verify(manifest, recovered)
                self.assertTrue(verified['chain_verified'])
                self.assertFalse(verified['source_closure_complete'])
                self.assertFalse(verified['release_qualified'])
                original = json.loads((self.output / 'inventory.json').read_text())
                for row in original['files']:
                    self.assertEqual(p.chain.sha(recovered / row['path']), row['sha256'])
            finally:
                subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'gpg-agent'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def test_missing_stage_refused_without_output(self):
        shutil.rmtree(self.stages / 'verify')
        with self.assertRaisesRegex(ValueError, 'four known'): self.prepare()
        self.assertFalse(self.output.exists())
    def test_unexpected_stage_or_nested_asset_refused(self):
        (self.stages / 'extra').mkdir()
        with self.assertRaisesRegex(ValueError, 'four known'): self.prepare()
        (self.stages / 'extra').rmdir()
        (self.stages / 'collector/undeclared.log').write_text('no')
        with self.assertRaisesRegex(ValueError, 'stage evidence entry'): self.prepare()
    def test_input_symlink_refused(self):
        self.qualification.unlink(); self.qualification.symlink_to(self.fixture.inventory)
        with self.assertRaisesRegex(ValueError, 'symlink'): self.prepare()
        self.assertFalse(self.output.exists())
    def test_output_overlap_refused(self):
        self.output = self.stages / 'output'
        with self.assertRaisesRegex(ValueError, 'overlaps'): self.prepare()
    def test_failed_chain_cannot_produce_private_success_root(self):
        path = self.stages / 'completion/receipt.json'
        value = json.loads(path.read_text()); value['passed'] = False; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Failed/incomplete'): self.prepare()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.base.glob('.prepare-candidate-*')))
    def test_limits_enforced_before_publishing(self):
        with mock.patch.object(p, 'MAX_FILES', 3):
            with self.assertRaisesRegex(ValueError, 'file-count'): self.prepare()
        with mock.patch.object(p, 'LIMIT', 1):
            with self.assertRaisesRegex(ValueError, 'logical-byte'): self.prepare()
        self.assertFalse(self.output.exists())
    def test_source_mutation_during_verify_refused(self):
        actual = p.chain.verify
        def mutate(manifest, root):
            result = actual(manifest, root)
            self.qualification.write_text('{"changed": true}')
            return result
        with mock.patch.object(p.chain, 'verify', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during preparation'): self.prepare()
        self.assertFalse(self.output.exists())
    def test_explicit_qualification_only(self):
        private = self.base / 'not-selected-secret.txt'; private.write_text('not included')
        self.prepare()
        self.assertFalse(any('not-selected' in file.name for file in self.output.rglob('*')))
        with self.assertRaisesRegex(ValueError, 'fresh'): self.prepare()
    def test_native_duplicate_copies_are_private_hardlinks(self):
        self.prepare()
        blobs = list(self.output.glob('stages/*/native-bytes/*'))
        hashes = {}
        for blob in blobs: hashes.setdefault(blob.name, []).append(blob)
        group = next(paths for paths in hashes.values() if len(paths) > 1)
        self.assertEqual(len({path.stat().st_ino for path in group}), 1)
        source = self.stages / group[0].relative_to(self.output / 'stages')
        self.assertNotEqual(group[0].stat().st_ino, source.stat().st_ino)

if __name__ == '__main__': unittest.main()
