"""SDK overlay tests with real, non-executable test Mach-O dylib fixtures."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('promotion', ROOT / 'promote-macos.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Promotion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(shutil.which(t) for t in ('clang', 'ld64.lld', 'llvm-lipo')):
            raise unittest.SkipTest('Native file construction tools unavailable')
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        source = cls.root / 'fixture.c'; source.write_text('int fixture(void) { return 1; }\n')
        names = ['libssl.3.dylib', 'libcrypto.3.dylib', 'libwebp.7.2.0.dylib',
                 'libwebpmux.3.1.2.dylib', 'libwebpdemux.2.0.17.dylib']
        for arch in ('arm64', 'x86_64'):
            d = cls.root / arch; d.mkdir()
            subprocess.run(['clang', '-target', arch + '-apple-macos11', '-c', str(source), '-o', str(d / 'fixture.o')], check=True, capture_output=True)
            base = ['ld64.lld', '-dylib', '-arch', arch, '-platform_version', 'macos', '11.0', '11.0', str(d / 'fixture.o')]
            for name in names:
                subprocess.run(base + ['-install_name', '@rpath/' + name, '-o', str(d / name)], check=True, capture_output=True)
            for kind, dependencies in [('network', names[:2]), ('webp', names[2:])]:
                subprocess.run(base + ['-install_name', '@rpath/' + kind,
                    *[item for dep in dependencies for item in ('-needed_library', str(d / dep))],
                    '-o', str(d / kind)], check=True, capture_output=True)
        for kind in ('network', 'webp'):
            subprocess.run(['llvm-lipo', '-create', str(cls.root / 'arm64' / kind),
                            str(cls.root / 'x86_64' / kind), '-output', str(cls.root / kind)], check=True)

    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.work = Path(self.t.name) / 'work'; self.work.mkdir()
        self.qt = self.work / 'qt-universal'; self.qt.mkdir()
        for suffix in ('', '_debug'):
            for name, fixture in [('lib/QtNetwork.framework/Versions/5/QtNetwork' + suffix, 'network'),
                                  ('plugins/imageformats/libqwebp' + suffix + '.dylib', 'webp')]:
                p = self.qt / name; p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.root / fixture, p)
        (self.qt / 'bin').mkdir(); shutil.copyfile(self.root / 'network', self.qt / 'bin/qmake')
        shutil.copytree(self.qt, self.work / 'sdk')
        (self.work / 'sdk/dependency.txt').write_text('preserve unrelated dependency')
        (self.work / 'evidence').mkdir()
        (self.work / 'evidence/result.json').write_text(json.dumps({'compiled': True, 'universal_assembled': True, 'baseline_sdk': str(self.work / 'original-sdk-fixture')}))
        self.freeze()

    def freeze(self):
        (self.work / 'evidence/assembly.json').write_text(json.dumps({'assembled': True, 'conflicts': [], 'outputs': m.assembly.inventory(self.qt)}))

    def test_preserved_baseline_and_dependencies(self):
        original = m.assembly.inventory(self.work / 'sdk')
        result = m.promote(self.work, self.work / 'promotion.json')
        self.assertTrue(result['promoted']); self.assertFalse(result['runtime_qualified'])
        self.assertEqual(m.assembly.inventory(self.work / 'sdk-before-qt'), original)
        self.assertEqual((self.work / 'sdk/dependency.txt').read_text(), 'preserve unrelated dependency')

    def test_changed_assembly_refused(self):
        (self.qt / 'bin/qmake').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Assembled Qt changed'):
            m.promote(self.work, self.work / 'promotion.json')
        self.assertFalse((self.work / 'sdk-before-qt').exists())

    def test_missing_framework_refused(self):
        (self.qt / 'lib/QtNetwork.framework/Versions/5/QtNetwork_debug').unlink(); self.freeze()
        with self.assertRaisesRegex(ValueError, 'framework replacement'):
            m.promote(self.work, self.work / 'promotion.json')

    def test_wrong_webp_imports_refused(self):
        shutil.copyfile(self.root / 'network', self.qt / 'plugins/imageformats/libqwebp.dylib'); self.freeze()
        with self.assertRaisesRegex(ValueError, 'Maintained dependencies missing'):
            m.promote(self.work, self.work / 'promotion.json')

    def test_prior_backup_refused(self):
        (self.work / 'sdk-before-qt').mkdir()
        with self.assertRaisesRegex(ValueError, 'fresh promotion'):
            m.promote(self.work, self.work / 'promotion.json')


if __name__ == '__main__':
    unittest.main()
