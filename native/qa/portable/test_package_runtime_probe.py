"""Synthetic provenance tests; no embedded runtime/native qualification claims."""
import hashlib,importlib.util,json,os,stat,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
FILE=Path(__file__).with_name('package-runtime-probe.py')
spec=importlib.util.spec_from_file_location('probe',FILE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Provenance(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'runtime';self.root.mkdir();self.archive=self.base/'candidate.zip'
 def fixture(self):
  with zipfile.ZipFile(self.archive,'w') as z:
   for name in ('bin/python3.13','bin/openssl','lib/libssl.so.3','lib/libcrypto.so.3','lib/_ssl.so','lib/QtNetwork','lib/libpython3.13.so'):
    data=('fixture '+name).encode();z.writestr(name,data);path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
  return m.archive_inventory(self.archive,self.root)
 def test_actual_host_python_rejected_before_output(self):
  result=subprocess.run([sys.executable,str(FILE),'--archive',str(self.archive),'--runtime-root',str(self.root),'--baseline-extension-manifest',str(self.base/'baseline'),'--baseline-extension-sha256','0'*64,'--openssl',str(self.root/'openssl'),'--output',str(self.base/'out'),'--runtime-scope','relocated-package','--target-platform','windows-x86_64'],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertIn('Refusing host Python',result.stderr);self.assertFalse((self.base/'out').exists())
 def test_base_prefix_cannot_be_host(self):
  with patch.object(m.sys,'executable',str(self.root/'python')),patch.object(m.sys,'base_prefix','/outside'):
   with self.assertRaisesRegex(ValueError,'base prefix'):m.require_embedded(self.root)
 def test_nonisolated_python_rejected(self):
  with patch.object(m.sys,'flags',SimpleNamespace(isolated=0)),self.assertRaisesRegex(ValueError,'must run isolated'):m.require_isolated(self.root)
 def test_external_pure_python_path_rejected(self):
  with patch.object(m.sys,'flags',SimpleNamespace(isolated=1)),patch.object(m.sys,'path',[str(self.root/'lib'),str(self.base/'SDK')]),self.assertRaisesRegex(ValueError,'import path escapes'):m.require_isolated(self.root)
 def test_isolated_candidate_paths_accepted(self):
  with patch.object(m.sys,'flags',SimpleNamespace(isolated=1)),patch.object(m.sys,'path',[str(self.root/'lib'),str(self.root/'python313.zip')]):m.require_isolated(self.root)
 def test_files_match_archive(self):
  inventory=self.fixture();row=m.bound_file(self.root/'bin/python3.13',self.root,inventory);self.assertEqual(row['archive_path'],'bin/python3.13')
 def test_runtime_mutation_rejected(self):
  self.fixture();(self.root/'bin/python3.13').write_text('changed')
  with self.assertRaisesRegex(ValueError,'differs from archive'):m.archive_inventory(self.archive,self.root)
 def test_after_inventory_mutation_rejected(self):
  inventory=self.fixture();(self.root/'lib/libssl.so.3').write_text('changed')
  with self.assertRaisesRegex(ValueError,'does not match archive'):m.bound_file(self.root/'lib/libssl.so.3',self.root,inventory)
 def test_external_loaded_binary_rejected(self):
  inventory=self.fixture();outside=self.base/'evil.so';outside.write_text('outside')
  with self.assertRaisesRegex(ValueError,'outside candidate'):m.bound_file(outside,self.root,inventory)
 def test_unsafe_archive_rejected(self):
  with zipfile.ZipFile(self.archive,'w') as z:z.writestr('../outside','no')
  with self.assertRaisesRegex(ValueError,'Unsafe archive'):m.archive_inventory(self.archive,self.root)
 def test_symlink_escape_rejected(self):
  outside=self.base/'outside';outside.write_text('no');(self.root/'link').symlink_to(outside)
  with zipfile.ZipFile(self.archive,'w') as z:
   i=zipfile.ZipInfo('link');i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,str(outside))
  with self.assertRaisesRegex(ValueError,'outside archive'):m.archive_inventory(self.archive,self.root)
 def test_regular_file_symlink_substitution_rejected(self):
  self.fixture();path=self.root/'lib/QtNetwork';path.unlink();path.symlink_to('libssl.so.3')
  with self.assertRaisesRegex(ValueError,'substituted'):m.archive_inventory(self.archive,self.root)
 def test_baseline_pin_and_shape(self):
  path=self.base/'baseline.json';path.write_text(json.dumps({'extensions':['_ssl','_hashlib']}));pin=m.digest(path);self.assertEqual(m.baseline(path,pin),['_ssl','_hashlib'])
  with self.assertRaisesRegex(ValueError,'hash mismatch'):m.baseline(path,'0'*64)
  path.write_text(json.dumps({'extensions':['_ssl','_ssl']}))
  with self.assertRaisesRegex(ValueError,'Invalid baseline'):m.baseline(path,m.digest(path))
 def test_mapped_roles_bind_exact_files(self):
  inventory=self.fixture();paths=[str(self.root/name) for name in inventory];rows,system,roles=m.mapped_receipt(paths,self.root,inventory)
  self.assertEqual(set(roles),{'ssl','crypto','python_ssl','qt_network','python'});self.assertFalse(system);self.assertEqual(len(rows),7)
 def test_system_ssl_cannot_replace_candidate(self):
  inventory=self.fixture();paths=[str(self.root/name) for name in inventory]+['/usr/lib/libssl.so.3']
  with patch.object(m,'system_path',return_value=True),self.assertRaisesRegex(ValueError,'Host/SDK'):m.mapped_receipt(paths,self.root,inventory)
 def test_unmapped_sdk_library_rejected(self):
  inventory=self.fixture();paths=[str(self.root/name) for name in inventory]+[str(self.base/'SDK/QtCore.so')]
  with self.assertRaisesRegex(ValueError,'Host/SDK'):m.mapped_receipt(paths,self.root,inventory)
 def test_qt_runtime_is_not_pyqt_extension(self):
  for name in ('QtNetwork.pyd','QtNetwork.abi3.so','QtNetwork.cpython-313-darwin.so'):self.assertIsNone(m.module_role(name))
  for name in ('QtNetwork','Qt5Network.dll','libQt5Network.so.5','libQt5Network.5.dylib'):
   self.assertEqual(m.module_role(name),'qt_network')
 def test_python_core_is_not_shim_or_executable(self):
  for name in ('python3.dll','python3.13','python313.exe','python.exe'):self.assertIsNone(m.module_role(name))
  for name in ('python313.dll','libpython3.13.so.1.0','libpython3.13.dylib','App/Python.framework/Versions/3.13/Python'):self.assertEqual(m.module_role(name),'python')
 def test_parent_maps_cannot_fill_missing_tls_child_role(self):
  inventory=self.fixture();child=[str(self.root/name) for name in inventory if 'crypto' not in name]
  parent=[str(self.root/name) for name in inventory];m.mapped_receipt(parent,self.root,inventory,required=set())
  with self.assertRaisesRegex(ValueError,'Missing mapped'):m.mapped_receipt(child,self.root,inventory)
 def test_missing_role_rejected(self):
  inventory=self.fixture();paths=[str(self.root/name) for name in inventory if 'crypto' not in name]
  with self.assertRaisesRegex(ValueError,'Missing mapped'):m.mapped_receipt(paths,self.root,inventory)

if __name__=='__main__':unittest.main()
