# SPDX-License-Identifier: GPL-3.0-or-later
"""Read stable Mach-O UUIDs without executing a binary or depending on host tools."""
import struct,uuid

def macho_uuids(data):
    if len(data)<8:return []
    magic=data[:4]
    if magic in (b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf'):
        count=struct.unpack_from('>I',data,4)[0];wide=magic==b'\xca\xfe\xba\xbf';stride=32 if wide else 20
        if count>64 or 8+count*stride>len(data):return []
        result=[]
        for i in range(count):
            pos=8+i*stride
            offset,size=struct.unpack_from('>QQ' if wide else '>II',data,pos+8)
            if offset+size>len(data):return []
            result.extend(macho_uuids(data[offset:offset+size]))
        return sorted(set(result))
    formats={b'\xcf\xfa\xed\xfe':('<',32),b'\xce\xfa\xed\xfe':('<',28),b'\xfe\xed\xfa\xcf':('>',32),b'\xfe\xed\xfa\xce':('>',28)}
    if magic not in formats:return []
    endian,offset=formats[magic]
    if len(data)<offset:return []
    count=struct.unpack_from(endian+'I',data,16)[0]
    if count>65536:return []
    result=[]
    for _ in range(count):
        if offset+8>len(data):return []
        command,size=struct.unpack_from(endian+'II',data,offset)
        if size<8 or offset+size>len(data):return []
        if command==0x1b and size>=24:result.append(str(uuid.UUID(bytes=data[offset+8:offset+24])))
        offset+=size
    return sorted(set(result))
