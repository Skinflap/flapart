"""Exercise only loader environment construction; no simulated native success."""
import ast
import os
import pathlib
import tempfile
import unittest

# The build driver intentionally executes at top level. Load only its pure helper.
source=pathlib.Path(__file__).with_name('build-macos-python.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='sdk_smoke_environment')
namespace={'os':os,'pathlib':pathlib};exec(compile(ast.Module(body=[node],type_ignores=[]),'<helper>','exec'),namespace)
setup=namespace['sdk_smoke_environment']

class SmokeEnvironment(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.sdk=self.root/'sdk/lib';self.site=self.sdk/'Python.framework/Versions/3.13/lib/python3.13/site-packages';self.site.mkdir(parents=True)
  self.new=self.root/'new';self.ssl=self.root/'openssl'
  for path in [self.sdk/'QtCore.framework/Versions/5/QtCore',self.new/'lib/Python.framework/Versions/3.13/Python',self.ssl/'lib/libssl.3.dylib']:
   path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture only')
 def tearDown(self):self.tmp.cleanup()
 def test_exact_priority_and_inherited_overrides_removed(self):
  base={'PATH':'keep','DYLD_INSERT_LIBRARIES':'bad','DYLD_FALLBACK_FRAMEWORK_PATH':'bad','PYTHONHOME':'old','PYTHONPATH':'old'}
  result=setup(base,self.new,self.site,self.ssl)
  self.assertEqual(result['DYLD_FRAMEWORK_PATH'].split(os.pathsep),[str(self.new/'lib'),str(self.sdk)])
  self.assertEqual(result['DYLD_LIBRARY_PATH'].split(os.pathsep),[str(self.ssl/'lib'),str(self.new/'lib'),str(self.sdk)])
  self.assertEqual(result['PATH'],'keep');self.assertEqual(result['PYTHONNOUSERSITE'],'1')
  for key in ('DYLD_INSERT_LIBRARIES','DYLD_FALLBACK_FRAMEWORK_PATH','PYTHONHOME'):self.assertNotIn(key,result)
  self.assertEqual(base['PYTHONPATH'],'old')
 def test_resolved_sdk_alias(self):
  alias=self.root/'site-alias';alias.symlink_to(self.site,target_is_directory=True)
  self.assertEqual(setup({},self.new,alias,self.ssl)['PYTHONPATH'],str(self.site))
 def test_missing_framework_refused(self):
  (self.sdk/'QtCore.framework/Versions/5/QtCore').unlink()
  with self.assertRaisesRegex(ValueError,'QtCore'):setup({},self.new,self.site,self.ssl)
 def test_non_framework_site_refused(self):
  other=self.root/'unrelated-site';other.mkdir()
  with self.assertRaisesRegex(ValueError,'framework-contained'):setup({},self.new,other,self.ssl)
 def test_missing_new_python_refused(self):
  (self.new/'lib/Python.framework/Versions/3.13/Python').unlink()
  with self.assertRaisesRegex(ValueError,'New Python'):setup({},self.new,self.site,self.ssl)

if __name__=='__main__':unittest.main()
