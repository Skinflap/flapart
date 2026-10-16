"""Synthetic receipt-contract tests only; these do not qualify any native runtime."""
import copy,hashlib,importlib.util,json,struct,tempfile,unittest,zipfile,stat
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def sha(data):return hashlib.sha256(data).hexdigest()
def native(arches,windows):
 if windows:
  data=bytearray(128);data[:2]=b'MZ';struct.pack_into('<I',data,60,64);data[64:68]=b'PE\0\0';struct.pack_into('<H',data,68,0x8664);return bytes(data)
 def thin(arch):return b'\xcf\xfa\xed\xfe'+struct.pack('<I',{'arm64':0x100000c,'x86_64':0x1000007}[arch])+b'\0'*24
 if len(arches)==1:return thin(arches[0])
 head=b'\xca\xfe\xba\xbe'+struct.pack('>I',len(arches));offset=8+20*len(arches);body=b''
 for arch in arches:
  part=thin(arch);head+=struct.pack('>IIIII',{'arm64':0x100000c,'x86_64':0x1000007}[arch],0,offset,len(part),0);body+=part;offset+=len(part)
 return head+body

class Fixture:
 def __init__(self,module,root,platform='windows-x86_64'):
  self.m=module;self.root=root;self.platform=platform;self.target,archset=module.PLATFORMS[platform];arches=sorted(archset);win=platform.startswith('windows');prefix='Flapart-Studio' if win else 'Flapart Studio.app/Contents'
  self.exe=prefix+('/bin/krita.exe' if win else '/MacOS/krita');files={self.exe:native(arches,win)}
  self.libs={}
  for role in ('ssl','crypto','python_ssl','qt_network','python'):
   path=prefix+'/lib/'+role+'.bin';files[path]=native(arches,win)+role.encode();self.libs[role]={'archive_path':path,'sha256':sha(files[path])}
  # Self-contained source-mirror test: synthetic plugin bytes, never released pins.
  plugin_path=root/'studio-plugin.zip'
  with zipfile.ZipFile(plugin_path,'w') as z:
   z.writestr('flapart.action','synthetic action');z.writestr('flapart/__init__.py','# synthetic fixture')
  module.__file__=str(root/'freeze-release.py');module.PLUGIN=sha(plugin_path.read_bytes())
  with zipfile.ZipFile(plugin_path) as plugin:
   for n in plugin.namelist():files[prefix+'/share/krita/'+('actions/flapart.action' if n=='flapart.action' else 'pykrita/'+n)]=plugin.read(n)
  files[prefix+'/example.class']=b'\xca\xfe\xba\xbe\0\0\0\x41'+b'java content'
  self.archive=root/'runtime.zip';inventory=[]
  with zipfile.ZipFile(self.archive,'w') as z:
   for path,data in files.items():
    z.writestr(path,data);entry={'path':path,'bytes':len(data),'sha256':sha(data)}
    if path==self.exe or path in [x['archive_path'] for x in self.libs.values()]:entry.update(architectures=arches,native_dependencies=[])
    inventory.append(entry)
   if not win:
    path=prefix+'/lib/ssl-link';target='ssl.bin';i=zipfile.ZipInfo(path);i.create_system=3;i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,target);inventory.append({'path':path,'symlink':target})
  self.digest=sha(self.archive.read_bytes());self.docs={};self.refs={}
  base={'payload_sha256':self.digest,'target_platform':self.target}
  self.docs['inventory']={**base,'platform':self.target,'runtime_collected':True,'files':inventory}
  artifacts=[]
  for kind in ('source','license','recipe'):
   path=kind+'.txt';(root/path).write_text('synthetic '+kind);artifacts.append({'kind':kind,'path':path,'sha256':sha((root/path).read_bytes())})
  mapped=[{k:a[k] for k in ('path','sha256')} for a in artifacts]
  self.docs['source_closure']={**base,'complete':True,'artifacts':artifacts,'native_sources':{p:copy.deepcopy(mapped) for p in [self.exe]+[v['archive_path'] for v in self.libs.values()]}}
  for kind in ('relocation','installer','tls','python'):
   self.refs[kind]=[]
   for arch in arches:
    name=kind+'-'+arch;doc={**base,'process_architecture':arch,'hardware_architecture':'arm64' if not win else arch,'execution_mode':'translated' if not win and arch=='x86_64' else 'native','native_execution':True,'runtime_scope':'installed-runtime' if kind=='installer' else 'relocated-package'}
    if kind=='relocation':doc.update({k:True for k in ('relocated_package_test','compiled_fork','original_krita_sentinels_preserved','build_environment_absent')})
    if kind=='installer':
     doc.update({k:True for k in ('installer_passed','native_runtime_tested','profile_isolation_verified','ordinary_krita_unchanged','native_canvas_png_kra_passed','studio_menu_reopens','failed_upgrade_preserved_receipt','failed_upgrade_preserved_artwork_and_settings','successful_upgrade_preserved_artwork_and_settings','previous_runtime_retained')});doc['security_approval_automated']=False
    if kind=='tls':
     cases={'valid':{'python_ok':True,'qt_ok':True,'qt_finished':True,'qt_error':0,'qt_ssl_errors':[]}}
     for case in ('unknown_ca','hostname_mismatch','expired'):cases[case]={'python_ok':False,'qt_ok':False,'qt_finished':True,'qt_error':6,'qt_ssl_errors':['rejected'],'python_certificate_rejected':True,'python_verify_code':10 if case=='expired' else 62,'qt_ssl_error_codes':[6]}
     doc.update(passed=True,python_openssl='OpenSSL 3.5.9 2026',qt_openssl_runtime='OpenSSL 3.5.9 2026',cases=cases,official_python={'verified':True,'status':200},official_qt={'finished':True,'error':0,'ssl_errors':[],'status':200},loaded_libraries=[dict(self.libs[role],role=role) for role in ('ssl','crypto','python_ssl','qt_network')])
    if kind=='python':doc.update(passed=True,version='3.13.16',abi='cp313',soabi='cp313-win_amd64' if win else 'cpython-313-darwin',native_plugin_imports_passed=True,extension_modules={'baseline':['_ssl','_hashlib'],'candidate':['_ssl','_hashlib'],'missing':[]},interpreter_library=self.libs['python'])
    self.docs[name]=doc;self.refs[kind].append(name)
  self.evidence={'schema':2,'platform':self.target,'payload_sha256':self.digest,'profile_namespace':'flapart-native','signature':'adhoc'}
 def rewrite_link(self,target):
  with zipfile.ZipFile(self.archive) as z:entries=[(i,z.read(i)) for i in z.infolist()]
  with zipfile.ZipFile(self.archive,'w') as z:
   for i,data in entries:z.writestr(i,target.encode() if stat.S_ISLNK(i.external_attr>>16) else data)
  self.docs['inventory']['files'][-1]['symlink']=target
  self.digest=sha(self.archive.read_bytes());self.evidence['payload_sha256']=self.digest
  for doc in self.docs.values():doc['payload_sha256']=self.digest
 def write(self):
  refs={}
  for name,doc in self.docs.items():
   data=json.dumps(doc).encode();(self.root/(name+'.json')).write_bytes(data);refs[name]={'path':name+'.json','sha256':sha(data)}
  self.evidence['receipts']={k:refs[k] for k in ('inventory','source_closure')}
  self.evidence['receipts'].update({k:[refs[n] for n in names] for k,names in self.refs.items()});return self.evidence
 def freeze(self):return self.m.freeze(self.archive,self.write(),self.platform,'0.2.0','https://accounts.flaptown.com/flapsoft/downloads/fixture.zip',self.exe,self.root)

