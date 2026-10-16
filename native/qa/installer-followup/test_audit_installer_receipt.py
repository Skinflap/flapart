"""Synthetic contract tests only; never claims a native installer ran."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from audit_installer_receipt import audit,GATES

class AuditTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.archive=self.root/'candidate.zip';self.archive.write_bytes(b'explicit synthetic opaque archive')
  self.sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()
  self.child=self.root/'child.json';self.receipt=self.root/'installer.json'
  self.native={'process_architecture':'arm64','hardware_architecture':'arm64','execution_mode':'native'}
  self.data={'passed':True,'native_child_exit_observed':True,**{k:True for k in GATES},**self.native,'payload_sha256':self.sha,'target_platform':'macos-universal2','native_execution':True,'runtime_scope':'installed-runtime','security_approval_automated':False}
  self.write()
 def tearDown(self):self.tmp.cleanup()
 def write(self):
  self.child.write_text(json.dumps(self.native));self.data['native_probe_sha256']=hashlib.sha256(self.child.read_bytes()).hexdigest();self.receipt.write_text(json.dumps(self.data))
 def run_audit(self,arch='arm64'):
  return audit(self.archive,self.sha,self.receipt,self.child,'macos-universal2',arch)
 def test_complete_claims_are_not_release_or_native_execution(self):
  result=self.run_audit();self.assertTrue(result['installer_fields_complete']);self.assertFalse(result['release_qualified']);self.assertFalse(result['native_test_performed_by_auditor']);self.assertFalse(result['source_closure_checked'])
 def test_each_gate_must_be_explicit_not_inferred(self):
  for key in GATES:
   with self.subTest(key=key):
    self.data.pop(key);self.write();self.assertIn('installer.'+key,self.run_audit()['gaps']);self.data[key]=True
 def test_current_producer_shape_cannot_be_promoted(self):
  for key in ('target_platform','runtime_scope','native_execution','process_architecture','hardware_architecture','execution_mode','failed_upgrade_preserved_artwork_and_settings'):self.data.pop(key)
  self.write();result=self.run_audit();self.assertFalse(result['installer_fields_complete']);self.assertGreaterEqual(len(result['gaps']),7)
 def test_actual_child_architecture_cannot_be_replaced_by_requested(self):
  result=self.run_audit('x86_64');self.assertIn('child.process_architecture',result['gaps'])
 def test_translated_child_is_explicit(self):
  self.native.update(process_architecture='x86_64',execution_mode='translated');self.data.update(self.native);self.write();self.assertTrue(self.run_audit('x86_64')['installer_fields_complete'])
  self.data['hardware_architecture']='x86_64';self.write();self.assertFalse(self.run_audit('x86_64')['installer_fields_complete'])
 def test_changed_child_payload_and_failed_child_rejected(self):
  self.child.write_text(json.dumps({**self.native,'error':'native failure'}));gaps=self.run_audit()['gaps'];self.assertIn('child.failure_absent',gaps);self.assertIn('installer.native_probe_sha256',gaps)
 def test_receipt_mismatched_archive_and_scope_rejected(self):
  self.data.update(payload_sha256='0'*64,runtime_scope='relocated-package');self.write();gaps=self.run_audit()['gaps'];self.assertIn('installer.payload_sha256',gaps);self.assertIn('installer.runtime_scope',gaps)
 def test_changed_actual_archive_rejected(self):
  self.archive.write_bytes(b'changed');
  with self.assertRaisesRegex(ValueError,'differs'):self.run_audit()
 def test_symlink_input_rejected(self):
  target=self.archive.with_suffix('.original');self.archive.rename(target);self.archive.symlink_to(target)
  with self.assertRaisesRegex(ValueError,'symlink'):self.run_audit()
 def test_security_approval_must_not_be_automated(self):
  self.data['security_approval_automated']=True;self.write();self.assertIn('installer.security_approval_automated',self.run_audit()['gaps'])
if __name__=='__main__':unittest.main()
