"""Exercise actual Mach-O/lipo assembly on disposable cross-compiled objects."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('merge', ROOT / 'merge-macos.py')
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class Assembly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.arm, self.intel = self.root / 'arm', self.root / 'intel'
        self.arm.mkdir(); self.intel.mkdir()
        self.lipo = shutil.which('llvm-lipo') or shutil.which('lipo')
        if not self.lipo or not shutil.which('clang'):
            self.skipTest('Actual clang and lipo required')
        source = self.root / 'sample.c'
        source.write_text('int flapart_test_symbol(void) { return 42; }\n')
        for cpu, directory in [('arm64', self.arm), ('x86_64', self.intel)]:
            subprocess.run(['clang', '-target', cpu + '-apple-macos11', '-c', str(source),
                            '-o', str(directory / 'sample.o')], check=True, capture_output=True)
            (directory / 'LICENSE').write_text('test fixture only\n')
            (directory / 'current').symlink_to('sample.o')

    def run_merge(self, review=None):
        return merge.merge(self.arm, self.intel, self.root / 'out', self.root / 'receipt.json', self.lipo, review)

    def refused(self):
        with self.assertRaises(ValueError):
            self.run_merge()
        self.assertFalse((self.root / 'out').exists())

    def test_actual_macho_slices_and_inputs(self):
        original = (merge.inventory(self.arm), merge.inventory(self.intel))
        receipt = self.run_merge()
        self.assertTrue(receipt['assembled'])
        self.assertFalse(receipt['runtime_qualified'])
        self.assertEqual(merge.archs(self.lipo, self.root / 'out/sample.o'), {'arm64', 'x86_64'})
        self.assertEqual(original, (merge.inventory(self.arm), merge.inventory(self.intel)))
        self.assertEqual((self.root / 'out/current').readlink(), Path('sample.o'))

    def test_missing_file_refused(self):
        (self.intel / 'LICENSE').unlink()
        self.refused()

    def test_wrong_cpu_refused(self):
        shutil.copy2(self.arm / 'sample.o', self.intel / 'sample.o')
        self.refused()

    def test_unreviewed_header_difference_refused(self):
        (self.arm / 'qconfig.h').write_text('arm\n')
        (self.intel / 'qconfig.h').write_text('intel\n')
        self.refused()
        self.assertTrue(json.loads((self.root / 'receipt.json').read_text())['conflicts'])

    def test_exact_reviewed_metadata_selection(self):
        for value, directory in [('arm', self.arm), ('intel', self.intel)]:
            (directory / 'qconfig.pri').write_text(value + '\n')
        review = self.root / 'review.json'
        review.write_text(json.dumps({'qconfig.pri': {
            'arm64_sha256': merge.sha(self.arm / 'qconfig.pri'),
            'x86_64_sha256': merge.sha(self.intel / 'qconfig.pri'),
            'select': 'arm64', 'reason': 'Fixture tests explicit source selection only'}}))
        self.run_merge(review)
        self.assertEqual((self.root / 'out/qconfig.pri').read_text(), 'arm\n')

    def test_escaping_link_refused(self):
        (self.arm / 'current').unlink()
        (self.arm / 'current').symlink_to('../sample.c')
        self.refused()

    def test_existing_output_preserved(self):
        (self.root / 'out').mkdir()
        sentinel = self.root / 'out/sentinel'
        sentinel.write_text('keep')
        with self.assertRaises(ValueError):
            self.run_merge()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_native_static_archives(self):
        ar = shutil.which('llvm-ar')
        if not ar:
            self.skipTest('llvm-ar required')
        for directory in (self.arm, self.intel):
            subprocess.run([ar, 'rcs', str(directory / 'sample.a'), str(directory / 'sample.o')], check=True)
        self.run_merge()
        self.assertEqual(merge.archs(self.lipo, self.root / 'out/sample.a'), {'arm64', 'x86_64'})


if __name__ == '__main__':
    unittest.main()
