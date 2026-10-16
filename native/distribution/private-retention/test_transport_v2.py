import importlib.util,json,hashlib,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v2',HERE/'transport_v2.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def row(path,data):return {'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
class Transport(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name).resolve();self.root=self.base/'in';self.root.mkdir();self.out=self.base/'packed'
  files={'candidate.zip':b'fixture zip','stages/collector/receipt.json':b'{ "original" : true }\n','stages/collector/native-bytes/abc':b'repeated','stages/verify/native-bytes/abc':b'repeated'}
  self.rows=[]
  for name,data in files.items():p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);self.rows.append(row(name,data))
  self.inv={'schema':1,'candidate':'candidate.zip','files':self.rows};(self.root/'inventory.json').write_text(json.dumps(self.inv,indent=4)+'\n')
 def pack(self):return v.pack(self.root,self.root/'inventory.json',self.out)
 def alter_manifest(self,change):
  p=self.out/'transport-v2.json';obj=json.loads(p.read_text());change(obj);p.write_bytes(v.encode(obj))
  outer=self.out/'inventory.json';o=json.loads(outer.read_text())
  o['files']=[row('transport-v2.json',p.read_bytes()) if r['path']=='transport-v2.json' else r for r in o['files']];outer.write_bytes(v.encode(o))
 def test_roundtrip_exact_private_dedup(self):
  receipt=self.pack();self.assertEqual(receipt['original_paths'],5);self.assertEqual(receipt['objects'],4)
  dest=self.base/'restored';v.restore(self.out,dest)
  for path in self.root.rglob('*'):
   if path.is_file():self.assertEqual(path.read_bytes(),(dest/path.relative_to(self.root)).read_bytes())
  a=dest/'stages/collector/native-bytes/abc';b=dest/'stages/verify/native-bytes/abc';self.assertEqual(a.stat().st_ino,b.stat().st_ino);self.assertNotEqual(a.stat().st_ino,(self.root/a.relative_to(dest)).stat().st_ino)
  self.assertEqual(dest.stat().st_mode&0o777,0o700)
 def test_tamper_missing_extra_objects(self):
  self.pack();blob=next((self.out/'objects').iterdir());original=blob.read_bytes();blob.write_bytes(b'bad')
  with self.assertRaises(ValueError):v.restore(self.out,self.base/'bad')
  blob.write_bytes(original);extra=self.out/'extra';extra.write_text('bad')
  with self.assertRaises(ValueError):v.restore(self.out,self.base/'bad')
  extra.unlink();blob.unlink()
  with self.assertRaises(ValueError):v.restore(self.out,self.base/'bad')
  self.assertFalse((self.base/'bad').exists())
 def test_manifest_tamper_even_when_outer_rehashed(self):
  self.pack();self.alter_manifest(lambda m:m.update(logical_bytes=m['logical_bytes']+1))
  with self.assertRaisesRegex(ValueError,'totals'):v.restore(self.out,self.base/'bad')
 def test_names_duplicates_traversal_and_parent_collisions(self):
  for bad in ['../x','/x','a\\b','A:stream','a//b','a/./b','x\x00y']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):v.rows_checked([row('candidate.zip',b'x'),row(bad,b'x')],'candidate.zip')
  for paths in [('A','a'),('a','a/b'),('A','a/b')]:
   with self.assertRaises(ValueError):v.rows_checked([row('candidate.zip',b'x'),*[row(p,b'y') for p in paths]],'candidate.zip')
 def test_limits(self):
  for key,value in [('MAX_OBJECTS',1),('LOGICAL_LIMIT',1),('MANIFEST_LIMIT',1),('MAX_PATHS',2)]:
   with mock.patch.object(v,key,value),self.assertRaises(ValueError):self.pack()
   self.assertFalse(self.out.exists())
  with mock.patch.object(v.retain,'LIMIT',1),self.assertRaises(ValueError):self.pack()
 def test_source_symlink_and_mismatch(self):
  p=self.root/'candidate.zip';p.write_bytes(b'wrong')
  with self.assertRaises(ValueError):self.pack()
  p.unlink();p.symlink_to('inventory.json')
  with self.assertRaises(ValueError):self.pack()
 def test_symlink_root_and_ancestor_rejected(self):
  alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
  with self.assertRaisesRegex(ValueError,'symlink input'):v.pack(alias,alias/'inventory.json',self.out)
  parent=self.base/'parent';parent.symlink_to(self.base,target_is_directory=True)
  with self.assertRaisesRegex(ValueError,'symlink input'):v.pack(parent/'in',parent/'in/inventory.json',self.out)
  self.pack();link=self.base/'packed-link';link.symlink_to(self.out,target_is_directory=True)
  with self.assertRaisesRegex(ValueError,'symlink input'):v.restore(link,self.base/'restore')
 def test_duplicate_json_key(self):
  p=self.root/'inventory.json';p.write_text('{"schema":1,"schema":1}')
  with self.assertRaisesRegex(ValueError,'duplicate JSON'):self.pack()
 def test_failed_exposure_cleans_output(self):
  self.pack();dest=self.base/'restore'
  with mock.patch.object(v.Path,'rename',side_effect=OSError('fixture')),self.assertRaises(OSError):v.restore(self.out,dest)
  self.assertFalse(dest.exists());self.assertFalse(list(self.base.glob('.restore-v2-*')))
 def test_unreferenced_object_rejected(self):
  self.pack();self.alter_manifest(lambda m:m['files'].pop())
  with self.assertRaises(ValueError):v.restore(self.out,self.base/'bad')
 def test_actual_gpg_roundtrip(self):
  self.pack();home=self.base/'keys';home.mkdir(mode=0o700)
  try:
   v.retain.gpg(home,'--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Disposable transport fixture','rsa2048','encr','1d')
   listing=v.retain.gpg(home,'--with-colons','--list-keys').stdout.decode();fpr=next(x.split(':')[9] for x in listing.splitlines() if x.startswith('fpr:'));pub=self.base/'pub';pub.write_bytes(v.retain.gpg(home,'--armor','--export',fpr).stdout)
   enc=self.base/'private.gpg';receipt=v.retain.encrypt(self.out,self.out/'inventory.json',pub,fpr,enc);dec=self.base/'decrypted';v.retain.decrypt(enc,receipt['encrypted_sha256'],home,fpr,dec)
   dest=self.base/'restored';v.restore(dec,dest);self.assertEqual((dest/'inventory.json').read_bytes(),(self.root/'inventory.json').read_bytes())
  finally:subprocess.run(['gpgconf','--homedir',str(home),'--kill','all'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

class Chain(unittest.TestCase):
 def test_explicit_prepare_restore_unchanged_chain(self):
  spec=importlib.util.spec_from_file_location('prep_fixture',HERE/'test_prepare_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  f=m.PreparationTests();f.setUp();self.addCleanup(f.doCleanups)
  result=m.p.prepare(f.fixture.archive,f.fixture.inventory,f.stages,{'runtime.json':f.qualification},f.output,True)
  self.assertEqual(result['transport_schema'],2)
  home=f.base/'chain-keys';home.mkdir(mode=0o700)
  try:
   v.retain.gpg(home,'--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Disposable chain transport fixture','rsa2048','encr','1d')
   fpr=next(x.split(':')[9] for x in v.retain.gpg(home,'--with-colons','--list-keys').stdout.decode().splitlines() if x.startswith('fpr:'));pub=f.base/'chain-pub';pub.write_bytes(v.retain.gpg(home,'--armor','--export',fpr).stdout)
   encrypted=f.base/'chain.gpg';receipt=v.retain.encrypt(f.output,f.output/'inventory.json',pub,fpr,encrypted)
   decrypted=f.base/'decrypted';v.retain.decrypt(encrypted,receipt['encrypted_sha256'],home,fpr,decrypted)
  finally:subprocess.run(['gpgconf','--homedir',str(home),'--kill','all'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  dest=f.base/'restored';v.restore(decrypted,dest)
  manifest=json.loads((dest/'chain-manifest.json').read_text());verified=m.p.chain.verify(manifest,dest);self.assertTrue(verified['chain_verified'])
  for p in f.stages.rglob('*'):
   if p.is_file():self.assertEqual(p.read_bytes(),(dest/'stages'/p.relative_to(f.stages)).read_bytes())
if __name__=='__main__':unittest.main(verbosity=2)
