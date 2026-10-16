#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('candidate_qualification', Path(__file__).with_name('qualify-candidate.py'))
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class QualificationSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'Flapart-Studio';self.candidate.mkdir()
        self.archive = self.root / 'candidate.zip';self.archive.write_bytes(b'pinned fixture')
        self.output = self.root / 'evidence'
        self.temporary = self.root / 'temporary';self.temporary.mkdir()
        self.binary = self.root / 'artifacts/Install Flapart.exe'

    def layout(self, **overrides):
        inputs = dict(candidate=self.candidate, archive=self.archive, output=self.output, temporary=self.temporary, installer_output=self.binary)
        inputs.update(overrides);m.check_layout(**inputs)

    def test_separate_fresh_layout(self):
        self.layout()

    def test_binary_outputs_cannot_enter_evidence(self):
        for change in ({'archive': self.output / 'candidate.zip'}, {'temporary': self.output / 'runtime'}, {'installer_output': self.output / 'installer.exe'}):
            with self.subTest(change=change):
                path = next(iter(change.values()));path.parent.mkdir(parents=True, exist_ok=True)
                if 'archive' in change:path.write_bytes(b'fixture')
                if 'temporary' in change:path.mkdir(exist_ok=True)
                with self.assertRaises(ValueError):self.layout(**change)
                # Existing output must not be the reason subsequent cases pass.
                import shutil
                shutil.rmtree(self.output)

    def test_runtime_and_output_cannot_overlap(self):
        with self.assertRaises(ValueError):self.layout(output=self.candidate / 'evidence')
        with self.assertRaises(ValueError):self.layout(installer_output=self.candidate / 'installer.exe')

    def test_durable_outputs_cannot_be_temporary_children(self):
        with self.assertRaises(ValueError):self.layout(output=self.temporary / 'evidence')
        with self.assertRaises(ValueError):self.layout(installer_output=self.temporary / 'installer.exe')

    def test_existing_output_is_never_reused(self):
        self.output.mkdir()
        with self.assertRaises(ValueError):self.layout()

    def test_changed_payload_fails_pin(self):
        pin = m.digest(self.archive);m.check_pin(self.archive, pin, 'Archive')
        self.archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):m.check_pin(self.archive, pin, 'Archive')

    def test_bad_pin_refused(self):
        for pin in (None, '', 'g' * 64, '0' * 63):
            with self.subTest(pin=pin), self.assertRaises(ValueError):m.check_pin(self.archive, pin, 'Archive')

    def test_probe_stage_makes_only_new_copy_writable(self):
        source = self.root / 'probe-source';(source / 'flapart_probe').mkdir(parents=True)
        for path in (source / 'flapart_probe.desktop', source / 'flapart_probe/__init__.py'):
            path.write_text('fixture');path.chmod(stat.S_IRUSR)
        target = self.root / 'probe-copy';m.stage_probe(source, target)
        self.assertFalse((source / 'flapart_probe.desktop').stat().st_mode & stat.S_IWUSR)
        self.assertTrue((target / 'flapart_probe.desktop').stat().st_mode & stat.S_IWUSR)
        self.assertEqual((source / 'flapart_probe/__init__.py').read_bytes(), (target / 'flapart_probe/__init__.py').read_bytes())
        with self.assertRaises(ValueError):m.stage_probe(source, target)

    def test_probe_links_refused(self):
        source = self.root / 'probe-source';(source / 'flapart_probe').mkdir(parents=True)
        (source / 'flapart_probe/__init__.py').write_text('fixture')
        (source / 'flapart_probe.desktop').symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, 'Linked'):m.stage_probe(source, self.root / 'probe-copy')

    def test_owned_image_cannot_escape_private_runtime(self):
        work = self.root / 'private';work.mkdir()
        self.assertTrue(m.owned_image(work / 'bin/krita.exe', work))
        self.assertFalse(m.owned_image(self.root / 'other/bin/krita.exe', work))
        (work / 'alias').symlink_to(self.root / 'other', target_is_directory=True)
        self.assertFalse(m.owned_image(work / 'alias/krita.exe', work))

    def profile_helpers(self):
        return m.load('test_profile_helpers', Path(__file__).resolve().parents[1] / 'portable/test-relocated.py')

    def test_profile_restores_on_stage_failure(self):
        path = self.root / 'flapartnativerc';path.write_bytes(b'original')
        with self.assertRaisesRegex(RuntimeError, 'stage failed'):
            with m.safe_profile([path], self.temporary, self.profile_helpers(), lambda: [], {}):
                path.write_bytes(b'qa');raise RuntimeError('stage failed')
        self.assertEqual(path.read_bytes(), b'original')
        self.assertFalse(list(self.temporary.iterdir()))

    def test_unconfirmed_child_exit_retains_original_backup(self):
        path = self.root / 'flapartnativerc';path.write_bytes(b'original');receipt = {}
        def uncertain():raise OSError('cannot verify exit')
        with self.assertRaisesRegex(RuntimeError, 'original profile retained'):
            with m.safe_profile([path], self.temporary, self.profile_helpers(), uncertain, receipt):path.write_bytes(b'qa')
        backup = Path(receipt['retained_profile_backups'][0])
        self.assertEqual((backup / path.name).read_bytes(), b'original')
        self.assertEqual(path.read_bytes(), b'qa')

    def test_late_child_cleanup_still_fails_gate(self):
        path = self.root / 'flapartnativerc';path.write_bytes(b'original');receipt = {}
        with self.assertRaisesRegex(ValueError, 'gate remains failed'):
            with m.safe_profile([path], self.temporary, self.profile_helpers(), lambda: [{'pid': 123}], receipt):path.write_bytes(b'qa')
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(receipt['profile_cleanup_stragglers'], [{'pid': 123}])

    def test_relocation_binding_requires_existing_native_outcomes(self):
        proof = dict(compiled_fork=True, relocated_package_test=True, original_krita_sentinels_preserved=True)
        app = dict(process_architecture='x86_64', hardware_architecture='x86_64', execution_mode='native')
        result = m.bind_relocation(proof, app, 'a' * 64)
        self.assertEqual(result['payload_sha256'], 'a' * 64)
        self.assertTrue(result['build_environment_absent'])
        for key in proof:
            with self.assertRaises(ValueError):m.bind_relocation({**proof, key: False}, app, 'a' * 64)
        with self.assertRaises(ValueError):m.bind_relocation(proof, {**app, 'error': 'failed'}, 'a' * 64)


if __name__ == '__main__':unittest.main()
