"""Synthetic source-provenance/parser tests, never native release evidence."""
import hashlib,json,struct,tempfile,unittest,zipfile
from pathlib import Path
from qualify_sources import produce,sha,system_import,critical
from native_metadata import parse

def pe(import_name=None,delay=None):
 d=bytearray(1024);d[:2]=b'MZ';struct.pack_into('<I',d,60,64);d[64:68]=b'PE\0\0';struct.pack_into('<H',d,68,0x8664);struct.pack_into('<H',d,84,240);struct.pack_into('<H',d,88,0x20b);struct.pack_into('<Q',d,112,0x140000000);struct.pack_into('<I',d,148,1024);struct.pack_into('<I',d,196,16)
 if import_name:struct.pack_into('<II',d,208,512,40);struct.pack_into('<I',d,524,600);d[600:601+len(import_name)]=import_name.encode()+b'\0'
 if delay:struct.pack_into('<II',d,304,700,64);struct.pack_into('<II',d,700,1,800);d[800:801+len(delay)]=delay.encode()+b'\0'
 return bytes(d)
def macho(cpu=0x1000007,weak='@rpath/libsample.dylib',uid=b'1'*16):
 name=weak.encode()+b'\0';length=(24+len(name)+7)//8*8;command=struct.pack('<IIIIII',0x80000018,length,24,0,0,0)+name+b'\0'*(length-24-len(name));commands=struct.pack('<II',0x1b,24)+uid+command
 return b'\xcf\xfa\xed\xfe'+struct.pack('<IIIIIII',cpu,0,6,2,len(commands),0,0)+commands
