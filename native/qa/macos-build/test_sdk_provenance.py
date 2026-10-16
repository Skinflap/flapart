import json
from pathlib import Path
import tempfile
import unittest
from sdk_provenance import validate, digest


class Provenance(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.maintained = self.root / 'maintained'
        self.baseline = self.maintained / 'sdk'; self.baseline.mkdir(parents=True)
        for name, data in [('network', 'old maintained network'), ('crypto', 'maintained TLS')]:
            (self.baseline / name).write_text(data)
        self.tls = self.root / 'tls.json'
        self.tls.write_text(json.dumps({'promoted': True, 'sdk': str(self.baseline),
            'copied': [{'path': n, 'sha256': digest(self.baseline / n)} for n in ('network', 'crypto')]}))
        self.sdk = self.root / 'build/sdk'; self.sdk.mkdir(parents=True)
        (self.sdk / 'network').write_text('new rebuilt network')
        (self.sdk / 'crypto').write_bytes((self.baseline / 'crypto').read_bytes())
        evidence = self.sdk.parent / 'evidence'; evidence.mkdir()
        (evidence / 'result.json').write_text(json.dumps({'compiled': True, 'universal_assembled': True, 'baseline_sdk': str(self.baseline)}))
        row = {'kind': 'native', 'sha256': digest(self.sdk / 'network'), 'mode': (self.sdk / 'network').stat().st_mode & 0o777}
        (evidence / 'assembly.json').write_text(json.dumps({'assembled': True, 'conflicts': [], 'outputs': {'network': row}}))
        self.qt = self.root / 'qt.json'
        self.qt.write_text(json.dumps({'promoted': True, 'sdk': str(self.sdk), 'baseline_sdk': str(self.baseline),
            'build_receipt_sha256': digest(evidence / 'result.json'),
            'assembly_receipt_sha256': digest(evidence / 'assembly.json'),
            'copied': [{'path': 'network', **row}]}))

    def test_legacy_maintained_sdk(self):
        self.assertTrue(validate(self.baseline, self.maintained, self.tls)['validated'])

    def test_combined_receipts(self):
        result = validate(self.sdk, self.maintained, self.tls, self.qt)
        self.assertTrue(result['validated']); self.assertEqual(result['rebuilt_qt_entries'], 1)
        self.assertFalse(result['runtime_qualified'])

    def test_new_prefix_requires_receipt(self):
        with self.assertRaisesRegex(ValueError, 'requires its Qt'):
            validate(self.sdk, self.maintained, self.tls)

    def test_changed_new_qt_refused(self):
        (self.sdk / 'network').write_text('old network sneaked back')
        with self.assertRaisesRegex(ValueError, 'Qt component changed'):
            validate(self.sdk, self.maintained, self.tls, self.qt)

    def test_changed_final_tls_refused(self):
        (self.sdk / 'crypto').write_text('old crypto')
        with self.assertRaisesRegex(ValueError, 'Maintained component changed in final'):
            validate(self.sdk, self.maintained, self.tls, self.qt)

    def test_changed_original_tls_refused(self):
        (self.baseline / 'crypto').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Original maintained component changed'):
            validate(self.sdk, self.maintained, self.tls, self.qt)

    def test_incomplete_promotion_refused(self):
        data = json.loads(self.qt.read_text()); data['copied'] = []; self.qt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'exact assembled output'):
            validate(self.sdk, self.maintained, self.tls, self.qt)

    def test_changed_build_receipt_refused(self):
        (self.sdk.parent / 'evidence/result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'provenance changed'):
            validate(self.sdk, self.maintained, self.tls, self.qt)


if __name__ == '__main__':
    unittest.main()
