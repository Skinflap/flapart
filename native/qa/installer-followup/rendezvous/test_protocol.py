import copy,json,tempfile,unittest
from pathlib import Path
import protocol as p

class ProtocolTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.src=self.root/'inputs';self.src.mkdir()
  self.data={name:(b'PK\x03\x04exact candidate bytes' if name.endswith('.zip') else p.encode({'fixture':name})) for name in p.FILES}
  self.paths={name:self.src/name for name in p.FILES}
  for name,path in self.paths.items():path.write_bytes(self.data[name])
  self.b={'repository':'owner/repo','workflow':'.github/workflows/followup.yml','run_id':10,'attempt':1,'commit':'a'*40,'job_id':20,'architecture':'arm64','operator_id':30,'candidate_sha256':p.digest(self.data[p.FILES[0]]),'candidate_bytes':len(self.data[p.FILES[0]]),'inventory_sha256':p.digest(self.data[p.FILES[1]]),'manifest_sha256':p.digest(self.data[p.FILES[2]])}
  self.key=b'public fixture bytes; not a real key';self.q=p.request(self.b,self.key,'B'*40,'c'*64,100,1000)
  self.run={'repository':'owner/repo','id':10,'attempt':1,'head_sha':'a'*40,'workflow':self.b['workflow'],'event':'workflow_dispatch','actor_id':30,'status':'in_progress'}
  self.job={'id':20,'run_id':10,'attempt':1,'architecture':'arm64','status':'in_progress'}
  self.artifact={'id':40,'run_id':10,'request_sha256':p.digest(p.encode(self.q)),'key_sha256':p.digest(self.key),'expired':False}
 def auth(self):return p.authenticate_request(p.encode(self.q),self.key,self.b,self.run,self.job,self.artifact,200)
 def packed(self):return p.pack(self.q,self.paths,self.root/'pack',200)
 def test_exact_roundtrip(self):
  self.assertEqual(self.auth(),self.q);root=self.packed();p.validate_pack(root,self.q,200)
  for name,data in self.data.items():self.assertEqual((root/name).read_bytes(),data)
  self.assertFalse(p.decode((root/'exchange.json').read_bytes())['native_executed'])
 def test_authenticated_run_fields(self):
  for key in self.run:
   with self.subTest(key=key):
    original=self.run[key];self.run[key]='wrong'
    with self.assertRaises(ValueError):self.auth()
    self.run[key]=original
 def test_job_attempt_and_architecture(self):
  for key in self.job:
   original=self.job[key];self.job[key]='wrong'
   with self.assertRaises(ValueError):self.auth()
   self.job[key]=original
 def test_key_tamper(self):
  self.key+=b'!'
  with self.assertRaises(ValueError):self.auth()
 def test_artifact_identity(self):
  self.artifact['run_id']=11
  with self.assertRaises(ValueError):self.auth()
 def test_dispatch_candidate_pin(self):
  expected=copy.deepcopy(self.b);expected['candidate_sha256']='f'*64
  with self.assertRaises(ValueError):p.authenticate_request(p.encode(self.q),self.key,expected,self.run,self.job,self.artifact,200)
 def test_expiry_future_and_boolean(self):
  for now in (99,1000,True):
   with self.assertRaises(ValueError):p.check_request(self.q,now)
 def test_duplicate_json(self):
  with self.assertRaises(ValueError):p.decode(b'{"schema":1,"schema":1}')
 def test_mutated_candidate(self):
  root=self.packed();(root/'candidate.zip').write_bytes(b'changed')
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_recomputed_inventory_does_not_override_pins(self):
  root=self.packed();path=root/'candidate.zip';path.write_bytes(b'changed');inv=p.decode((root/'inventory.json').read_bytes())
  row=next(r for r in inv['files'] if r['path']=='candidate.zip');row.update(bytes=7,sha256=p.file_digest(path));(root/'inventory.json').write_bytes(p.encode(inv))
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_replayed_nonce(self):
  root=self.packed();other=copy.deepcopy(self.q);other['nonce']='d'*64
  with self.assertRaises(ValueError):p.validate_pack(root,other,200)
 def test_symlink(self):
  root=self.packed();path=root/'candidate.zip';path.unlink();path.symlink_to(self.paths['candidate.zip'])
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_extra_and_missing_files(self):
  root=self.packed();(root/'unexpected').write_bytes(b'no')
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
  (root/'unexpected').unlink();(root/'candidate.zip').unlink()
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_no_overwrite(self):
  self.packed()
  with self.assertRaises(ValueError):self.packed()
 def test_no_input_overlap(self):
  with self.assertRaises(ValueError):p.pack(self.q,self.paths,self.src/'output',200)
 def test_input_wrong_pin_leaves_no_output(self):
  self.paths['candidate.zip'].write_bytes(b'bad')
  with self.assertRaises(ValueError):self.packed()
  self.assertFalse((self.root/'pack').exists())
 def test_changed_exchange_outcome_rejected(self):
  root=self.packed();path=root/'exchange.json';obj=p.decode(path.read_bytes());obj['native_executed']=True;path.write_bytes(p.encode(obj))
  inv=p.decode((root/'inventory.json').read_bytes());row=next(r for r in inv['files'] if r['path']=='exchange.json');row.update(bytes=path.stat().st_size,sha256=p.file_digest(path));(root/'inventory.json').write_bytes(p.encode(inv))
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_metadata_limit(self):
  root=self.packed();(root/'inventory.json').write_bytes(b' '*65537)
  with self.assertRaises(ValueError):p.validate_pack(root,self.q,200)
 def test_boolean_schema_rejected(self):
  q=copy.deepcopy(self.q);q['schema']=True
  with self.assertRaises(ValueError):p.check_request(q,200)
 def test_parent_symlink_rejected(self):
  link=self.root/'alias';link.symlink_to(self.src,target_is_directory=True)
  inputs={name:link/name for name in p.FILES}
  with self.assertRaises(ValueError):p.pack(self.q,inputs,self.root/'pack',200)
 def response_fixture(self):
  cipher=self.root/'fixture.gpg';cipher.write_bytes(b'opaque ciphertext fixture, not encryption')
  r=p.response(self.q,cipher,50,60,200);raw=p.encode(r)
  release={'id':60,'draft':True,'published_at':None,'author_id':30,'target_commitish':'a'*40,'request_sha256':p.digest(p.encode(self.q))}
  asset={'id':50,'release_id':60,'name':'candidate.gpg','uploader_id':30,'state':'uploaded','bytes':cipher.stat().st_size,'sha256':p.file_digest(cipher)}
  response_asset={'id':51,'release_id':60,'name':'response.json','uploader_id':30,'state':'uploaded','bytes':len(raw),'sha256':p.digest(raw)}
  return [raw,self.q,cipher,release,asset,response_asset,200]
 def test_response_roundtrip(self):
  args=self.response_fixture();self.assertEqual(p.validate_response(*args)['asset_id'],50)
 def test_response_authenticated_identity_tamper(self):
  for index in (3,4,5):
   for key in self.response_fixture()[index]:
    with self.subTest(index=index,key=key):
     args=self.response_fixture();args[index][key]='wrong'
     with self.assertRaises(ValueError):p.validate_response(*args)
 def test_response_ciphertext_tamper(self):
  args=self.response_fixture();args[2].write_bytes(b'altered')
  with self.assertRaises(ValueError):p.validate_response(*args)
 def test_response_replay(self):
  args=self.response_fixture();args[1]=copy.deepcopy(self.q);args[1]['nonce']='d'*64
  with self.assertRaises(ValueError):p.validate_response(*args)

if __name__=='__main__':unittest.main()
