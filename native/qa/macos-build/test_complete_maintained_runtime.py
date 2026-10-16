# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('completion', Path(__file__).with_name('complete-maintained-runtime.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def macho(deps=(), rpaths=(), cpu=0x100000c):
    commands = []
    for command, names, header in [(0xc, deps, 24), (0x8000001c, rpaths, 12)]:
        for name in names:
            data = name.encode() + b'\0'
            size = (header + len(data) + 7) // 8 * 8
            commands.append(struct.pack('<III', command, size, header) + bytes(header - 12) + data + bytes(size - header - len(data)))
    payload = b''.join(commands)
    return struct.pack('<8I', 0xfeedfacf, cpu, 0, 6, len(commands), len(payload), 0, 0) + payload

def universal(deps=(), rpaths=()):
    arm = macho(deps, rpaths)
    x86 = macho(deps, rpaths, 0x1000007)
    return (struct.pack('>II', 0xcafebabe, 2) + struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0)
            + struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(x86), 0) + arm + x86)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'Space in name.app'
        self.root.mkdir()
        self.sdk = self.base / 'sdk'
        self.sdk.mkdir()
        self.ssl = self.put(self.root / m.FRAMEWORK / 'libssl.3.dylib', universal())
        self.crypto = self.put(self.root / m.FRAMEWORK / 'libcrypto.3.dylib', universal())
    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path
    def test_normalization_uses_real_fat_parser_and_safe_arguments(self):
        path = self.put(self.root / 'Contents/MacOS/krita', universal([str(self.sdk / 'lib/libssl.3.dylib'), '/usr/lib/libSystem.B.dylib'], [str(self.sdk / 'lib')]))
        plan = m.relocation_plan(self.root, [self.sdk])
        row = next(row for row in plan if row['path'].endswith('/krita'))
        self.assertEqual(row['args'][:3], ['-change', str(self.sdk / 'lib/libssl.3.dylib'), '@loader_path/../Frameworks/libssl.3.dylib'])
        self.assertIn('-delete_rpath', row['args'])
        self.assertEqual(m.native(path)['architectures'], ['arm64', 'x86_64'])
    def test_unknown_absolute_rejected_even_with_matching_basename(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['/unapproved/libssl.3.dylib']))
        with self.assertRaisesRegex(ValueError, 'Unapproved absolute'): m.relocation_plan(self.root, [self.sdk])
    def test_escaping_loader_rejected(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['@loader_path/../../../../external.dylib']))
        with self.assertRaisesRegex(ValueError, 'escapes'): m.relocation_plan(self.root)
    def test_single_slice_rejected(self):
        self.put(self.root / 'Contents/MacOS/krita', macho())
        with self.assertRaisesRegex(ValueError, 'Non-universal'): m.relocation_plan(self.root)
    def test_ambiguous_rpath_rejected(self):
        self.put(self.root / 'Contents/PlugIns/libssl.3.dylib', universal())
        self.put(self.root / 'Contents/MacOS/krita', universal(['@rpath/libssl.3.dylib']))
        with self.assertRaisesRegex(ValueError, 'ambiguous'): m.relocation_plan(self.root)
    def test_old_ssl_rejected(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['@rpath/libssl.1.1.dylib']))
        with self.assertRaisesRegex(ValueError, 'Obsolete TLS'): m.relocation_plan(self.root)
    def test_symlink_escape_rejected(self):
        (self.root / 'outside').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'Escaping bundle'): m.relocation_plan(self.root)
    def test_missing_dependency_rejected(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['@rpath/missing.dylib']))
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'): m.relocation_plan(self.root)
    def fixture(self):
        self.put(self.sdk / 'lib/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python', universal())
        self.put(self.sdk / 'bin/openssl', universal(['@rpath/libcrypto.3.dylib']))
        self.put(self.sdk / 'lib/ossl-modules/legacy.dylib', universal(['@rpath/libcrypto.3.dylib']))
        for name in ('libssl.3.dylib', 'libcrypto.3.dylib'): self.put(self.sdk / 'lib' / name, universal())
        cert = self.put(self.sdk / 'ssl/cert.pem', b'-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n')
        custom = self.put(self.root / m.VERSION / 'lib/python3.13/sitecustomize.py', b'from __future__ import annotations\nORIGINAL_PRESERVED = True\n')
        lic = self.put(self.base / 'LICENSE', b'Fixture license only\n' * 20)
        return lic, hashlib.sha256(cert.read_bytes()).hexdigest(), custom
    def test_alias_import_resolves_to_canonical_native(self):
        real = self.put(self.root / m.FRAMEWORK / 'libz.1.3.2.dylib', universal())
        (real.parent / 'libz.1.dylib').symlink_to(real.name)
        self.put(self.root / 'Contents/MacOS/krita', universal(['@rpath/libz.1.dylib']))
        row = next(r for r in m.relocation_plan(self.root) if r['path'].endswith('/krita'))
        self.assertIn('@loader_path/../Frameworks/libz.1.3.2.dylib', row['args'])
    def test_system_traversal_rejected(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['/usr/lib/../../outside.dylib']))
        with self.assertRaisesRegex(ValueError, 'traversal'): m.relocation_plan(self.root)
    def test_nested_executable_uses_own_directory(self):
        folder = self.root / m.PYTHON.parent
        self.put(folder / 'nested.dylib', universal())
        data = bytearray(universal(['@executable_path/nested.dylib']))
        for offset in (48, 48 + len(macho(['@executable_path/nested.dylib']))):
            struct.pack_into('<I', data, offset + 12, 2)
        self.put(self.root / m.PYTHON, data)
        row = next(r for r in m.relocation_plan(self.root) if r['path'] == m.PYTHON.as_posix())
        self.assertEqual(row['args'], ['-change', '@executable_path/nested.dylib', '@loader_path/nested.dylib'])
    def test_bundle_provider_does_not_get_dylib_identity(self):
        data = bytearray(universal())
        for offset in (48, 48 + len(macho())): struct.pack_into('<I', data, offset + 12, 8)
        path = self.put(self.root / m.PROVIDERS / 'legacy.dylib', data)
        self.assertFalse(any(r['path'] == path.relative_to(self.root).as_posix() for r in m.relocation_plan(self.root)))
    def test_executable_context_ambiguity_rejected(self):
        self.put(self.root / 'Contents/MacOS/shared.dylib', universal())
        nested = self.root / m.PYTHON
        data = bytearray(universal())
        for offset in (48, 48 + len(macho())): struct.pack_into('<I', data, offset + 12, 2)
        self.put(nested, data)
        self.put(nested.parent / 'shared.dylib', universal())
        self.put(self.root / m.FRAMEWORK / 'consumer.dylib', universal(['@executable_path/shared.dylib']))
        with self.assertRaisesRegex(ValueError, 'ambiguous executable-relative'): m.relocation_plan(self.root)
    def test_known_builder_dll_removal_is_narrow_and_recorded(self):
        folder = self.root / m.VERSION / 'lib/python3.13/site-packages/pyqtbuild/bundle/dlls'
        path = self.put(folder / 'openssl-64/libssl-1_1-x64.dll', b'MZfixture')
        binding = self.put(folder.parent.parent.parent / 'PyQt5/QtCore.so', universal())
        removed = m.remove_known_build_dlls(self.root)
        self.assertEqual(removed[0]['sha256'], hashlib.sha256(b'MZfixture').hexdigest())
        self.assertFalse(path.exists())
        self.assertTrue(binding.exists())
    def test_unknown_builder_dll_refuses_all_deletion(self):
        folder = self.root / m.VERSION / 'lib/python3.13/site-packages/pyqtbuild/bundle/dlls'
        path = self.put(folder / 'openssl-64/libssl-1_1-x64.dll', b'MZfixture')
        self.put(folder / 'unexpected.dll', b'MZother')
        with self.assertRaisesRegex(ValueError, 'Unreviewed'): m.remove_known_build_dlls(self.root)
        self.assertTrue(path.exists())
    def test_dry_plan_preserves_original_bundle(self):
        lic, pin, custom = self.fixture()
        before = custom.read_bytes()
        result = m.complete(self.root, self.sdk, lic, lic, pin)
        self.assertFalse(result['runtime_completed'])
        self.assertFalse(result['native_validated'])
        self.assertEqual(custom.read_bytes(), before)
        self.assertFalse((self.root / m.PYTHON).exists())
        self.assertTrue(any(row['path'] == m.CLI.as_posix() for row in result['relocations']))
    def test_bad_pin_fails_before_mutation(self):
        lic, _, custom = self.fixture()
        before = custom.read_bytes()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): m.complete(self.root, self.sdk, lic, lic, '0' * 64)
        self.assertEqual(custom.read_bytes(), before)
    def test_bootstrap_defaults_and_preserved_site_source_under_isolation(self):
        lic, pin, custom = self.fixture()
        m.populate(self.root, self.sdk, lic, lic, pin)
        self.assertTrue((self.root / m.PYTHON).is_file())
        self.assertTrue(custom.with_name('_flapart_original_sitecustomize.py').read_text().startswith('from __future__'))
        # Executes packaged bootstrap under host -I; this tests bootstrap logic,
        # not macOS framework startup (which needs native qualification).
        code = 'import runpy,sys,os;sys.path.insert(0,sys.argv[1]);r=runpy.run_path(sys.argv[2]);assert os.environ["SSL_CERT_FILE"]==sys.argv[3];assert os.environ["OPENSSL_MODULES"]==sys.argv[4];assert r["_flapart_original_sitecustomize"].ORIGINAL_PRESERVED'
        env = {k:v for k,v in os.environ.items() if k not in ('SSL_CERT_FILE', 'OPENSSL_MODULES', 'OPENSSL_CONF')}
        subprocess.run([sys.executable, '-I', '-B', '-c', code, str(custom.parent), str(custom), str(self.root / m.CERT), str(self.root / m.PROVIDERS)], env=env, check=True)
    def test_native_tool_failure_preserves_collector_bundle(self):
        lic, pin, custom = self.fixture()
        before = custom.read_bytes()
        with mock.patch.object(m.platform, 'system', return_value='Darwin'), mock.patch.object(m.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'install_name_tool')):
            with self.assertRaises(subprocess.CalledProcessError):
                m.complete(self.root, self.sdk, lic, lic, pin, apply=True)
        self.assertEqual(custom.read_bytes(), before)
        self.assertFalse((self.root / m.PYTHON).exists())
        self.assertFalse(list(self.base.glob('.flapart-runtime-*')))
    def test_second_arch_bad_import_rejected(self):
        arm = macho()
        x86 = macho(['/unknown/bad.dylib'], cpu=0x1000007)
        fat = (struct.pack('>II', 0xcafebabe, 2) + struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0)
               + struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(x86), 0) + arm + x86)
        self.put(self.root / 'Contents/MacOS/krita', fat)
        with self.assertRaisesRegex(ValueError, 'Unapproved absolute'): m.relocation_plan(self.root)
    def test_relocated_verifier_rejects_pending_rpath(self):
        self.put(self.root / 'Contents/MacOS/krita', universal([], ['/outside']))
        with self.assertRaisesRegex(ValueError, 'Unfinished'): m.verify_relocated(self.root)
    def test_valid_loader_dependency_verified(self):
        self.put(self.root / 'Contents/MacOS/krita', universal(['@loader_path/../Frameworks/libssl.3.dylib']))
        m.verify_relocated(self.root)

if __name__ == '__main__': unittest.main()
