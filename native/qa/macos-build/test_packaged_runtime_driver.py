"""Portable driver safety tests; not native execution evidence."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('driver', Path(__file__).with_name('test-packaged-runtime.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

class Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir()

    def prefix(self, name):
        path = self.root / name
        path.mkdir()
        (path / 'sentinel').write_text(name)
        return path

    def test_restore_on_probe_failure(self):
        paths = [self.prefix('sdk'), self.prefix('openssl')]
        with self.assertRaisesRegex(RuntimeError, 'probe failed'):
            with driver.hidden_prefixes(paths, self.runtime, self.evidence):
                self.assertTrue(all(not path.exists() for path in paths))
                raise RuntimeError('probe failed')
        for path in paths:
            self.assertEqual((path / 'sentinel').read_text(), path.name)

    def test_nested_prefix_refused_before_mutation(self):
        parent = self.prefix('sdk')
        child = parent / 'lib'
        child.mkdir()
        with self.assertRaises(AssertionError):
            with driver.hidden_prefixes([parent, child], self.runtime, self.evidence):
                self.fail('Unsafe prefix set accepted')
        self.assertTrue(child.exists())

    def test_runtime_prefix_refused(self):
        with self.assertRaises(AssertionError):
            with driver.hidden_prefixes([self.runtime], self.runtime, self.evidence):
                self.fail('Runtime hidden')
        self.assertTrue(self.runtime.exists())

    def test_recreated_prefix_preserves_original_and_restores_others(self):
        first, second = self.prefix('sdk'), self.prefix('ssl')
        with self.assertRaisesRegex(RuntimeError, 'Refusing to overwrite'):
            with driver.hidden_prefixes([first, second], self.runtime, self.evidence):
                second.mkdir()
                (second / 'new').write_text('unrelated new data')
        self.assertTrue((first / 'sentinel').exists())
        self.assertEqual((second / 'new').read_text(), 'unrelated new data')
        hidden = list(self.root.glob('ssl-hidden-*'))
        self.assertEqual(len(hidden), 1)
        self.assertEqual((hidden[0] / 'sentinel').read_text(), 'ssl')

    def test_dangling_conflict_restores_other_original(self):
        first, second = self.prefix('sdk'), self.prefix('ssl')
        original = driver.identities([first, second])
        with self.assertRaisesRegex(RuntimeError, 'Refusing to overwrite'):
            with driver.hidden_prefixes([first, second], self.runtime, self.evidence):
                second.symlink_to('missing-target')
        self.assertEqual((first / 'sentinel').read_text(), 'sdk')
        self.assertTrue(second.is_symlink())
        self.assertFalse(second.exists())
        self.assertFalse(driver.restored([first, second], original))
        hidden = list(self.root.glob('ssl-hidden-*'))
        self.assertEqual(len(hidden), 1)
        self.assertEqual((hidden[0] / 'sentinel').read_text(), 'ssl')

    def test_recreated_same_path_is_not_original_identity(self):
        prefix = self.prefix('sdk')
        original = driver.identities([prefix])
        self.assertTrue(driver.restored([prefix], original))
        prefix.rename(self.root / 'retained-original')
        prefix.mkdir()
        self.assertFalse(driver.restored([prefix], original))

    def test_symlink_to_original_does_not_count_as_restored(self):
        prefix = self.prefix('sdk')
        original = driver.identities([prefix])
        retained = self.root / 'retained-original'
        prefix.rename(retained)
        prefix.symlink_to(retained, target_is_directory=True)
        self.assertFalse(driver.restored([prefix], original))

    def test_restore_oserror_does_not_skip_other_prefixes(self):
        first, second = self.prefix('sdk'), self.prefix('ssl')
        rename = Path.rename
        def failing_restore(path, destination):
            if path.name.startswith('ssl-hidden-') and destination == second:
                raise OSError('synthetic restoration I/O failure')
            return rename(path, destination)
        with patch.object(Path, 'rename', failing_restore):
            with self.assertRaisesRegex(RuntimeError, 'synthetic restoration I/O failure'):
                with driver.hidden_prefixes([first, second], self.runtime, self.evidence):
                    pass
        self.assertEqual((first / 'sentinel').read_text(), 'sdk')
        self.assertFalse(second.exists())
        self.assertEqual(len(list(self.root.glob('ssl-hidden-*'))), 1)

    def run_preflight(self, candidate, prefix, output, archive, baseline, helper_file=None):
        argv = ['driver', '--candidate', str(candidate), '--baseline', str(baseline),
                '--output', str(output), '--archive-output', str(archive),
                '--hide-build-prefix', str(prefix)]
        # Only platform/CI gating is simulated. Real paths and all confinement
        # validation run unchanged; an attempted native probe fails this test.
        with patch.object(driver.platform, 'system', return_value='Darwin'), patch.dict(
                os.environ, {'CI': 'true', 'RUNNER_TEMP': str(self.root)}), patch.object(
                driver.sys, 'argv', argv), patch.object(driver.subprocess, 'run') as run:
            if helper_file:
                with patch.object(driver, '__file__', str(helper_file)):
                    with self.assertRaisesRegex(AssertionError, 'Probe inputs must remain available'):
                        driver.main()
            else:
                with self.assertRaises(AssertionError):
                    driver.main()
            run.assert_not_called()
        self.assertEqual((prefix / 'sentinel').read_text(), prefix.name)
        self.assertFalse(archive.exists())
        self.assertEqual(list(self.root.glob('*-hidden-*')), [])

    def test_output_inside_candidate_refused_before_creation(self):
        candidate = self.root / 'Flapart Studio.app'
        candidate.mkdir()
        output = candidate / 'evidence'
        prefix = self.prefix('sdk')
        self.run_preflight(candidate, prefix, output, self.root / 'archive.zip', self.root / 'baseline.json')
        self.assertFalse(output.exists())

    def test_hidden_inputs_refused_before_prefix_rename(self):
        for kind in ('archive', 'baseline', 'helper'):
            with self.subTest(input=kind), tempfile.TemporaryDirectory(dir=self.root) as temp:
                root = Path(temp)
                candidate = root / 'Flapart Studio.app'
                candidate.mkdir()
                prefix = root / 'sdk'
                prefix.mkdir()
                (prefix / 'sentinel').write_text('sdk')
                archive = prefix / 'archive.zip' if kind == 'archive' else root / 'archive.zip'
                baseline = prefix / 'baseline.json' if kind == 'baseline' else root / 'baseline.json'
                baseline.write_text('{}')
                helper = prefix / 'macos-build/test-packaged-runtime.py' if kind == 'helper' else None
                self.run_preflight(candidate, prefix, root / 'evidence', archive, baseline, helper)

    def test_archive_links_and_modes(self):
        bundle = self.root / 'Flapart Studio.app'
        bundle.mkdir()
        executable = bundle / 'Python'
        executable.write_bytes(b'synthetic executable')
        executable.chmod(0o755)
        (bundle / 'python3').symlink_to('Python')
        archive = self.root / 'candidate.zip'
        driver.archive_bundle(bundle, archive)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.read('Flapart Studio.app/python3'), b'Python')
            self.assertEqual(stat.S_IFMT(z.getinfo('Flapart Studio.app/python3').external_attr >> 16), stat.S_IFLNK)
            self.assertTrue(z.getinfo('Flapart Studio.app/Python').external_attr >> 16 & 0o111)

    def test_archive_escape_refused(self):
        bundle = self.root / 'Flapart Studio.app'
        bundle.mkdir()
        (self.root / 'outside').write_bytes(b'private')
        (bundle / 'escape').symlink_to('../outside')
        with self.assertRaises(AssertionError):
            driver.archive_bundle(bundle, self.root / 'candidate.zip')

    def test_build_environment_removed(self):
        with patch.dict(os.environ, {'PYTHONPATH': '/build/python', 'DYLD_LIBRARY_PATH': '/build/lib', 'SSL_CERT_FILE': '/test/ca', 'OPENSSL_MODULES': '/build/providers', 'CMAKE_PREFIX_PATH': '/sdk', 'PATH': '/build/bin'}, clear=True):
            env = driver.clean_environment()
        for key in ('PYTHONPATH', 'DYLD_LIBRARY_PATH', 'SSL_CERT_FILE', 'OPENSSL_MODULES', 'CMAKE_PREFIX_PATH'):
            self.assertNotIn(key, env)
        self.assertEqual(env['PATH'], '/usr/bin:/bin:/usr/sbin:/sbin')

if __name__ == '__main__':
    unittest.main()
