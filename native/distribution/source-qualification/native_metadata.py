"""Read PE imports (including delay loads) and Mach-O slices without executing code."""
import struct,uuid

def check(ok,message):
 if not ok:raise ValueError(message)
def unpack(fmt,data,offset):
 check(offset>=0 and offset+struct.calcsize(fmt)<=len(data),'Truncated native metadata');return struct.unpack_from(fmt,data,offset)
def string(data,offset,end):
 check(0<=offset<end<=len(data),'Invalid native string offset');stop=data.find(b'\0',offset,end);check(stop>=0,'Unterminated native import');return data[offset:stop].decode('utf-8')

def parse(data):
 if data[:2]==b'MZ':return pe(data)
 formats={b'\xcf\xfa\xed\xfe':('<',32),b'\xce\xfa\xed\xfe':('<',28),b'\xfe\xed\xfa\xcf':('>',32),b'\xfe\xed\xfa\xce':('>',28)}
 if data[:4] in formats:return macho(data,*formats[data[:4]])
 fats={b'\xca\xfe\xba\xbe':('>',20),b'\xbe\xba\xfe\xca':('<',20),b'\xca\xfe\xba\xbf':('>',32),b'\xbf\xba\xfe\xca':('<',32)}
 if data[:4] in fats:
  endian,stride=fats[data[:4]];count=unpack(endian+'I',data,4)[0]
  if count>16:return None # Java CAFEBABE class version is not Mach-O.
  check(count>0 and 8+stride*count<=len(data),'Invalid universal Mach-O table');slices=[];ranges=[]
  for i in range(count):
   cpu=unpack(endian+'I',data,8+i*stride)[0];offset,size=unpack(endian+('II' if stride==20 else 'QQ'),data,16+i*stride)
   check(offset>=8+stride*count and size>=28 and offset+size<=len(data),'Invalid universal slice bounds')
   check(all(offset+size<=a or offset>=b for a,b in ranges),'Overlapping universal slices');ranges.append((offset,offset+size));part=parse(data[offset:offset+size]);check(part and part['format']=='macho' and len(part['slices'])==1,'Invalid universal native slice');row=part['slices'][0];check(row['cpu']==cpu,'Universal CPU mismatch');slices.append(row)
  check(len({s['architecture'] for s in slices})==len(slices),'Duplicate architecture slice');return combine('macho',slices)
 if data[:4]==b'\x7fELF':raise ValueError('Unexpected ELF in Windows/Mac package')
 return None

def combine(kind,slices):
 return {'format':kind,'architectures':sorted(s['architecture'] for s in slices),'macho_uuids':sorted(s['uuid'] for s in slices if s.get('uuid')),'native_dependencies':sorted({d for s in slices for d in s['dependencies']}),'slices':slices}
def macho(data,endian,header):
 cpu=unpack(endian+'I',data,4)[0];arches={0x1000007:'x86_64',0x100000c:'arm64'};check(cpu in arches,'Unsupported Mach-O CPU')
 count,size=unpack(endian+'II',data,16);check(count<=65536 and header+size<=len(data),'Invalid Mach-O commands');pos=header;deps=[];rpaths=[];identity=None
 for _ in range(count):
  command,length=unpack(endian+'II',data,pos);check(length>=8 and pos+length<=header+size,'Invalid Mach-O command bounds');kind=command&0x7fffffff
  if kind in (0xc,0x18,0x1f,0x20,0x23):
   check(length>=24,'Truncated dylib command');offset=unpack(endian+'I',data,pos+8)[0];check(offset>=24,'Invalid dylib name');deps.append(string(data,pos+offset,pos+length))
  elif kind==0x1c:
   offset=unpack(endian+'I',data,pos+8)[0];check(offset>=12,'Invalid RPATH');rpaths.append(string(data,pos+offset,pos+length))
  elif kind==0x1b:
   check(length==24 and identity is None,'Invalid/duplicate LC_UUID');identity=str(uuid.UUID(bytes=data[pos+8:pos+24]))
  pos+=length
 check(pos==header+size,'Mach-O command size mismatch')
 return combine('macho',[{'cpu':cpu,'architecture':arches[cpu],'uuid':identity,'dependencies':deps,'rpaths':rpaths}])
def pe(data):
 off=unpack('<I',data,60)[0];check(data[off:off+4]==b'PE\0\0','Invalid PE signature');cpu,sections=unpack('<HH',data,off+4);check(cpu in (0x8664,0xaa64),'Unsupported PE CPU');optlen=unpack('<H',data,off+20)[0];opt=off+24
 check(unpack('<H',data,opt)[0]==0x20b and optlen>=112 and opt+optlen+40*sections<=len(data),'Invalid PE32+ optional header')
 count=unpack('<I',data,opt+108)[0];check(count<=16 and 112+8*count<=optlen,'Invalid PE directory count');imagebase=unpack('<Q',data,opt+24)[0];headers=unpack('<I',data,opt+60)[0];table=[]
 for i in range(sections):
  pos=opt+optlen+40*i;vsize,rva,size,raw=unpack('<IIII',data,pos+8);check(raw+size<=len(data),'PE section outside file');table.append((rva,size,raw))
 def address(rva,length=1):
  if rva<headers:check(rva+length<=min(headers,len(data)),'Invalid PE header RVA');return rva
  for start,size,raw in table:
   if start<=rva and rva+length<=start+size:return raw+rva-start
  raise ValueError('PE import RVA outside file-backed sections')
 deps=[]
 for index,stride in ((1,20),(13,32)):
  if count<=index:continue
  rva,size=unpack('<II',data,opt+112+8*index)
  if not rva:check(size==0,'PE directory size without RVA');continue
  check(size>=stride and size<=1024*1024,'Invalid PE import directory');terminated=False
  for relative in range(0,size-stride+1,stride):
   pos=address(rva+relative,stride);values=unpack('<'+'I'*(stride//4),data,pos)
   if not any(values):terminated=True;break
   name=values[3] if index==1 else values[1]
   if index==13:
    check(values[0] in (0,1),'Unknown delayed-import attributes')
    if values[0]==0:name-=imagebase
   start=address(name);end=min(len(data),start+4096);deps.append(string(data,start,end))
  check(terminated,'Unterminated PE import descriptors')
 return combine('pe',[{'cpu':cpu,'architecture':{0x8664:'x86_64',0xaa64:'arm64'}[cpu],'dependencies':deps,'uuid':None}])
