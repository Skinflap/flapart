import struct
import unittest
from macho_format import is_macho

class MachOFormatTests(unittest.TestCase):
    def test_thin_without_uuid(self):
        # Valid 64-bit arm64 header with no load commands: no LC_UUID exists.
        header = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 6, 0, 0, 0, 0)
        self.assertTrue(is_macho(header))

    def test_fat_without_uuid(self):
        arm = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 6, 0, 0, 0, 0)
        intel = struct.pack('<IIIIIIII', 0xfeedfacf, 0x1000007, 3, 6, 0, 0, 0, 0)
        header = struct.pack('>II', 0xcafebabe, 2)
        header += struct.pack('>IIIII', 0x100000c, 0, 48, len(arm), 0)
        header += struct.pack('>IIIII', 0x1000007, 3, 80, len(intel), 0)
        self.assertTrue(is_macho(header + arm + intel))

    def test_java_shared_magic_and_nonbinary(self):
        self.assertFalse(is_macho(bytes.fromhex('cafebabe0000003400010000')))
        self.assertFalse(is_macho(b'plain text'))

    def test_fat_out_of_bounds(self):
        self.assertFalse(is_macho(struct.pack('>II', 0xcafebabe, 1) + struct.pack('>IIIII', 0x100000c, 0, 4096, 32, 0)))

if __name__ == '__main__': unittest.main()
