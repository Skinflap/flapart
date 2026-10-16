"""Portable profile restoration regression tests; no native execution."""
import importlib.util,tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
FILE=Path(__file__).with_name('test-relocated.py');spec=importlib.util.spec_from_file_location('relocated',FILE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Profile(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'preferences';self.config.mkdir();self.settings=self.config/'flapartnativerc';self.settings.write_text('original');self.data=self.root/'flapart-native';self.data.mkdir();(self.data/'art.kra').write_bytes(b'original art');self.missing=self.config/'flapartnativedisplayrc';self.paths=[self.settings,self.missing,self.data];self.sentinel=self.config/'kritarc';self.sentinel.write_text('ordinary Krita')
 def generated(self):
  self.settings.write_text('test');self.missing.write_text('test display');self.data.mkdir();(self.data/'test.png').write_bytes(b'test')
 def verify(self):
  self.assertEqual(self.settings.read_text(),'original');self.assertEqual((self.data/'art.kra').read_bytes(),b'original art');self.assertFalse((self.data/'test.png').exists());self.assertFalse(self.missing.exists());self.assertEqual(self.sentinel.read_text(),'ordinary Krita');self.assertFalse(list(self.root.glob('flapart-prior-profile-*')))
 def test_success_and_sequential_runs_restore(self):
  for _ in range(2):
   with m.preserved_profile(self.paths,self.root):self.generated()
   self.verify()
 def test_helper_failure_restores(self):
  with self.assertRaisesRegex(ValueError,'probe failed'):
   with m.preserved_profile(self.paths,self.root):self.generated();raise ValueError('probe failed')
  self.verify()
 def test_setup_failure_restores_already_moved_only(self):
  move=shutil.move
  def failing(src,dst):
   if src==str(self.data):raise OSError('move blocked')
   return move(src,dst)
  with patch.object(m.shutil,'move',failing),self.assertRaisesRegex(OSError,'move blocked'):
   with m.preserved_profile(self.paths,self.root):self.fail('setup should fail')
  self.verify()
 def test_restore_failure_retains_backup_and_restores_other_paths(self):
  move=shutil.move
  def failing(src,dst):
   if dst==str(self.data):raise OSError('restore blocked')
   return move(src,dst)
  with patch.object(m.shutil,'move',failing),self.assertRaisesRegex(RuntimeError,'retained backup'):
   with m.preserved_profile(self.paths,self.root):self.generated()
  self.assertEqual(self.settings.read_text(),'original');backups=list(self.root.glob('flapart-prior-profile-*'));self.assertEqual(len(backups),1);self.assertEqual((backups[0]/'flapart-native/art.kra').read_bytes(),b'original art');self.assertEqual(self.sentinel.read_text(),'ordinary Krita')
 def test_generated_escape_symlink_unlinked_without_touching_target(self):
  outside=self.root/'external';outside.mkdir();(outside/'keep').write_text('keep')
  with m.preserved_profile(self.paths,self.root):self.data.symlink_to(outside,target_is_directory=True)
  self.verify();self.assertEqual((outside/'keep').read_text(),'keep')
 def test_prior_symlink_restored_as_link(self):
  self.settings.unlink();outside=self.root/'external-settings';outside.write_text('original');self.settings.symlink_to(outside)
  with m.preserved_profile(self.paths,self.root):self.generated()
  self.assertTrue(self.settings.is_symlink());self.assertEqual(outside.read_text(),'original');self.verify()
if __name__=='__main__':unittest.main()
