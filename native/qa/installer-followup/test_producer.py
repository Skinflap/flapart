"""Portable producer/launcher contracts using synthetic bytes; no native execution."""
import importlib.util,json,os,stat,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
FILES=[ROOT/'installers'/p/'ci_e2e.py' for p in ('macos-online','windows-online')]
spec=importlib.util.spec_from_file_location('producer',FILES[0]);producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
class ProducerTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.installed=self.root/'installed';self.installed.mkdir();self.executable=self.installed/'krita';self.executable.write_bytes(b'explicit synthetic image');self.digest=producer.sha(self.executable)
 def tearDown(self):self.tmp.cleanup()
 def native(self):
  return {**{k:True for k in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action','action_reopens')},'process_architecture':'arm64','hardware_architecture':'arm64','execution_mode':'native','process_image':{'path':str(self.executable),'sha256':self.digest,'qt_application_file_path':str(self.executable)},'lifecycle':{k:True for k in ('cleanup_started','qa_documents_closed','qt_exit_requested','about_to_quit')},'canvas':[64,64],'round_trip':[64,64,'Draw here'],'round_trip_pixel':[70,110,191,255],'browser_handoff':['https://flaptown.com/flapart/?from=native&destination=profile'],'application_font':'Syne Mono'}
 def check(self,native,arch='arm64'):
  return producer.validate_child(native,arch,'Darwin',self.executable,self.digest)
 def test_copies_identical(self):self.assertEqual(FILES[0].read_bytes(),FILES[1].read_bytes())
 def test_child_identity_and_lifecycle_are_required(self):
  self.assertEqual(self.check(self.native())['process_architecture'],'arm64')
  for key in ('process_image','lifecycle','canvas','process_architecture'):
   n=self.native();n.pop(key)
   with self.subTest(key=key),self.assertRaises(RuntimeError):self.check(n)
 def test_wrong_child_image_or_changed_actual_bytes_refused(self):
  n=self.native();n['process_image']['qt_application_file_path']=str(self.root/'wrong')
  with self.assertRaises(RuntimeError):self.check(n)
  self.executable.write_bytes(b'changed')
  with self.assertRaises(RuntimeError):self.check(self.native())
 def test_rosetta_is_not_relabelled_as_native_intel(self):
  n=self.native();n.update(process_architecture='x86_64',execution_mode='translated')
  self.assertEqual(self.check(n,'x86_64')['execution_mode'],'translated')
  n['hardware_architecture']='x86_64'
  with self.assertRaises(RuntimeError):self.check(n,'x86_64')
 def test_launcher_return_before_actual_child_exit_is_rejected(self):
  if os.name=='nt':self.skipTest('POSIX process liveness fixture')
  child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
  try:
   launcher=subprocess.run([sys.executable,'-c','pass'],check=True)
   self.assertEqual(launcher.returncode,0)
   with self.assertRaisesRegex(RuntimeError,'still running'):producer.require_process_exited(child.pid,'Darwin')
  finally:child.terminate();child.wait(timeout=10)
  producer.require_process_exited(child.pid,'Darwin')
 def test_actual_image_path_mismatch_rejected(self):
  native=self.native();other=self.root/'other-image';other.write_bytes(self.executable.read_bytes());native['process_image']['path']=str(other)
  with self.assertRaisesRegex(RuntimeError,'pinned executable'):self.check(native)
 def test_clean_environment_drops_injection_and_secrets(self):
  with patch.dict(os.environ,{'DYLD_LIBRARY_PATH':'sdk','DYLD_INSERT_LIBRARIES':'inject','PYTHONPATH':'sdk','QT_QPA_PLATFORM_PLUGIN_PATH':'sdk','SECRET_TOKEN':'private','HOME':str(self.root)},clear=True):
   env=producer.clean_environment('Darwin',self.root/'output');self.assertFalse(any(k in env for k in ('DYLD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES','PYTHONPATH','QT_QPA_PLATFORM_PLUGIN_PATH','SECRET_TOKEN')));self.assertEqual(env['PATH'],'/usr/bin:/bin:/usr/sbin:/sbin')
 def archive(self,entries):
  archive=self.root/'payload.zip'
  with zipfile.ZipFile(archive,'w') as z:
   for name,body in entries:z.writestr(name,body)
  return archive
 def test_actual_installed_bytes_checked_not_only_receipt(self):
  archive=self.archive([('krita',self.executable.read_bytes())]);record=producer.installed_inventory(archive,self.installed);self.assertEqual(record['krita']['sha256'],self.digest)
  self.executable.write_bytes(b'mutated')
  with self.assertRaises(RuntimeError):producer.installed_inventory(archive,self.installed)
 def test_unexpected_installed_file_refused(self):
  archive=self.archive([('krita',self.executable.read_bytes())]);(self.installed/'injected.dylib').write_bytes(b'extra')
  with self.assertRaisesRegex(RuntimeError,'Unexpected'):producer.installed_inventory(archive,self.installed)
 def test_unsafe_or_duplicate_archive_member_refused(self):
  for entries in ([('../outside',b'a')],[('krita',b'a'),('KRITA',b'b')]):
   with self.subTest(entries=entries),self.assertRaises(RuntimeError):producer.installed_inventory(self.archive(entries),self.installed)
 def test_runtime_snapshot_detects_bytes_and_links(self):
  tree=self.root/'tree';tree.mkdir();(tree/'actual').write_bytes(b'a');(tree/'alias').symlink_to('actual');before=producer.snapshot([tree]);self.assertEqual(before['0/alias'],{'symlink':'actual'});(tree/'actual').write_bytes(b'b');self.assertNotEqual(producer.snapshot([tree]),before)
  (tree/'alias').unlink();(tree/'alias').symlink_to('../installed/krita')
  with self.assertRaises(RuntimeError):producer.snapshot([tree])
 def test_failure_receipt_written_on_unsupported_host_and_not_overwritten(self):
  if sys.platform!='linux':self.skipTest('Linux-only early host refusal')
  output=self.root/'out';argv=[sys.executable,str(FILES[0]),'--archive',str(self.root/'missing.zip'),'--manifest',str(self.root/'missing.json'),'--probe',str(self.root/'probe'),'--output',str(output),'--archive-sha256','0'*64,'--architecture','arm64']
  result=subprocess.run(argv,capture_output=True);self.assertNotEqual(result.returncode,0)
  receipt=output/'installer-e2e.json';data=json.loads(receipt.read_text());self.assertFalse(data['passed']);self.assertFalse(data['native_execution']);self.assertFalse(data['release_qualified']);self.assertIn('Native Mac or Windows',data['error'])
  before=receipt.read_bytes();subprocess.run(argv,capture_output=True);self.assertEqual(receipt.read_bytes(),before)
 def test_mac_launcher_normal_and_qa_argv(self):
  # Exercise the real launch branch in an isolated shell harness; preceding Mac
  # signature/receipt checks remain native-only and are not bypassed in production.
  source=(ROOT/'installers/macos-online/Flapart Studio.command').read_text();branch=source[source.index('export FLAPART_NATIVE=1'):]
  stub=self.root/'open';stub.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n');stub.chmod(0o755)
  script=self.root/'launch';script.write_text('set -euo pipefail\napp="/fixture/Flapart Studio.app"\n'+branch.replace('/usr/bin/open',str(stub)))
  normal=subprocess.run(['/bin/bash',str(script),'drawing.kra'],capture_output=True,text=True,check=True);self.assertEqual(normal.stdout.splitlines(),['-a','/fixture/Flapart Studio.app','--args','drawing.kra'])
  env={**os.environ,'FLAPART_QA_EXPECT_COMPILED':'1','FLAPART_QA_OUTPUT':str(self.root)}
  for arch in ('arm64','x86_64'):
   run=subprocess.run(['/bin/bash',str(script),'--flapart-qa-architecture',arch],env=env,capture_output=True,text=True,check=True);self.assertEqual(run.stdout.splitlines(),['-n','-W','--arch',arch,'-a','/fixture/Flapart Studio.app'])
  for args in (['--flapart-qa-architecture','i386'],['--flapart-qa-architecture','arm64','extra']):self.assertNotEqual(subprocess.run(['/bin/bash',str(script),*args],env=env,capture_output=True).returncode,0)
  env.pop('FLAPART_QA_EXPECT_COMPILED');self.assertNotEqual(subprocess.run(['/bin/bash',str(script),'--flapart-qa-architecture','arm64'],env=env,capture_output=True).returncode,0)
if __name__=='__main__':unittest.main()
