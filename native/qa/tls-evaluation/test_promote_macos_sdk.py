"""Synthetic SDK promotion tests using real Mach-O headers; no native execution."""
import hashlib,importlib.util,json,os,struct,tempfile,unittest
from pathlib import Path
FILE=Path(__file__).with_name('promote-macos-sdk.py');spec=importlib.util.spec_from_file_location('promotion',FILE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def macho(architectures=('x86_64','arm64'),imports=()):
 cpu={'x86_64':0x1000007,'arm64':0x100000c}
 def thin(arch):
  commands=b''
  for dep in imports:
   name=dep.encode()+b'\0';size=(24+len(name)+7)//8*8;commands+=struct.pack('<IIIIII',0xc,size,24,0,0,0)+name+b'\0'*(size-24-len(name))
  return b'\xcf\xfa\xed\xfe'+struct.pack('<IIIIIII',cpu[arch],0,6,len(imports),len(commands),0,0)+commands
 if len(architectures)==1:return thin(architectures[0])
 header=b'\xca\xfe\xba\xbe'+struct.pack('>I',len(architectures));offset=8+20*len(architectures);body=b''
 for arch in architectures:
  part=thin(arch);header+=struct.pack('>IIIII',cpu[arch],0,offset,len(part),0);offset+=len(part);body+=part
 return header+body

def ar_object(arch='arm64',bad_cpu=False,body=None):
 data=bytearray(macho((arch,)))
 struct.pack_into('<I',data,12,1)  # MH_OBJECT, not MH_DYLIB.
 if bad_cpu:struct.pack_into('<I',data,4,0x1000007 if arch=='arm64' else 0x100000c)
 def member(name,payload):
  header=name.ljust(16)+b'0'.ljust(12)+b'0'.ljust(6)+b'0'.ljust(6)+b'100644'.ljust(8)+str(len(payload)).encode().ljust(10)+b'`\n'
  return header+payload+(b'\n' if len(payload)%2 else b'')
 # Actual Apple BSD extended-name shape, including NUL name alignment.
 name=b'object.o\0\0\0\0'
 return b'!<arch>\n'+member(b'#1/12',name+(bytes(data) if body is None else body))
def fat_archive(parts=None):
 parts=parts or [('x86_64',ar_object('x86_64')),('arm64',ar_object('arm64'))]
 cpus={'x86_64':0x1000007,'arm64':0x100000c};header=b'\xca\xfe\xba\xbe'+struct.pack('>I',len(parts));offset=8+20*len(parts);body=b''
 for arch,data in parts:
  header+=struct.pack('>IIIII',cpus[arch],0,offset,len(data),0);body+=data;offset+=len(data)
 return header+body

def tree(root):
 result={}
 for p in sorted(root.rglob('*')):
  name=p.relative_to(root).as_posix()
  if p.is_symlink():result[name]=('link',os.readlink(p))
  elif p.is_file():result[name]=('file',hashlib.sha256(p.read_bytes()).hexdigest())
 return result
class Fixture:
 def __init__(self,root):
  self.work=root/'work';self.sdk=self.work/'sdk';self.ssl=self.work/'openssl';self.evidence=root/'evidence';self.evidence.mkdir();self.output=root/'promotion.json'
  for local,retained in [('openssl-build/openssl-build-receipt.json','openssl-build.json'),('network-build/receipt.json','network-build.json'),('bearer-build/receipt.json','bearer-build.json'),('python-build/python-build-receipt.json','python-build.json')]:
   content=json.dumps({'compiled':True,'component':retained});self.write(self.work/local,content);self.write(self.evidence/retained,content)
  self.write(self.evidence/'native-ci-receipt.json',json.dumps({'passed':True,'stage':'native-tls-probe-passed'}));self.write(self.evidence/'tls-validation.json',json.dumps({'passed':True}))
  self.network=self.work/'network-build/lib/QtNetwork.framework/Versions/5';self.target=self.sdk/'lib/QtNetwork.framework/Versions/5'
  for name in ('QtNetwork','QtNetwork_debug'):
   self.write(self.network/name,macho(imports=('@rpath/libssl.3.dylib','@rpath/libcrypto.3.dylib')));self.write(self.network/'Resources'/(name+'.prl'),'QMAKE_PRL_LIBS = -L'+str(self.ssl/'lib')+' -lssl -lcrypto\n');self.write(self.target/name,macho(imports=('@rpath/libssl.1.1.dylib',)))
  self.write(self.sdk/'include/openssl/obsolete.h','obsolete');self.write(self.sdk/'include/openssl/opensslv.h','OpenSSL 1.1.1');self.write(self.sdk/'include/other.h','preserve me')
  self.write(self.ssl/'include/openssl/opensslv.h','#define OPENSSL_VERSION_TEXT "OpenSSL 3.5.9"');self.write(self.ssl/'include/openssl/ssl.h','maintained header')
  for name in ('libssl.1.1.dylib','libcrypto.1.1.dylib'):self.write(self.sdk/'lib'/name,macho())
  for name in ('libssl.3.dylib','libcrypto.3.dylib'):self.write(self.ssl/'lib'/name,macho())
  self.write(self.ssl/'lib/pkgconfig/openssl.pc','prefix='+str(self.ssl)+'\nlibdir=${prefix}/lib\n');self.write(self.ssl/'ssl/openssl.cnf','configuration');self.write(self.ssl/'bin/openssl',macho(imports=('@rpath/libssl.3.dylib','@rpath/libcrypto.3.dylib')))
 def write(self,path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data if isinstance(data,bytes) else data.encode())
 def run(self):return m.promote(self.work,self.evidence,self.output)
class Promotion(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=Fixture(Path(self.tmp.name))
 def refused_without_mutation(self):
  before=tree(self.f.sdk)
  with self.assertRaises((AssertionError,ValueError)):self.f.run()
  self.assertEqual(tree(self.f.sdk),before)
 def test_success_replaces_headers_metadata_and_both_variants(self):
  result=self.f.run();self.assertTrue(result['promoted']);self.assertFalse(result['release_qualified']);self.assertFalse(result['runtime_qualified']);self.assertFalse((self.f.sdk/'include/openssl/obsolete.h').exists());self.assertEqual((self.f.sdk/'include/other.h').read_text(),'preserve me')
  self.assertNotIn(str(self.f.ssl),(self.f.sdk/'lib/pkgconfig/openssl.pc').read_text());self.assertIn(str(self.f.sdk),(self.f.sdk/'lib/pkgconfig/openssl.pc').read_text())
  for name in ('QtNetwork','QtNetwork_debug'):
   self.assertEqual((self.f.target/name).read_bytes(),(self.f.network/name).read_bytes());self.assertIn(str(self.f.sdk),(self.f.target/'Resources'/(name+'.prl')).read_text())
  for name in ('libssl.1.1.dylib','libcrypto.1.1.dylib'):self.assertFalse((self.f.sdk/'lib'/name).exists())
 def test_universal_openssl_archives_promoted_without_runtime_parser_change(self):
  data=fat_archive()
  for name in ('libssl.a','libcrypto.a'):self.f.write(self.f.ssl/'lib'/name,data)
  info=m.native(self.f.ssl/'lib/libssl.a');self.assertEqual(info['format'],'static-archive');self.assertEqual(info['architectures'],['arm64','x86_64'])
  with self.assertRaisesRegex(ValueError,'Invalid universal native slice'):m.metadata.parse(data)
  result=self.f.run();self.assertTrue(result['promoted']);self.assertEqual((self.f.sdk/'lib/libssl.a').read_bytes(),data)
 def test_archives_already_in_sdk_are_validated(self):
  self.f.write(self.f.sdk/'lib/existing.a',fat_archive());self.assertTrue(self.f.run()['promoted'])
 def test_wrong_archive_object_cpu_refused_before_mutation(self):
  self.f.write(self.f.ssl/'lib/libssl.a',fat_archive([('arm64',ar_object('arm64',True)),('x86_64',ar_object('x86_64'))]));self.refused_without_mutation()
 def test_single_arch_static_input_refused(self):
  self.f.write(self.f.ssl/'lib/libssl.a',fat_archive([('arm64',ar_object())]));self.refused_without_mutation()
 def test_archive_cannot_impersonate_dynamic_library(self):
  self.f.write(self.f.ssl/'lib/libssl.3.dylib',fat_archive());self.refused_without_mutation()
 def test_thin_static_archive_in_promotion_plan_refused(self):
  self.f.write(self.f.ssl/'lib/libssl.a',ar_object());self.refused_without_mutation()
 def test_dynamic_macho_bad_slice_still_refused_with_filename(self):
  data=bytearray(macho());struct.pack_into('<I',data,52,0x100000c)  # First declared x86 slice carries wrong CPU.
  path=self.f.ssl/'lib/libssl.3.dylib';self.f.write(path,bytes(data))
  with self.assertRaisesRegex(ValueError,'libssl.3.dylib.*CPU mismatch'):m.native(path)
  self.refused_without_mutation()
 def test_static_member_header_bounds_truncation_and_padding_refused(self):
  variants=[]
  archive=bytearray(ar_object());archive[56:66]=b'9999999999';variants.append(bytes(archive))
  archive=bytearray(ar_object());archive[66:68]=b'xx';variants.append(bytes(archive))
  variants.append(ar_object()[:30])
  for archive in variants:
   self.f.write(self.f.ssl/'lib/libssl.a',fat_archive([('arm64',archive),('x86_64',ar_object('x86_64'))]));self.refused_without_mutation()
 def test_mixed_static_and_dynamic_slices_refused(self):
  self.f.write(self.f.ssl/'lib/libssl.a',fat_archive([('arm64',ar_object()),('x86_64',macho(('x86_64',)))]));self.refused_without_mutation()
 def test_malformed_static_bounds_and_members_refused(self):
  valid=fat_archive();variants=[]
  overlap=bytearray(valid);struct.pack_into('>I',overlap,36,48);variants.append(bytes(overlap))
  variants.extend([valid[:-1],fat_archive([('arm64',ar_object(body=b'not an object')),('x86_64',ar_object('x86_64'))]),fat_archive([('arm64',ar_object()),('arm64',ar_object())]),fat_archive([('arm64',ar_object(body=macho(('arm64',)))),('x86_64',ar_object('x86_64'))])])
  for data in variants:
   with self.subTest(size=len(data)):
    self.f.write(self.f.ssl/'lib/libssl.a',data);self.refused_without_mutation()
 def test_invalid_archive_diagnostic_names_file(self):
  path=self.f.ssl/'lib/libssl.a';self.f.write(path,fat_archive()[:-1])
  with self.assertRaisesRegex(ValueError,'libssl.a'):m.native(path)
 def test_only_verified_old_engine_modules_are_retired(self):
  paths=[self.f.sdk/'lib/engines-1.1'/name for name in ('capi.dylib','padlock.dylib')]
  for path in paths:self.f.write(path,macho(imports=('@rpath/libcrypto.1.1.dylib',)))
  hashes={str(p.relative_to(self.f.sdk)):m.digest(p) for p in paths}
  result=self.f.run();self.assertTrue(result['promoted']);self.assertFalse(paths[0].parent.exists())
  removed={r['path']:r['sha256'] for r in result['removed'] if r.get('reason')=='retired-openssl-1.1-engine'}
  self.assertEqual(removed,hashes)
 def test_unknown_retired_engine_entry_refused(self):
  self.f.write(self.f.sdk/'lib/engines-1.1/extra.dylib',macho(imports=('@rpath/libcrypto.1.1.dylib',)));self.refused_without_mutation()
 def test_nonobsolete_engine_refused(self):
  self.f.write(self.f.sdk/'lib/engines-1.1/capi.dylib',macho(imports=('@rpath/libcrypto.3.dylib',)));self.refused_without_mutation()
 def test_retired_engine_consumer_refused(self):
  self.f.write(self.f.sdk/'lib/engines-1.1/capi.dylib',macho(imports=('@rpath/libcrypto.1.1.dylib',)))
  self.f.write(self.f.sdk/'plugins/consumer.dylib',macho(imports=('@rpath/engines-1.1/capi.dylib',)));self.refused_without_mutation()
 def test_retired_engine_symlink_refused(self):
  path=self.f.sdk/'lib/engines-1.1';path.symlink_to(self.f.ssl/'lib',target_is_directory=True);self.refused_without_mutation()
 def test_workspace_receipt_mismatch_refused(self):
  (self.f.evidence/'network-build.json').write_text('{}');self.refused_without_mutation()
 def test_failed_native_tls_receipt_refused(self):
  (self.f.evidence/'native-ci-receipt.json').write_text(json.dumps({'passed':False,'stage':'native-tls-probe-passed'}));self.refused_without_mutation()
 def test_old_ssl_consumer_refused_before_mutation(self):
  self.f.write(self.f.sdk/'plugins/remaining.dylib',macho(imports=('@rpath/libcrypto.1.1.dylib',)));self.refused_without_mutation()
 def test_missing_debug_variant_refused_before_mutation(self):
  (self.f.network/'QtNetwork_debug').unlink();self.refused_without_mutation()
 def test_missing_debug_link_metadata_refused(self):
  (self.f.network/'Resources/QtNetwork_debug.prl').unlink();self.refused_without_mutation()
 def test_single_slice_debug_variant_refused(self):
  self.f.write(self.f.network/'QtNetwork_debug',macho(('arm64',),('@rpath/libssl.3.dylib',)));self.refused_without_mutation()
 def test_old_ssl_debug_variant_refused(self):
  self.f.write(self.f.network/'QtNetwork_debug',macho(imports=('@rpath/libssl.1.1.dylib',)));self.refused_without_mutation()
 def test_target_parent_symlink_escape_refused(self):
  outside=Path(self.tmp.name)/'outside';outside.mkdir();target=self.f.sdk/'ssl';target.symlink_to(outside);self.refused_without_mutation();self.assertEqual(list(outside.iterdir()),[])
 def test_source_symlink_escape_refused(self):
  outside=Path(self.tmp.name)/'outside';outside.write_text('outside');(self.f.ssl/'lib/escape').symlink_to(outside);self.refused_without_mutation()
 def test_copied_relative_symlink_cannot_escape_sdk(self):
  outside=self.f.work/'outside';outside.write_text('outside');(self.f.ssl/'lib/escape').symlink_to('../../outside');self.refused_without_mutation()
 def test_single_slice_openssl_provider_refused(self):
  self.f.write(self.f.ssl/'lib/libssl.3.dylib',macho(('arm64',)));self.refused_without_mutation()
 def test_forward_symlink_copy_does_not_depend_on_enumeration_order(self):
  directory=self.f.ssl/'lib/forward';directory.mkdir();self.f.write(directory/'provider.dylib',macho())
  for i in range(16):(directory/f'alias-{i}.dylib').symlink_to('provider.dylib')
  if list(directory.iterdir()).index(directory/'provider.dylib')==0:self.skipTest('Filesystem enumerated provider first; forward-link condition not exercised')
  result=self.f.run();self.assertTrue(result['promoted']);self.assertTrue((self.f.sdk/'lib/forward/alias-0.dylib').is_symlink());self.assertEqual((self.f.sdk/'lib/forward/alias-0.dylib').read_bytes(),(directory/'provider.dylib').read_bytes())
 def test_new_openssl_cli_old_ssl_import_refused(self):
  self.f.write(self.f.ssl/'bin/openssl',macho(imports=('@rpath/libssl.1.1.dylib',)));self.refused_without_mutation()
if __name__=='__main__':unittest.main()
