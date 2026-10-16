# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('recorder', Path(__file__).with_name('stage_recorder.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def macho(cpu, identity):
    command = struct.pack('<II', 0x1b, 24) + bytes([identity]) * 16
    return struct.pack('<8I', 0xfeedfacf, cpu, 0, 6, 1, len(command), 0, 0) + command

def fat(identity=1):
    arm, x86 = macho(0x100000c, identity), macho(0x1000007, identity + 1)
    return struct.pack('>II', 0xcafebabe, 2) + struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0) + struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(x86), 0) + arm + x86

class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.tree = self.base / 'tree with space'
        self.tree.mkdir()
        self.binary = self.tree / 'library.dylib'
        self.binary.write_bytes(fat())
        self.evidence = self.base / 'evidence'
    def run_stage(self, source, **kwargs):
        helper = self.base / 'actual_helper.py'
        helper.write_text(source)
        return m.record_stage('test-stage', [sys.executable, str(helper), str(self.binary)], self.base,
            {'package': self.tree}, self.evidence, helpers=[helper], **kwargs)
    def test_actual_command_change_and_all_slice_identity(self):
        result = self.run_stage('import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_bytes(p.read_bytes()+b"actual change"); print("stdout evidence"); print("stderr evidence",file=sys.stderr)')
        self.assertTrue(result['passed'])
        self.assertEqual(result['returncode'], 0)
        self.assertTrue(result['comparison_complete'])
        change = result['changed_files'][0]
        self.assertEqual(change['change'], 'modified')
        self.assertEqual(len(change['after']['macho_uuids']), 2)
        self.assertEqual(change['after']['architectures'], ['arm64', 'x86_64'])
        self.assertEqual(change['after']['sha256'], hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertEqual(result['stdout']['sha256'], m.digest(self.evidence / 'stdout.log'))
        self.assertEqual(result['stderr']['sha256'], m.digest(self.evidence / 'stderr.log'))
        self.assertEqual(result['before_snapshot']['sha256'], m.digest(self.evidence / 'before.json'))
        self.assertEqual(len(result['helpers']), 3)
    def test_explicit_private_byte_retention_captures_real_inputs_outputs(self):
        initial = self.binary.read_bytes()
        result = self.run_stage('import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_bytes(p.read_bytes()+b"new")', retain_native_bytes=True)
        self.assertTrue(result['passed'])
        before = result['before']['package']['files'][0]
        after = result['after']['package']['files'][0]
        self.assertEqual((self.evidence / before['retained_bytes']).read_bytes(), initial)
        self.assertEqual((self.evidence / after['retained_bytes']).read_bytes(), self.binary.read_bytes())
        self.assertEqual((self.evidence / after['retained_bytes']).stat().st_mode & 0o777, 0o600)
    def test_universal_static_archive_preserves_members_without_fake_uuid(self):
        def ar(member):
            header = b'object.o/       ' + b'0           ' + b'0     ' + b'0     ' + b'100644  ' + str(len(member)).encode().ljust(10) + b'`\n'
            return b'!<arch>\n' + header + member + (b'\n' if len(member) % 2 else b'')
        arm, x86 = ar(macho(0x100000c, 1)), ar(macho(0x1000007, 2))
        data = struct.pack('>II', 0xcafebabe, 2) + struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0) + struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(x86), 0) + arm + x86
        info = m.captured_metadata(data)
        self.assertEqual(info['format'], 'static-archive')
        self.assertEqual(info['architectures'], ['arm64', 'x86_64'])
        self.assertEqual(info['macho_uuids'], [])
        self.assertEqual(len(info['slices'][0]['member_uuids']), 1)
        (self.tree / 'input.a').write_bytes(data)
        self.assertEqual(len(m.snapshot(self.tree)['files']), 2)
    def test_pe32_inputs_capture_cpu_imports_and_hash(self):
        data = bytearray(1024)
        data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 128)
        data[128:132] = b'PE\0\0'
        struct.pack_into('<HH', data, 132, 0x14c, 1)
        struct.pack_into('<H', data, 148, 224)
        opt = 152
        struct.pack_into('<H', data, opt, 0x10b)
        struct.pack_into('<I', data, opt + 28, 0x400000)
        struct.pack_into('<I', data, opt + 60, 512)
        struct.pack_into('<I', data, opt + 92, 16)
        struct.pack_into('<II', data, opt + 104, 0x1000, 40)
        struct.pack_into('<IIII', data, opt + 224 + 8, 512, 0x1000, 512, 512)
        struct.pack_into('<5I', data, 512, 0, 0, 0, 0x1040, 0)
        data[576:589] = b'KERNEL32.dll\0'
        path = self.tree / 'builder-only.dll'; path.write_bytes(data)
        row = next(row for row in m.snapshot(self.tree)['files'] if row['path'] == path.name)
        self.assertEqual(row['architectures'], ['x86'])
        self.assertEqual(row['slices'][0]['cpu'], 0x14c)
        self.assertEqual(row['native_dependencies'], ['KERNEL32.dll'])
        self.assertEqual(row['sha256'], hashlib.sha256(data).hexdigest())
        # Include an actual PE32 delay import using RVA addressing.
        struct.pack_into('<II', data, opt + 96 + 13 * 8, 0x1080, 64)
        struct.pack_into('<8I', data, 640, 1, 0x10c0, 0, 0, 0, 0, 0, 0)
        data[704:715] = b'USER32.dll\0'
        info = m.captured_metadata(data)
        self.assertEqual(info['native_dependencies'], ['KERNEL32.dll', 'USER32.dll'])
    def test_failed_command_retains_mutated_outputs_and_logs(self):
        result = self.run_stage('import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_bytes(p.read_bytes()+b"partial"); print("failed"); sys.exit(7)')
        self.assertFalse(result['passed'])
        self.assertEqual(result['returncode'], 7)
        self.assertEqual(len(result['changed_files']), 1)
        self.assertEqual(json.loads((self.evidence / 'receipt.json').read_text())['returncode'], 7)
    def test_environment_is_allowlisted_for_record_and_child(self):
        env = dict(os.environ, SOME_PRIVATE_CREDENTIAL='not-for-the-child', CFLAGS='-O2')
        result = self.run_stage('import os; assert "SOME_PRIVATE_CREDENTIAL" not in os.environ; assert os.environ["CFLAGS"]=="-O2"', source_env=env)
        self.assertTrue(result['passed'])
        self.assertNotIn('SOME_PRIVATE_CREDENTIAL', result['environment'])
        self.assertNotIn('not-for-the-child', (self.evidence / 'receipt.json').read_text())
    def test_explicit_no_bytecode_environment_prevents_child_cache(self):
        module = self.base / 'sdk_query_fixture.py'
        module.write_text('VALUE = 42\n')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = self.run_stage('import sys, sdk_query_fixture; assert sys.dont_write_bytecode; assert sdk_query_fixture.VALUE == 42', source_env=env)
        self.assertTrue(result['passed'])
        self.assertEqual(result['environment']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertFalse((self.base / '__pycache__').exists())
    def test_nested_evidence_refused_before_execution(self):
        self.evidence = self.tree / 'evidence'
        with self.assertRaisesRegex(ValueError, 'contain one another'): self.run_stage('raise RuntimeError("must not run")')
        self.assertFalse(self.evidence.exists())
    def test_capture_inside_evidence_refused(self):
        with self.assertRaisesRegex(ValueError, 'contain one another'):
            m.validate_layout({'tree': self.base / 'future/child'}, self.base / 'future')
    def test_escaping_symlink_retains_failure_receipt(self):
        (self.tree / 'outside').symlink_to(self.base)
        result = self.run_stage('raise RuntimeError("must not run")')
        self.assertFalse(result['passed'])
        self.assertIsNone(result['returncode'])
        self.assertFalse(result['comparison_complete'])
        self.assertTrue((self.evidence / 'receipt.json').is_file())
    def test_broken_alias_identifies_relative_path_without_running_command(self):
        (self.tree / 'missing alias').symlink_to('missing-target')
        result = self.run_stage('raise RuntimeError("must not run")')
        self.assertFalse(result['passed'])
        self.assertIsNone(result['returncode'])
        self.assertIn('Captured tree contains a broken symlink: "missing alias"', result['errors'])

    def test_confined_alias_and_directory_alias_retained(self):
        (self.tree / 'libalias.dylib').symlink_to('library.dylib')
        directory = self.tree / 'real'; directory.mkdir()
        (self.tree / 'alias-dir').symlink_to('real', target_is_directory=True)
        result = m.snapshot(self.tree)
        self.assertEqual({r['kind'] for r in result['files']}, {'native', 'file-alias', 'directory-alias'})
    def test_missing_output_tree_can_be_added_by_build(self):
        self.binary.unlink(); self.tree.rmdir()
        source = 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.parent.mkdir(); p.write_bytes(bytes.fromhex(' + repr(fat().hex()) + '))'
        result = self.run_stage(source)
        self.assertTrue(result['passed'])
        self.assertFalse(result['before']['package']['exists'])
        self.assertEqual(result['changed_files'][0]['change'], 'added')
    def test_malformed_native_failure_is_not_ignored(self):
        self.binary.write_bytes(b'\xcf\xfa\xed\xfeinvalid')
        result = self.run_stage('raise RuntimeError("must not run")')
        self.assertFalse(result['passed'])
        self.assertIsNone(result['returncode'])
    def test_after_escape_does_not_invent_removed_files(self):
        result = self.run_stage('import pathlib,sys; p=pathlib.Path(sys.argv[1]); (p.parent/"outside").symlink_to(p.parent.parent)')
        self.assertEqual(result['returncode'], 0)
        self.assertFalse(result['passed'])
        self.assertFalse(result['comparison_complete'])
        self.assertEqual(result['changed_files'], [])
    def test_secret_like_argv_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Credential-like'):
            m.record_stage('test', [sys.executable, '--token=do-not-record'], self.base, {'tree': self.tree}, self.evidence)
        self.assertFalse(self.evidence.exists())
    def test_timeout_retains_receipt(self):
        result = self.run_stage('import time; time.sleep(10)', timeout=0.05)
        self.assertFalse(result['passed'])
        self.assertTrue(result['timed_out'])
        self.assertIsNotNone(result['returncode'])
    def test_cannot_overwrite_evidence(self):
        self.evidence.mkdir()
        with self.assertRaisesRegex(ValueError, 'fresh'): self.run_stage('pass')
    def test_changed_helper_fails_stage(self):
        result = self.run_stage('import pathlib; pathlib.Path(__file__).write_text("changed")')
        self.assertEqual(result['returncode'], 0)
        self.assertFalse(result['passed'])
        self.assertIn('Recorded tool/helper changed during stage', result['errors'])

if __name__ == '__main__': unittest.main()
