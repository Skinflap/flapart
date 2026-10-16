import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import candidate_runner as c
import protocol as p

fixture_module=c.load('actual_preparation_fixture',c.NATIVE/'distribution/private-retention/test_prepare_candidate.py')

class CandidateAdmissionTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixture_module.PreparationTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.fixture.prepare()
  self.root=self.fixture.output;self.base=self.fixture.base;self.cipher=self.base/'cipher.gpg';self.cipher.write_bytes(b'opaque fixture transport, not GPG authentication')
  self.manifest=self.base/'installer-original.json';self.manifest.write_bytes(p.encode({'sha256':p.file_digest(self.root/'candidate.zip'),'platform':'macos-universal2','kind':'namespaced-compiled-fork','profileNamespace':'flapart-native','status':'ci-candidate'}))
  b={'repository':'owner/repo','workflow':'.github/workflows/native-followup.yml','run_id':10,'attempt':1,'commit':'a'*40,'job_id':20,'architecture':'arm64','operator_id':30,'candidate_sha256':p.file_digest(self.root/'candidate.zip'),'candidate_bytes':(self.root/'candidate.zip').stat().st_size,'inventory_sha256':p.file_digest(self.root/'candidate-inventory.json'),'manifest_sha256':p.file_digest(self.manifest)}
  self.request=p.request(b,b'public fixture','B'*40,'c'*64,100,1000);self.chainsha=p.file_digest(self.root/'chain-manifest.json')
 def admit(self):return c.admit(self.root,self.request,self.manifest,self.chainsha,self.cipher,p.file_digest(self.cipher),200)
 def rehash_retention(self,path):
  inv=c.transport.read(self.root/'inventory.json',c.transport.MANIFEST_LIMIT);name=path.relative_to(self.root).as_posix();row=next(r for r in inv['files'] if r['path']==name);row.update(bytes=path.stat().st_size,sha256=p.file_digest(path));(self.root/'inventory.json').write_bytes(p.encode(inv))
 def test_actual_recorded_stage_chain_admission(self):
  before=p.file_digest(self.root/'candidate.zip');result=self.admit();self.assertTrue(result['admitted']);self.assertTrue(result['chain_verified']);self.assertFalse(result['native_executed']);self.assertFalse(result['release_qualified']);self.assertEqual(before,p.file_digest(self.root/'candidate.zip'))
  self.assertGreater(result['required_free_bytes_before_installer'],3*result['expanded_archive_bytes'])
 def test_changed_blob_even_with_updated_retention_inventory(self):
  path=next((self.root/'stages/codesign/native-bytes').iterdir());path.write_bytes(path.read_bytes()+b'tamper');self.rehash_retention(path)
  with self.assertRaises(ValueError):self.admit()
 def test_missing_stage_receipt(self):
  (self.root/'stages/verify/receipt.json').unlink()
  with self.assertRaises(ValueError):self.admit()
 def test_altered_chain_pin(self):
  cm=self.root/'chain-manifest.json';obj=p.decode(cm.read_bytes());obj['tree']='alternate';cm.write_bytes(p.encode(obj));self.rehash_retention(cm)
  with self.assertRaises(ValueError):self.admit()
 def test_archive_changed_even_with_updated_retention_inventory(self):
  path=self.root/'candidate.zip';path.write_bytes(path.read_bytes()+b'tamper');self.rehash_retention(path)
  with self.assertRaises(ValueError):self.admit()
 def test_installer_manifest_must_be_original_unqualified(self):
  obj=p.decode(self.manifest.read_bytes());obj['status']='qualified';self.manifest.write_bytes(p.encode(obj));self.request['binding']['manifest_sha256']=p.file_digest(self.manifest)
  with self.assertRaises(ValueError):self.admit()
 def test_unlisted_extra_file(self):
  (self.root/'extra').write_bytes(b'extra')
  with self.assertRaises(ValueError):self.admit()
 def test_symlink_file(self):
  path=self.root/'candidate.zip';path.rename(self.base/'outside.zip');path.symlink_to(self.base/'outside.zip')
  with self.assertRaises(ValueError):self.admit()
 def test_expiry_during_chain_check(self):
  with patch.object(c.time,'monotonic',side_effect=[0,1000]):
   with self.assertRaises(ValueError):self.admit()
 def test_small_cipher_limit_refuses_before_chain(self):
  with patch.object(p,'LIMIT',2):
   with self.assertRaises(ValueError):self.admit()
 def test_concrete_launcher_plan_pins_helpers_without_running(self):
  installer=self.base/'installer';installer.mkdir();probe=self.base/'probe';(probe/'flapart_probe').mkdir(parents=True)
  for path in (installer/'ci_e2e.py',installer/'Install Flapart.command',installer/'Flapart Studio.command',probe/'flapart_probe.desktop',probe/'flapart_probe/__init__.py'):path.write_text('harmless fixture')
  pins=c.helper_inputs(installer,probe);out=self.base/'result';result=c.installer_plan(self.root,self.request,self.manifest,installer,probe,out,pins)
  self.assertEqual(result['argv'][result['argv'].index('--archive')+1],str(self.root/'candidate.zip'));self.assertFalse(result['native_executed']);self.assertFalse(out.exists())
  (installer/'ci_e2e.py').write_text('changed')
  with self.assertRaises(ValueError):c.installer_plan(self.root,self.request,self.manifest,installer,probe,out,pins)
 def test_host_gate_prevents_portable_native_claim(self):
  with patch.object(c.platform,'system',return_value='Linux'):
   with self.assertRaises(ValueError):c.run_installer(None,None,None,None,None,None,None,None,None,None)

if __name__=='__main__':unittest.main()
