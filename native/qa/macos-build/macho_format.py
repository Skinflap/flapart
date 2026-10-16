"""Detect Mach-O independently of optional UUID load commands."""
import struct
THIN_MAGICS = {b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf'}
FAT_MAGICS = {b'\xca\xfe\xba\xbe': ('>', False), b'\xbe\xba\xfe\xca': ('<', False), b'\xca\xfe\xba\xbf': ('>', True), b'\xbf\xba\xfe\xca': ('<', True)}

def is_macho(data):
    if data[:4] in THIN_MAGICS:
        return True  # Let native lipo reject malformed thin files.
    layout = FAT_MAGICS.get(data[:4])
    if layout is None or len(data) < 8:
        return False
    endian, wide = layout
    count = struct.unpack_from(endian + 'I', data, 4)[0]
    entry_size = 32 if wide else 20
    header_size = 8 + count * entry_size
    if not count or header_size > len(data):
        return False
    # Java classes share CAFEBABE. A fat Mach-O must describe in-bounds native
    # slices, not merely start with that magic. UUIDs are deliberately irrelevant.
    for index in range(count):
        offset, size = struct.unpack_from(endian + ('QQ' if wide else 'II'), data, 8 + index * entry_size + 8)
        if offset < header_size or size < 4 or offset + size > len(data):
            return False
        if data[offset:offset + 4] not in THIN_MAGICS:
            return False
    return True
