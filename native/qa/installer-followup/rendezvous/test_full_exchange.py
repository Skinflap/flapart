import copy,shutil,unittest
from pathlib import Path
from unittest.mock import patch
import protocol as p,full_chain as f,response_full as response,coordinator_full as coord,runner_full as runner
import runner_fixture as owned

fixtures=f.candidate.load('exchange_candidate_fixtures',Path(__file__).with_name('test_candidate_runner.py'))
http=f.candidate.load('exchange_http_fixtures',Path(__file__).with_name('test_coordinator_fixture.py'))

@unittest.skipUnless(shutil.which('gpg') and shutil.which('gpgconf'),'GPG required')
class FullExchangeTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.CandidateAdmissionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.base=self.fixture.base;self.root=self.fixture.root;self.manifest=self.fixture.manifest;self.chain=self.fixture.chainsha;self.binding=self.fixture.request['binding']
  self.state=self.base/'runner-state.json';self.public=self.base/'runner-public'
  runner.prepare(self.binding,self.chain,self.state,self.public,100)
  self.addCleanup(lambda:owned.cleanup(self.state) if self.state.exists() else None)
  self.request=p.read_metadata(self.public/'request.json');self.adapter=http.Adapter(self.binding,self.request,(self.public/'recipient-public.asc').read_bytes());self.output=self.base/'coordinator-real'
 def coordinate(self):return coord.coordinate(self.binding,40,self.root,self.manifest,self.chain,self.output,self.adapter,clock=lambda:200)
 def test_actual_crypto_chain_receiver_and_scoped_draft_cleanup(self):
  receipt=self.coordinate();self.assertTrue(receipt['ready']);self.assertFalse(receipt['native_executed']);self.assertEqual([x[0] for x in self.adapter.uploads],['candidate.gpg','response.json'])
  self.adapter.t.obj(self.adapter.base+'/releases?per_page=100',[self.adapter.rel])
  result=runner.receive(self.state,self.chain,40,self.base/'receiver',self.adapter.reader,clock=lambda:200)
  self.assertTrue(result['passed']);self.assertTrue(result['chain_verified']);self.assertFalse(result['native_executed']);self.assertTrue(result['ephemeral_home_removed'])
  self.assertEqual(p.file_digest(self.base/'receiver/admitted/recovered/candidate.zip'),self.binding['candidate_sha256'])
  cleaned=coord.cleanup(self.binding,40,self.chain,self.output/'coordinator-receipt.json',self.adapter);self.assertTrue(cleaned['cleanup_complete']);self.assertEqual(self.adapter.deleted,[(self.binding['repository'],60)])
 def test_starter_response_asset_waits_then_actual_chain_admitted(self):
  self.coordinate();self.adapter.t.obj(self.adapter.base+'/releases?per_page=100',[self.adapter.rel]);original=self.adapter.reader.json;pending=[True];sleeps=[]
  def observed(path):
   rows=original(path)
   if '/assets?' in path and pending[0]:
    rows=copy.deepcopy(rows);next(a for a in rows if a['name']=='response.json').update(state='starter',size=0,digest=None)
   return rows
  def wait(seconds):sleeps.append(seconds);pending[0]=False
  self.adapter.reader.json=observed
  result=runner.receive(self.state,self.chain,40,self.base/'receiver',self.adapter.reader,clock=lambda:200,sleep=wait)
  self.assertEqual(len(sleeps),1);self.assertTrue(result['passed']);self.assertTrue(result['chain_verified']);self.assertTrue(result['ephemeral_home_removed']);self.assertFalse(result['native_executed'])
 def test_incomplete_upload_expires_without_download_and_cleans_key(self):
  self.coordinate();self.adapter.t.obj(self.adapter.base+'/releases?per_page=100',[self.adapter.rel]);original=self.adapter.reader.json;now=[200];sleeps=[]
  def observed(path):
   rows=original(path)
   if '/assets?' in path:
    rows=copy.deepcopy(rows);next(a for a in rows if a['name']=='candidate.gpg').update(state='starter',size=0,digest=None)
   return rows
  def wait(seconds):sleeps.append(seconds);now[0]=self.request['expires']
  self.adapter.reader.json=observed
  with patch.object(response,'fetch',side_effect=AssertionError('must not fetch incomplete upload')) as fetch:
   result=runner.receive(self.state,self.chain,40,self.base/'receiver',self.adapter.reader,clock=lambda:now[0],sleep=wait)
  fetch.assert_not_called();self.assertEqual(len(sleeps),1);self.assertFalse(result['passed']);self.assertTrue(result['ephemeral_home_removed']);self.assertFalse(self.state.exists());self.assertFalse((self.base/'receiver/candidate.gpg').exists())
 def test_wrong_chain_before_any_draft(self):
  with self.assertRaises(ValueError):coord.coordinate(self.binding,40,self.root,self.manifest,'f'*64,self.output,self.adapter,clock=lambda:200)
  self.assertFalse(self.adapter.created)
 def test_wrong_operator_before_any_draft(self):
  self.adapter.operator_id=lambda:31
  with self.assertRaises(ValueError):self.coordinate()
  self.assertFalse(self.adapter.created)
 def test_wrong_attempt_before_any_draft(self):
  self.adapter.run['run_attempt']=2;self.adapter.t.obj(self.adapter.base+'/actions/runs/10',self.adapter.run)
  with self.assertRaises(ValueError):self.coordinate()
  self.assertFalse(self.adapter.created)
 def test_descriptor_changed_in_draft_body_refused(self):
  self.coordinate();value=p.decode(self.adapter.rel['body'].encode());value['descriptor']['payload_bytes']+=1;value['descriptor_sha256']=p.digest(p.encode(value['descriptor']));self.adapter.rel['body']=p.encode(value).decode();self.adapter.sync()
  dest=self.base/'download.gpg'
  with self.assertRaises(ValueError):response.fetch(self.adapter.reader,self.request,self.chain,40,60,dest,200)
  self.assertFalse(dest.exists())
 def test_response_asset_operator_must_match(self):
  self.coordinate();self.adapter.assets[1]['uploader']['id']=31;self.adapter.sync()
  with self.assertRaises(ValueError):response.fetch(self.adapter.reader,self.request,self.chain,40,60,self.base/'download.gpg',200)
 def test_published_release_never_accepted_or_deleted(self):
  self.coordinate();self.adapter.rel['draft']=False;self.adapter.rel['published_at']='today';self.adapter.sync()
  with self.assertRaises(ValueError):response.fetch(self.adapter.reader,self.request,self.chain,40,60,self.base/'download.gpg',200)
  with self.assertRaises(ValueError):coord.cleanup(self.binding,40,self.chain,self.output/'coordinator-receipt.json',self.adapter)
  self.assertFalse(self.adapter.deleted)
 def test_descriptor_request_nonce_replay(self):
  self.coordinate();other=copy.deepcopy(self.request);other['nonce']='e'*64
  with self.assertRaises(ValueError):response.fetch(self.adapter.reader,other,self.chain,40,60,self.base/'download.gpg',200)
 def test_failure_preserves_partial_draft_no_automatic_delete(self):
  def fail(*args):raise RuntimeError('signed-url-private')
  self.adapter.upload=fail
  with self.assertRaises(ValueError) as error:self.coordinate()
  self.assertNotIn('signed-url',str(error.exception));saved=p.read_metadata(self.output/'coordinator-receipt.json');self.assertEqual(saved['release_id'],60);self.assertFalse(saved['ready']);self.assertFalse(self.adapter.deleted)
 def test_unrecorded_asset_cleanup_refused(self):
  self.coordinate();self.adapter.assets.append({'id':999,'name':'foreign'});self.adapter.sync()
  with self.assertRaises(ValueError):coord.cleanup(self.binding,40,self.chain,self.output/'coordinator-receipt.json',self.adapter)
  self.assertFalse(self.adapter.deleted)
 def test_low_disk_download_refusal(self):
  self.coordinate()
  with patch.object(f.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
   with self.assertRaises(ValueError):response.fetch(self.adapter.reader,self.request,self.chain,40,60,self.base/'download.gpg',200)
  self.assertFalse((self.base/'download.gpg').exists())
 def test_receiver_expiry_cleanup_no_native_claim(self):
  result=runner.receive(self.state,self.chain,40,self.base/'receiver',self.adapter.reader,clock=lambda:4000)
  self.assertFalse(result['passed']);self.assertFalse(result['native_executed']);self.assertTrue(result['ephemeral_home_removed'])

if __name__=='__main__':unittest.main()