class Fixture:
 def __init__(self,root,name='app/bin/sample.dll',data=None):
  self.root=root;self.name=name;data=data or pe();self.archive=root/'candidate.zip'
  with zipfile.ZipFile(self.archive,'w') as z:z.writestr(name,data)
  self.pin=sha(self.archive);self.value=hashlib.sha256(data).hexdigest();self.commit='a'*40;self.sdk='b'*64
  source=self.ref('source.txt','source');recipe=self.ref('recipes-'+self.commit+'.tar','recipe');license=self.ref('LICENSE.txt','notice')
  self.source=source;self.recipe=recipe;self.license=license;selected={'url':'https://example.invalid/source','algorithm':'SHA256','digest':source['sha256'],'artifact':source}
  branch=self.ref('branch.json',{'platform':'windows','package':'ext_sample','recipe_commit':self.commit,'recipe_sha256':recipe['sha256'],'selection_basis':'Synthetic reviewed Windows condition','selected_sources':[selected]})
  self.docs={'inventory':{'platform':'windows-x86_64','files':[{'path':name,'sha256':self.value,'bytes':len(data)}]},'correspondence':[{'sdk_path':'bin/sample.dll','sha256':self.value,'package':'ext_sample','recipe_commit':self.commit,'archive_sha256':self.sdk,'macho_uuids':[]}],'sdk_lock':{'platform':'windows','packages':[{'name':'ext_sample','recipe_commit':self.commit,'sha256':self.sdk}]},'source_plan':[{'platform':'windows','name':'ext_sample','recipe_commit':self.commit,'urls_all_platform_branches':[{k:selected[k] for k in ('url','algorithm','digest')}],'git_all_platform_branches':[]}],'url_receipt':[{**{k:selected[k] for k in ('url','algorithm','digest')},**source,'status':'verified-existing'}],'recipes':[{'commit':self.commit,'archive':recipe['path'],'sha256':recipe['sha256']}],'selections':{'platform':'windows','packages':[{'platform':'windows','package':'ext_sample','recipe_commit':self.commit,'recipe':recipe,'branch_evidence':branch,'sources':[selected],'license_notices':[license]}]}}
 def ref(self,name,value):
  path=self.root/name;path.write_text(json.dumps(value) if isinstance(value,(dict,list)) else value);return {'path':name,'sha256':sha(path)}
 def run(self,platform="windows-x86_64"):
  refs={k:self.ref(k+'.json',v) for k,v in self.docs.items()};return produce(self.archive,self.pin,platform,refs,self.root)
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_complete_synthetic_correspondence(self):
  f=Fixture(self.root);inventory,result=f.run();self.assertTrue(result['complete']);self.assertEqual(inventory['files'][0]['native_dependencies'],[]);self.assertFalse(result['release_qualified'])
 def test_pending_mutations(self):
  cases={
   'unknown origin':lambda f:f.docs['correspondence'].clear(),
   'wrong lock':lambda f:f.docs['sdk_lock']['packages'][0].update(sha256='c'*64),
   'no notices':lambda f:f.docs['selections']['packages'][0].update(license_notices=[]),
   'wrong platform branch':lambda f:f.docs['selections']['packages'][0].update(platform='macos'),
   'wrong recipe':lambda f:f.docs['recipes'][0].update(commit='d'*40),
   'no selection':lambda f:f.docs['selections']['packages'].clear(),
   'wrong source receipt':lambda f:f.docs['url_receipt'][0].update(sha256='e'*64),
   'all branches not selection':lambda f:f.docs['source_plan'][0].update(urls_all_platform_branches=[]),
  }
  for label,mutate in cases.items():
   with self.subTest(label=label):
    f=Fixture(self.root);mutate(f);_,result=f.run();self.assertFalse(result['complete']);self.assertTrue(result['unresolved'])
 def test_maintained_components_need_explicit_build(self):
  for name in ('krita.exe','Qt5Network.dll','qgenericbearer.dll','libssl-3-x64.dll','python313.dll','libgcc_s_seh-1.dll'):
   with self.subTest(binary=name):
    f=Fixture(self.root,'app/bin/'+name);_,result=f.run();self.assertFalse(result['complete']);self.assertIn('provenance pending',str(result['unresolved']))
 def test_preserved_pyqt_bindings_are_not_rebuilt_qt_runtime(self):
  for name in ('QtNetwork.cpython-313-darwin.so','QtNetwork.abi3.so','QtNetwork.pyd'):self.assertFalse(critical('PyQt5/'+name,'ext_pyqt5'))
  for name in ('QtNetwork','Qt5Network.dll','libQt5Network.5.dylib','qgenericbearer.dll','python313.dll','libssl.3.dylib'):self.assertTrue(critical(name))
 def test_archive_pin_refused(self):
  f=Fixture(self.root);f.pin='0'*64
  with self.assertRaisesRegex(ValueError,'archive SHA'):f.run()
 def test_inventory_changed_refused(self):
  f=Fixture(self.root);f.docs['inventory']['files'][0]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'Inventory byte'):f.run()
 def test_missing_import_pending(self):
  f=Fixture(self.root,data=pe('missing.dll'));_,result=f.run();self.assertFalse(result['complete']);self.assertEqual(result['unresolved'][0]['reason'],'dependency-unresolved')
 def test_narrow_system_import_evidence(self):
  f=Fixture(self.root,data=pe('KERNEL32.dll'));proof=f.ref('system.json',{'platform':'windows','dependency':'KERNEL32.dll','windows_system_component':True,'basis':'Synthetic Windows system evidence'});f.docs['selections']['dependencies']={f.name:{'KERNEL32.dll':{'system_evidence':proof}}};_,result=f.run();self.assertTrue(result['complete'])
  self.assertFalse(system_import('libssl-3-x64.dll','windows'));self.assertFalse(system_import('/tmp/host.dylib','macos'))
 def test_os_d3d_compiler_requires_supported_target_evidence(self):
  f=Fixture(self.root,data=pe('D3DCompiler_47.dll'))
  proof={'platform':'windows','dependency':'D3DCompiler_47.dll','windows_system_component':True,'basis':'Synthetic Windows OS component evidence'}
  f.docs['selections']['dependencies']={f.name:{'D3DCompiler_47.dll':{'system_evidence':f.ref('d3d-system.json',proof)}}}
  _,result=f.run();self.assertFalse(result['complete'])
  proof['minimum_windows']='10';f.docs['selections']['dependencies'][f.name]['D3DCompiler_47.dll']['system_evidence']=f.ref('d3d-system.json',proof)
  _,result=f.run();self.assertTrue(result['complete'])
  self.assertFalse(system_import('D3DCompiler_43.dll','windows'))
 def test_wrong_import_target_rejected(self):
  f=Fixture(self.root,data=pe('different.dll'));f.docs['selections']['dependencies']={f.name:{'different.dll':{'archive_path':f.name}}};_,result=f.run();self.assertFalse(result['complete'])
 def test_rebuilt_provenance_does_not_accept_wrong_output(self):
  f=Fixture(self.root,'app/bin/krita.exe');proof=f.ref('build.json',{'target_platform':'windows-x86_64','outputs':[{'archive_path':f.name,'sha256':'0'*64}]});f.docs['selections']['rebuilt']={f.name:proof};_,result=f.run();self.assertFalse(result['complete'])
 def test_non_native_asset_notice_coverage(self):
  f=Fixture(self.root);data=b'font fixture';name='app/font.ttf'
  with zipfile.ZipFile(f.archive,'a') as z:z.writestr(name,data)
  f.pin=sha(f.archive);f.docs['inventory']['files'].append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
  _,result=f.run();self.assertFalse(result['complete']);self.assertEqual(result['unresolved'][0]['reason'],'asset-notices-pending')
  f.docs['selections']['asset_notices']={name:[f.license]};_,result=f.run();self.assertTrue(result['complete'])
 def test_uuid_mapping_requires_transformation_provenance(self):
  f=Fixture(self.root,'Flapart Studio.app/Contents/lib/libsample.dylib',macho());f.docs['inventory']['platform']='macos-x86_64'
  for name in ('sdk_lock','selections'):f.docs[name]['platform']='macos'
  f.docs['source_plan'][0]['platform']='macos';selection=f.docs['selections']['packages'][0];selection['platform']='macos';branch=json.loads((self.root/'branch.json').read_text());branch['platform']='macos';selection['branch_evidence']=f.ref('branch.json',branch)
  origin=f.docs['correspondence'][0];origin['macho_uuids']=parse(macho())['macho_uuids'];origin['sha256']='f'*64;f.docs['selections']['dependencies']={f.name:{'@rpath/libsample.dylib':{'archive_path':f.name}}}
  _,result=f.run('macos-x86_64');self.assertFalse(result['complete']);self.assertIn('UUID identity alone',str(result['unresolved']))
  log=f.ref('transform.log','synthetic signing transformation');proof=f.ref('transform.json',{'target_platform':'macos-x86_64','input_sha256':'f'*64,'output_sha256':f.value,'commands':['synthetic controlled signing'],'log':log});f.docs['selections']['transformations']={f.name:proof}
  _,result=f.run('macos-x86_64');self.assertTrue(result['complete'])
 def test_actual_imports_and_delay_imports_parsed(self):self.assertEqual(parse(pe('KERNEL32.dll','USER32.dll'))['native_dependencies'],['KERNEL32.dll','USER32.dll'])
 def test_weak_macho_import_and_uuid_parsed(self):
  result=parse(macho());self.assertEqual(result['native_dependencies'],['@rpath/libsample.dylib']);self.assertEqual(len(result['macho_uuids']),1)
 def test_universal_preserves_per_slice_imports(self):
  x=macho(weak='@rpath/x.dylib');a=macho(0x100000c,weak='@rpath/a.dylib',uid=b'2'*16);data=b'\xca\xfe\xba\xbe'+struct.pack('>I',2)+struct.pack('>IIIII',0x1000007,0,48,len(x),0)+struct.pack('>IIIII',0x100000c,0,48+len(x),len(a),0)+x+a;result=parse(data);self.assertEqual(result['architectures'],['arm64','x86_64']);self.assertEqual(result['slices'][0]['dependencies'],['@rpath/x.dylib']);self.assertEqual(result['slices'][1]['dependencies'],['@rpath/a.dylib'])
 def test_java_not_macho(self):self.assertIsNone(parse(b'\xca\xfe\xba\xbe\0\0\0\x41'))
 def test_truncated_native_refused(self):
  with self.assertRaises(ValueError):parse(b'MZbad')
if __name__=='__main__':unittest.main()
