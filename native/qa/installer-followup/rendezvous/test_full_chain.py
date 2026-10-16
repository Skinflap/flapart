import copy,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import full_chain as f
import protocol as p

fixtures=f.candidate.load('full_chain_actual_fixture',Path(__file__).with_name('test_candidate_runner.py'))

@unittest.skipUnless(shutil.which('gpg') and shutil.which('gpgconf'),'GPG required')
class CompleteEnvelopeTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.CandidateAdmissionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.base=self.fixture.base;self.root=self.fixture.root;self.manifest=self.fixture.manifest;self.chain=self.fixture.chainsha
  self.temp=tempfile.TemporaryDirectory(prefix='fcg-',dir=Path('/tmp').resolve());self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)/'g';self.home.mkdir(mode=0o700)
  self.ret=f.retention();self.ret.gpg(self.home,'--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Harmless full-chain test','rsa2048','encr','1d')
  self.addCleanup(lambda:__import__('subprocess').run(['gpgconf','--homedir',str(self.home),'--kill','all'],stdout=__import__('subprocess').DEVNULL,stderr=__import__('subprocess').DEVNULL))
  listing=self.ret.gpg(self.home,'--with-colons','--list-keys').stdout.decode();fingerprint=next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
  self.public=self.base/'public.asc';self.public.write_bytes(self.ret.gpg(self.home,'--armor','--export',fingerprint).stdout)
  self.request=p.request(self.fixture.request['binding'],self.public.read_bytes(),fingerprint,'c'*64,100,1000)
  self.envelope=self.base/'full-envelope';self.cipher=self.base/'full.gpg';self.output=self.base/'restored-full'
 def packed(self):return f.pack(self.root,self.manifest,self.request,self.chain,self.envelope,200)
 def encrypted(self):
  self.packed();return f.encrypt(self.envelope,self.request,self.chain,self.public,self.cipher,200)
 def restore(self,d):return f.decrypt_restore_admit(self.cipher,self.home,self.request,self.chain,d,p.digest(p.encode(d)),self.output,200)
 def test_actual_encrypt_decrypt_restore_chain_admission(self):
  original=p.file_digest(self.root/'candidate.zip');d=self.encrypted();result=self.restore(d)
  self.assertTrue(result['chain_verified']);self.assertFalse(result['native_executed']);self.assertFalse(result['release_qualified']);self.assertFalse(result['source_closure_complete'])
  self.assertEqual(p.file_digest(self.output/'recovered/candidate.zip'),original);self.assertEqual((self.output/'envelope/installer-original.json').read_bytes(),self.manifest.read_bytes())
  self.assertEqual(p.file_digest(self.output/'recovered/chain-manifest.json'),self.chain)
 def test_incomplete_chain_rejected_before_pack(self):
  (self.root/'stages/verify/receipt.json').unlink()
  with self.assertRaises(ValueError):self.packed()
  self.assertFalse(self.envelope.exists())
 def test_original_chain_wrong_independent_pin(self):
  self.chain='f'*64
  with self.assertRaises(ValueError):self.packed()
 def test_mutated_envelope_object(self):
  self.packed();blob=next((self.envelope/'retained/objects').iterdir());blob.write_bytes(blob.read_bytes()+b'changed')
  with self.assertRaises(ValueError):f.encrypt(self.envelope,self.request,self.chain,self.public,self.cipher,200)
  self.assertFalse(self.cipher.exists())
 def test_descriptor_wrong_identity_even_with_new_descriptor_hash(self):
  d=self.encrypted();d['chain_manifest_sha256']='f'*64
  with self.assertRaises(ValueError):self.restore(d)
  self.assertFalse(self.output.exists())
 def test_ciphertext_corruption_with_recomputed_outer_pin(self):
  d=self.encrypted();data=bytearray(self.cipher.read_bytes());data[len(data)//2]^=1;self.cipher.write_bytes(data);d['ciphertext_sha256']=p.file_digest(self.cipher)
  with self.assertRaises(ValueError):self.restore(d)
  self.assertFalse(self.output.exists())
 def test_independent_descriptor_pin_refuses_metadata_change(self):
  d=self.encrypted();pin=p.digest(p.encode(d));d['payload_bytes']+=1
  with self.assertRaises(ValueError):f.decrypt_restore_admit(self.cipher,self.home,self.request,self.chain,d,pin,self.output,200)
 def test_low_disk_before_decrypt_no_output(self):
  d=self.encrypted()
  with patch.object(f.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
   with self.assertRaises(ValueError):self.restore(d)
  self.assertFalse(self.output.exists())
 def test_expired_request(self):
  d=self.encrypted()
  with self.assertRaises(ValueError):f.decrypt_restore_admit(self.cipher,self.home,self.request,self.chain,d,p.digest(p.encode(d)),self.output,1000)
  self.assertFalse(self.output.exists())
 def test_ciphertext_limit_preserved(self):
  self.packed()
  with patch.object(p,'LIMIT',2):
   with self.assertRaises(ValueError):f.encrypt(self.envelope,self.request,self.chain,self.public,self.cipher,200)
  self.assertFalse(self.cipher.exists())
 def test_symlink_metadata_refused(self):
  self.packed();path=self.envelope/'exchange.json';path.rename(self.base/'exchange-original');path.symlink_to(self.base/'exchange-original')
  with self.assertRaises(ValueError):f.validate_envelope(self.envelope,self.request,self.chain,200)
 def test_selfconsistent_malicious_transport_metadata_refused_before_encrypt(self):
  self.packed();meta=self.envelope/'retained/transport-v2.json';value=f.transport.read(meta,f.transport.MANIFEST_LIMIT);value['files'][0]['path']='../escape';meta.write_bytes(p.encode(value))
  nested_path=self.envelope/'retained/inventory.json';nested=f.transport.read(nested_path,2*1024**2)
  row=next(r for r in nested['files'] if r['path']=='transport-v2.json');row.update(bytes=meta.stat().st_size,sha256=p.file_digest(meta));nested_path.write_bytes(p.encode(nested))
  outer_path=self.envelope/'inventory.json';outer=f.transport.read(outer_path,2*1024**2)
  for name in ('retained/transport-v2.json','retained/inventory.json'):
   row=next(r for r in outer['files'] if r['path']==name);path=self.envelope/name;row.update(bytes=path.stat().st_size,sha256=p.file_digest(path))
  outer_path.write_bytes(p.encode(outer))
  with self.assertRaises(ValueError):f.encrypt(self.envelope,self.request,self.chain,self.public,self.cipher,200)
  self.assertFalse(self.cipher.exists());self.assertFalse((self.base/'escape').exists())
 def test_no_existing_destination_replacement(self):
  d=self.encrypted();self.output.mkdir();(self.output/'keep').write_bytes(b'prior')
  with self.assertRaises(ValueError):self.restore(d)
  self.assertEqual((self.output/'keep').read_bytes(),b'prior')
 def test_descriptor_rejects_malformed_types(self):
  d=self.encrypted()
  for field,value in [('files',True),('payload_bytes',-1),('ciphertext_bytes',p.LIMIT+1),('schema',True)]:
   changed=dict(d);changed[field]=value
   with self.subTest(field=field):
    with self.assertRaises(ValueError):self.restore(changed)

if __name__=='__main__':unittest.main()