class Contract(unittest.TestCase):
 def test_both_scripts(self):
  for directory in ('windows-online','macos-online'):
   spec=importlib.util.spec_from_file_location(directory,ROOT/directory/'freeze-release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   self.assertEqual(m.binary_architectures(b'\xca\xfe\xba\xbe\0\0\0\x41'+b'Java class'),())
   with self.assertRaises(ValueError):m.binary_architectures(b'MZ'+b'\0'*62)
   with self.assertRaises(ValueError):m.binary_architectures(b'\xca\xfe\xba\xbe'+struct.pack('>I',2)+b'\0'*40)
   for platform in ('windows-x86_64','macos-universal2'):
    with self.subTest(script=directory,platform=platform),tempfile.TemporaryDirectory() as tmp:
     f=Fixture(m,Path(tmp),platform);result=f.freeze();self.assertEqual(result['platform'],'macos-universal' if platform.startswith('macos') else platform)
     if platform.startswith('macos'):self.assertEqual(result['qualification']['execution']['tls']['x86_64']['execution_mode'],'translated')
   mutations={
    'wrong archive':lambda f:f.docs['tls-x86_64'].update(payload_sha256='0'*64),
    'wrong platform':lambda f:f.docs['installer-x86_64'].update(target_platform='macos-arm64'),
    'SDK receipt':lambda f:f.docs['tls-x86_64'].update(runtime_scope='sdk'),
    'missing upgrade':lambda f:f.docs['installer-x86_64'].pop('failed_upgrade_preserved_artwork_and_settings'),
    'old SSL':lambda f:f.docs['tls-x86_64'].update(python_openssl='OpenSSL 1.1.1'),
    'old SSL import':lambda f:f.docs['inventory']['files'][0].update(native_dependencies=['libssl-1_1-x64.dll']),
    'expired accepted':lambda f:f.docs['tls-x86_64']['cases']['expired'].update(python_ok=True),
    'default trust failed':lambda f:f.docs['tls-x86_64']['official_python'].update(verified=False),
    'extension lost':lambda f:f.docs['python-x86_64']['extension_modules'].update(candidate=['_ssl']),
    'wrong SOABI':lambda f:f.docs['python-x86_64'].update(soabi='cp313'),
    'unmapped source':lambda f:f.docs['source_closure']['native_sources'].pop(f.exe),
    'unmapped library':lambda f:f.docs['tls-x86_64']['loaded_libraries'][0].update(sha256='0'*64),
    'fake native hardware':lambda f:f.docs['tls-x86_64'].update(hardware_architecture='arm64'),
    'missing receipt':lambda f:f.refs['python'].clear(),
   }
   for label,mutate in mutations.items():
    with self.subTest(script=directory,rejection=label),tempfile.TemporaryDirectory() as tmp:
     f=Fixture(m,Path(tmp));mutate(f)
     with self.assertRaises(ValueError):f.freeze()
   for label in ('missing arm run','incorrect slices','symlink escape','tampered receipt','missing source artifact','symlink loop','symlink dangling'):
    with self.subTest(script=directory,rejection=label),tempfile.TemporaryDirectory() as tmp:
     f=Fixture(m,Path(tmp),'macos-universal2')
     if label=='symlink loop':f.rewrite_link('ssl-link')
     if label=='symlink dangling':f.rewrite_link('missing.bin')
     if label=='missing arm run':f.refs['tls'].pop(0)
     if label=='incorrect slices':f.docs['inventory']['files'][0]['architectures']=['arm64']
     if label=='symlink escape':f.docs['inventory']['files'][-1]['symlink']='../../../../outside'
     if label=='missing source artifact':(Path(tmp)/'source.txt').unlink()
     evidence=f.write()
     if label=='tampered receipt':(Path(tmp)/'inventory.json').write_text('{}')
     with self.assertRaises(ValueError):m.freeze(f.archive,evidence,f.platform,'0.2.0','https://accounts.flaptown.com/flapsoft/downloads/fixture.zip',f.exe,f.root)

if __name__=='__main__':unittest.main()
