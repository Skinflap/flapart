import unittest
from python_runtime_paths import relocated_lines

class Paths(unittest.TestCase):
    def test_relocates_and_deduplicates(self):
        self.assertEqual(relocated_lines('python313.zip\n.\n../lib/site-packages\nC:/SDK/lib/site-packages\nimport site\n','C:/SDK'),['python313.zip','.','../lib/site-packages','import site'])
    def test_case_insensitive_sdk(self):
        self.assertEqual(relocated_lines('python313.zip\n.\nc:/sdk/lib/site-packages\n','C:/SDK')[-1],'../lib/site-packages')
    def test_reject_external(self):
        for line in ['C:/other/site-packages','../../outside','D:/SDK/lib','C:relative','import os','x\x00y']:
            with self.subTest(line=line),self.assertRaises(ValueError):
                relocated_lines('python313.zip\n.\n'+line,'C:/SDK')
    def test_missing_stdlib(self):
        with self.assertRaises(ValueError):relocated_lines('.\n','C:/SDK')

if __name__=='__main__':unittest.main()
