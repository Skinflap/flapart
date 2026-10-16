import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collections import namedtuple

spec = importlib.util.spec_from_file_location('admission', Path(__file__).with_name('admission.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
Disk = namedtuple('Disk', 'total used free')


class Admission(unittest.TestCase):
    def test_duplicate_bytes_count_logically_but_unique_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a').write_bytes(b'same')
            (root / 'b').write_bytes(b'same')
            with patch.object(m.shutil, 'disk_usage', return_value=Disk(10**12, 0, 10**12)):
                result = m.measure([root], root)
            self.assertEqual(result['input_files'], 2)
            self.assertEqual(result['logical_bytes'], 8)
            self.assertEqual(result['unique_bytes'], 4)
            self.assertFalse(result['release_qualified'])
            self.assertTrue(result['final_preparer_validation_required'])

    def test_low_disk_fails_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / 'a'
            f.write_bytes(b'preserve')
            with patch.object(m.shutil, 'disk_usage', return_value=Disk(100, 99, 1)):
                result = m.measure([f], root)
            self.assertFalse(result['estimated_disk_fits'])
            self.assertEqual(f.read_bytes(), b'preserve')

    def test_symlink_and_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / 'a'
            f.write_bytes(b'a')
            with self.assertRaisesRegex(ValueError, 'Overlapping'):
                m.measure([root, f], root)
            (root / 'b').symlink_to(f)
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                m.measure([root], root)

    def test_v2_peak_tracks_unique_not_repeated_logical_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = b'x' * (1024 * 1024)
            for i in range(100):
                (root / str(i)).write_bytes(data)
            legacy = m.measure([root], root)
            compact = m.measure([root], root, transport_v2=True)
            self.assertEqual(compact['format'], 'private-retention-v2')
            self.assertEqual(compact['unique_bytes'], len(data))
            self.assertLess(compact['estimated_additional_peak_bytes'], legacy['estimated_additional_peak_bytes'])
            self.assertTrue(compact['unique_storage_with_generated_fits'])

    def test_missing_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Missing'):
                m.measure([Path(tmp) / 'missing'], tmp)


if __name__ == '__main__':
    unittest.main()
