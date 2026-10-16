# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile

spec = importlib.util.spec_from_file_location('chain', Path(__file__).with_name('verify_chain.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r = m.recorder

def thin(cpu, value):
    return struct.pack('<8I', 0xfeedfacf, cpu, 0, 6, 1, 24, 0, 0) + struct.pack('<II', 0x1b, 24) + bytes([value]) * 16

def fat():
    arm, x86 = thin(0x100000c, 1), thin(0x1000007, 2)
    return struct.pack('>II', 0xcafebabe, 2) + struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0) + struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(x86), 0) + arm + x86

class ChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.package = self.base / 'runtime' / 'Flapart Studio.app'
        self.package.mkdir(parents=True)
        self.binary = self.package / 'Contents/MacOS/krita'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(fat()); self.binary.chmod(0o755)
        (self.binary.parent / 'alias').symlink_to('krita')
        (self.package / 'notice.txt').write_text('Fixture only, not a real application')
        self.root = self.base / 'evidence'; self.root.mkdir()
        stages = []
        for name in m.STAGES:
            helper = self.base / (name + '.py')
            suffix = b'' if name == 'verify' else name.encode()
            helper.write_text('from pathlib import Path\nimport sys\np=Path(sys.argv[1]);p.write_bytes(p.read_bytes()+' + repr(suffix) + ')\nprint(' + repr(name) + ')\n')
            evidence = self.root / name
            result = r.record_stage(name, [sys.executable, str(helper), str(self.binary)], self.base, {'package': self.package}, evidence, helpers=[helper], retain_native_bytes=True)
            self.assertTrue(result['passed'])
            stages.append({'stage': name, 'receipt': self.ref(evidence / 'receipt.json')})
        self.archive = self.root / 'candidate.zip'
        self.inventory = self.root / 'inventory.json'
        self.make_archive()
        self.manifest = {'schema': 1, 'platform': 'macos-universal2', 'tree': 'package', 'archive_prefix': self.package.name,
            'stages': stages, 'archive': self.ref(self.archive), 'inventory': self.ref(self.inventory), 'tool_artifacts': []}
    def ref(self, path):
        return {'path': path.relative_to(self.root).as_posix(), 'sha256': m.sha(path)}
    def make_archive(self):
        rows = []
        with zipfile.ZipFile(self.archive, 'w') as z:
            for p in sorted(self.package.rglob('*')):
                if not p.is_file(): continue
                name = p.relative_to(self.package.parent).as_posix()
                if p.is_symlink():
                    target = p.readlink().as_posix()
                    info = zipfile.ZipInfo(name); info.create_system = 3; info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(info, target.encode()); rows.append({'path': name, 'symlink': target})
                else:
                    z.write(p, name); rows.append({'path': name, 'sha256': m.sha(p), 'bytes': p.stat().st_size})
        self.inventory.write_text(json.dumps({'platform': 'macos-universal2', 'files': rows}))
    def alter_receipt(self, stage, mutate):
        path = self.root / stage / 'receipt.json'; data = json.loads(path.read_text()); mutate(data); path.write_text(json.dumps(data))
        next(row for row in self.manifest['stages'] if row['stage'] == stage)['receipt'] = self.ref(path)
    def test_actual_mutation_chain_and_zip(self):
        result = m.verify(self.manifest, self.root)
        self.assertTrue(result['chain_verified'])
        self.assertFalse(result['source_closure_complete']); self.assertFalse(result['release_qualified'])
        self.assertEqual(result['native_files'], 1)
        self.assertTrue(result['recorded_only_tool_hashes'])
        self.assertEqual(result['independently_retained_tool_hashes'], [])
    def test_pe32_collector_asset_must_be_removed_before_final_archive(self):
        data = bytearray(512); data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 128)
        data[128:132] = b'PE\0\0'; struct.pack_into('<HH', data, 132, 0x14c, 0)
        struct.pack_into('<H', data, 148, 224); struct.pack_into('<H', data, 152, 0x10b)
        for remove in (False, True):
            self.binary.write_bytes(fat())
            dll = self.package / 'builder-only.dll'; dll.write_bytes(data)
            for name in m.STAGES:
                helper = self.base / (name + '-pe32.py')
                source = 'from pathlib import Path\nimport sys\np=Path(sys.argv[1])\n'
                if name == 'completion' and remove:
                    source += '(p.parent.parent.parent/"builder-only.dll").unlink()\n'
                helper.write_text(source)
                evidence = self.root / (name + '-pe32-' + str(remove))
                result = r.record_stage(name, [sys.executable, str(helper), str(self.binary)], self.base, {'package': self.package}, evidence, helpers=[helper], retain_native_bytes=True)
                self.assertTrue(result['passed'])
                next(row for row in self.manifest['stages'] if row['stage'] == name)['receipt'] = self.ref(evidence / 'receipt.json')
            self.make_archive(); self.manifest.update(archive=self.ref(self.archive), inventory=self.ref(self.inventory))
            if remove:
                self.assertTrue(m.verify(self.manifest, self.root)['chain_verified'])
            else:
                with self.assertRaisesRegex(ValueError, 'Final Mac native format'): m.verify(self.manifest, self.root)
    def test_original_runner_tool_paths_not_needed(self):
        for name in m.STAGES:
            (self.base / (name + '.py')).unlink()
        self.assertTrue(m.verify(self.manifest, self.root)['chain_verified'])
    def test_missing_or_reordered_stages_refused(self):
        for stages in [self.manifest['stages'][:-1], list(reversed(self.manifest['stages']))]:
            variant = dict(self.manifest, stages=stages)
            with self.assertRaisesRegex(ValueError, 'required stages'): m.verify(variant, self.root)
    def test_failed_or_incomplete_stage_refused(self):
        self.alter_receipt('completion', lambda d: d.update(passed=False))
        with self.assertRaisesRegex(ValueError, 'Failed/incomplete'): m.verify(self.manifest, self.root)
    def test_altered_log_refused(self):
        (self.root / 'collector/stdout.log').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'Altered evidence'): m.verify(self.manifest, self.root)
    def test_altered_before_snapshot_refused(self):
        (self.root / 'completion/before.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Altered evidence'): m.verify(self.manifest, self.root)
    def test_altered_native_blob_refused(self):
        blob = next((self.root / 'codesign/native-bytes').iterdir()); blob.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Altered evidence'): m.verify(self.manifest, self.root)
    def test_altered_tool_agreement_refused(self):
        self.alter_receipt('codesign', lambda d: d['tools'][0].update(sha256_after='0' * 64))
        with self.assertRaisesRegex(ValueError, 'Tool/helper changed'): m.verify(self.manifest, self.root)
    def test_altered_independently_retained_tool_refused(self):
        path = self.root / 'python-tool'; shutil.copyfile(sys.executable, path)
        self.manifest['tool_artifacts'] = [self.ref(path)]
        self.assertTrue(m.verify(self.manifest, self.root)['independently_retained_tool_hashes'])
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Altered evidence'): m.verify(self.manifest, self.root)
    def test_tree_label_and_unreviewed_mapping_refused(self):
        self.manifest['tree'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'tree label'): m.verify(self.manifest, self.root)
        self.manifest['tree'] = 'package'; self.manifest['stages'][1]['prefix'] = 'other'
        with self.assertRaisesRegex(ValueError, 'path mapping'): m.verify(self.manifest, self.root)
    def test_changed_native_archive_even_with_new_inventory_refused(self):
        self.binary.write_bytes(self.binary.read_bytes() + b'after-sign-tamper'); self.make_archive()
        self.manifest.update(archive=self.ref(self.archive), inventory=self.ref(self.inventory))
        with self.assertRaisesRegex(ValueError, 'differ from signed output'): m.verify(self.manifest, self.root)
    def test_duplicate_zip_refused(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.archive, 'a') as z: z.writestr(self.package.name + '/notice.txt', b'duplicate')
        self.manifest['archive'] = self.ref(self.archive)
        with self.assertRaisesRegex(ValueError, 'Duplicate/colliding'): m.verify(self.manifest, self.root)
    def test_unsafe_zip_path_refused(self):
        with zipfile.ZipFile(self.archive, 'a') as z: z.writestr('../escape', b'x')
        self.manifest['archive'] = self.ref(self.archive)
        with self.assertRaisesRegex(ValueError, 'Unsafe/outside'): m.verify(self.manifest, self.root)
    def test_escaping_symlink_zip_refused(self):
        alias = self.binary.parent / 'alias'; alias.unlink(); alias.symlink_to('../../../../outside')
        # Construct explicitly: package.rglob's is_file skips this broken link.
        rows = json.loads(self.inventory.read_text())
        for row in rows['files']:
            if row['path'].endswith('/alias'): row['symlink'] = '../../../../outside'
        rebuilt = self.root / 'rewritten.zip'
        with zipfile.ZipFile(self.archive) as old, zipfile.ZipFile(rebuilt, 'w') as new:
            for info in old.infolist():
                new.writestr(info, b'../../../../outside' if info.filename.endswith('/alias') else old.read(info))
        rebuilt.replace(self.archive); self.inventory.write_text(json.dumps(rows))
        self.manifest.update(archive=self.ref(self.archive), inventory=self.ref(self.inventory))
        with self.assertRaisesRegex(ValueError, 'Escaping archive'): m.verify(self.manifest, self.root)
    def test_file_directory_conflict_refused(self):
        name = self.package.name + '/notice.txt/child'
        with zipfile.ZipFile(self.archive, 'a') as z: z.writestr(name, b'x')
        data = json.loads(self.inventory.read_text()); data['files'].append({'path': name, 'bytes': 1, 'sha256': hashlib.sha256(b'x').hexdigest()})
        self.inventory.write_text(json.dumps(data)); self.manifest.update(archive=self.ref(self.archive), inventory=self.ref(self.inventory))
        with self.assertRaisesRegex(ValueError, 'descends through'): m.verify(self.manifest, self.root)
    def test_symlink_archive_change_refused(self):
        alias = self.binary.parent / 'alias'; alias.unlink(); alias.symlink_to('../MacOS/krita'); self.make_archive()
        self.manifest.update(archive=self.ref(self.archive), inventory=self.ref(self.inventory))
        with self.assertRaisesRegex(ValueError, 'aliases differ'): m.verify(self.manifest, self.root)
    def test_changed_archive_pin_refused(self):
        self.archive.write_bytes(self.archive.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'Altered evidence'): m.verify(self.manifest, self.root)
    def test_stage_link_catches_actual_unrecorded_mutation(self):
        # Re-run the final two stages over different bytes: individually valid
        # receipts cannot connect to the earlier completion output.
        self.binary.write_bytes(self.binary.read_bytes() + b'unrecorded')
        for name in ('codesign', 'verify'):
            helper = self.base / (name + '.py'); evidence = self.root / (name + '-alternate')
            r.record_stage(name, [sys.executable, str(helper), str(self.binary)], self.base, {'package': self.package}, evidence, helpers=[helper], retain_native_bytes=True)
            next(row for row in self.manifest['stages'] if row['stage'] == name)['receipt'] = self.ref(evidence / 'receipt.json')
        with self.assertRaisesRegex(ValueError, 'Broken adjacent'): m.verify(self.manifest, self.root)

if __name__ == '__main__': unittest.main()
