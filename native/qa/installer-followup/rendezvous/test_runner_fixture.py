import importlib.util,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import fixture,protocol as p,runner_fixture as r

spec=importlib.util.spec_from_file_location('runner_retention',r.RETENTION);retain=importlib.util.module_from_spec(spec);spec.loader.exec_module(retain)

@unittest.skipUnless(shutil.which('gpg') and shutil.which('gpgconf'),'GPG required')
class RunnerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.state=self.root/'state.json';self.public=self.root/'public'
  self.binding={'repository':'owner/repo','workflow':'.github/workflows/fixture.yml','run_id':10,'attempt':1,'commit':'a'*40,'job_id':20,'architecture':'arm64','operator_id':30}
  r.prepare(self.binding,self.state,self.public,100);self.obj,self.home=r.check_state(self.state);self.request=self.obj['request']
  self.addCleanup(lambda:r.cleanup(self.state) if self.state.exists() else None)
 def test_prepare_only_public_members_and_fixed_pins(self):
  self.assertEqual({x.name for x in self.public.iterdir()},{'request.json','recipient-public.asc'})
  self.assertFalse(self.home.is_relative_to(self.public));self.assertEqual(self.state.stat().st_mode&0o077,0)
  for k,v in fixture.pins().items():self.assertEqual(self.request['binding'][k],v)
 def test_cleanup_refuses_wrong_marker(self):
  marker=self.home/'.rendezvous-owner';marker.write_text('wrong')
  try:
   with self.assertRaises(ValueError):r.cleanup(self.state)
   self.assertTrue(self.home.exists())
  finally:marker.write_text(self.obj['owner'])
 def test_token_removed_and_absent_from_child_env(self):
  with patch.dict(os.environ,{'FLAPART_GITHUB_TOKEN':'test-secret','GITHUB_TOKEN':'other-secret'}):
   self.assertEqual(r.consume_token('FLAPART_GITHUB_TOKEN'),'test-secret');self.assertNotIn('FLAPART_GITHUB_TOKEN',os.environ)
   env=r.child_environment();self.assertNotIn('GITHUB_TOKEN',env);self.assertNotIn('FLAPART_GITHUB_TOKEN',env)
 def test_expired_failure_receipt_and_cleanup(self):
  result=r.receive(self.state,self.root/'out',object(),clock=lambda:4000)
  self.assertFalse(result['passed']);self.assertFalse(result['native_executed']);self.assertTrue(result['ephemeral_home_removed']);self.assertFalse(self.home.exists())
 def test_nonfixture_request_refused(self):
  value=p.read_metadata(self.state);value['request']['binding']['candidate_sha256']='f'*64;self.state.write_bytes(p.encode(value))
  with self.assertRaises(ValueError):r.receive(self.state,self.root/'out',object(),clock=lambda:200)
  self.assertFalse((self.root/'out').exists())
 def test_actual_harmless_decrypt_after_incomplete_draft_wait(self):
  src=self.root/'src';src.mkdir();paths={}
  for name,data in fixture.payloads().items():paths[name]=src/name;paths[name].write_bytes(data)
  packed=p.pack(self.request,paths,self.root/'pack',200);cipher=self.root/'encrypted.gpg'
  retain.encrypt(packed,packed/'inventory.json',self.public/'recipient-public.asc',self.request['fingerprint'],cipher)
  outer=self
  class Client:
   calls=0
   def json(self,path):
    if '/assets?' in path:
     self.calls+=1
     return [] if self.calls==1 else [{'name':name,'uploader':{'id':30},'size':1024} for name in ('candidate.gpg','response.json')]
    return [{'id':60,'tag_name':r.g.draft_tag(outer.request)}]
  def fetch(client,obj,release,destination,now):
   shutil.copyfile(cipher,destination);return {'response':p.response(obj,destination,50,60,now)}
  sleeps=[]
  with patch.object(r.g,'fetch_response',side_effect=fetch):result=r.receive(self.state,self.root/'out',Client(),clock=lambda:200,sleep=sleeps.append)
  self.assertTrue(result['passed']);self.assertTrue(sleeps);self.assertFalse(result['native_executed']);self.assertFalse(result['release_qualified']);self.assertFalse(self.home.exists())
  for name,data in fixture.payloads().items():self.assertEqual((self.root/'out/recovered'/name).read_bytes(),data)

if __name__=='__main__':unittest.main()
