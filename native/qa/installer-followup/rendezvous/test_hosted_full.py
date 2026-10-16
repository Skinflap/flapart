import copy,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import hosted_full as h
import protocol as p
try:import yaml
except ImportError:yaml=None

class HostedContracts(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name).resolve()
  self.env={'GITHUB_ACTIONS':'true','CI':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REPOSITORY':'owner/repo','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_REF':'owner/repo/'+h.WORKFLOW+'@refs/heads/main','GITHUB_RUN_ID':'10','GITHUB_RUN_ATTEMPT':'1','GITHUB_ACTOR_ID':'30','FLAPART_ARCHITECTURE':'arm64','FLAPART_CANDIDATE_SHA256':'b'*64,'FLAPART_CANDIDATE_BYTES':'200','FLAPART_INVENTORY_SHA256':'c'*64,'FLAPART_MANIFEST_SHA256':'d'*64,'FLAPART_CHAIN_SHA256':'e'*64,'FLAPART_REQUEST_ARTIFACT_ID':'40'}
 def client(self):
  ctx=h.context(self.env)
  run={'id':10,'run_attempt':1,'head_sha':'a'*40,'path':h.WORKFLOW,'event':'workflow_dispatch','status':'in_progress','repository':{'full_name':'owner/repo'},'actor':{'id':30},'triggering_actor':{'id':30}}
  jobs={'total_count':1,'jobs':[{'id':20,'run_id':10,'name':'installer-arm64','status':'in_progress','labels':['macos-15']}]}
  class Client:
   def json(self,path):return jobs if '/jobs?' in path else run
  return Client(),run,jobs
 def test_authenticated_binding(self):
  client,_,_=self.client();b=h.authenticate_binding(h.context(self.env),client);self.assertEqual(b['job_id'],20);self.assertEqual(b['candidate_sha256'],'b'*64);self.assertNotIn('chain_manifest_sha256',b)
 def test_wrong_attempt_actor_job_or_commit(self):
  for target,key,value in [('run','run_attempt',2),('run','head_sha','f'*40),('run','triggering_actor',{'id':31}),('job','name','installer-x86_64'),('job','labels',['macos-15-intel'])]:
   client,run,jobs=self.client();(run if target=='run' else jobs['jobs'][0])[key]=value
   with self.subTest(key=key):
    with self.assertRaises(ValueError):h.authenticate_binding(h.context(self.env),client)
 def test_inputs_reject_shell_text_and_oversize(self):
  for name,value in [('FLAPART_CANDIDATE_BYTES','$(touch nope)'),('FLAPART_CANDIDATE_BYTES',str(p.LIMIT+1)),('FLAPART_CHAIN_SHA256','a'*64+';anything'),('FLAPART_ARCHITECTURE','arm64;anything'),('GITHUB_EVENT_NAME','pull_request'),('GITHUB_WORKFLOW_REF','owner/repo/.github/workflows/other.yml@refs/heads/main')]:
   env={**self.env,name:value}
   with self.subTest(name=name):
    with self.assertRaises(ValueError):h.context(env)
 def test_real_git_committed_helper_binding(self):
  repo=self.base/'checkout';repo.mkdir();subprocess.run(['git','init','-q',str(repo)],check=True)
  helper=repo/'helper.py';helper.write_bytes(b'print("fixture")\n');subprocess.run(['git','-C',str(repo),'add','helper.py'],check=True)
  subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture'],check=True)
  commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip();pins=h.verify_committed(repo,commit,[helper]);self.assertEqual(pins['helper.py'],p.file_digest(helper))
  helper.write_bytes(b'changed')
  with self.assertRaises(ValueError):h.verify_committed(repo,commit,[helper])
 def test_selected_json_excludes_artwork_keys_and_recovered_tree(self):
  root=self.base/'run';root.mkdir();(root/'receiver/admitted/recovered').mkdir(parents=True);(root/'receiver/admitted/recovered/secret.json').write_text('{"do_not_upload":true}')
  (root/'artwork.png').write_bytes(b'private picture');(root/'private-state.json').write_text('{"do_not_upload":true}');(root/'hosted-result.json').write_bytes(p.encode({'passed':False,'native_executed':False,'release_qualified':False}))
  result=h.collect(root);self.assertEqual(result['selected_files'],1);self.assertEqual({x.name for x in (root/'selected-json').iterdir()},{'hosted-result.json','selection.json'})
 def test_selected_json_bounds_and_symlinks_refused(self):
  for mode in ('size','symlink'):
   root=self.base/mode;root.mkdir();path=root/'hosted-result.json'
   if mode=='size':path.write_bytes(b' '*(h.MAX_RECEIPT+1))
   else:path.symlink_to(self.base/'outside');(self.base/'outside').write_text('{}')
   with self.assertRaises(ValueError):h.collect(root)
   self.assertFalse((root/'selected-json').exists())
 def test_failed_admission_never_invokes_installer(self):
  root=self.base/'run';root.mkdir();client,_,_=self.client();ctx=h.context(self.env);binding=h.authenticate_binding(ctx,client)
  h.save(root,'session.json',{'schema':1,'context':ctx,'binding':binding,'helper_pins':{},'committed_helpers':{}})
  with patch.object(h,'checkout_inputs',return_value=({},{})),patch.object(h.runner_full,'receive',return_value={'passed':False,'chain_verified':False}),patch.object(h.candidate,'run_installer') as native:
   result=h.run(root,self.base,self.env,client)
  native.assert_not_called();self.assertFalse(result['passed']);self.assertFalse(result['native_executed']);self.assertFalse(result['release_qualified'])
 def test_session_pin_change_refused_before_receiver(self):
  root=self.base/'run';root.mkdir();ctx=h.context(self.env);ctx['candidate_sha256']='f'*64;h.save(root,'session.json',{'schema':1,'context':ctx})
  with patch.object(h.runner_full,'receive') as receive:
   with self.assertRaises(ValueError):h.run(root,self.base,self.env,object())
  receive.assert_not_called()
 def test_cleanup_without_owned_state_is_noop(self):
  root=self.base/'not-created';self.assertFalse(h.cleanup(root)['ephemeral_state_present']);self.assertFalse(root.exists())

class DraftWorkflowTests(unittest.TestCase):
 def setUp(self):self.path=Path(__file__).resolve().parents[3]/'ci/drafts/native-installer-full-chain.yml';self.text=self.path.read_text()
 @unittest.skipUnless(yaml,'PyYAML used for review-only schema check')
 def test_manual_schema_inputs_matrix_cleanup_and_artifacts(self):
  value=yaml.load(self.text,Loader=yaml.BaseLoader);self.assertEqual(set(value['on']),{'workflow_dispatch'});self.assertEqual(set(value['on']['workflow_dispatch']['inputs']),{'candidate_sha256','candidate_bytes','inventory_sha256','manifest_sha256','chain_sha256'})
  job=value['jobs']['installer'];self.assertEqual({x['architecture']:x['runner'] for x in job['strategy']['matrix']['include']},{'arm64':'macos-15','x86_64':'macos-15-intel'});self.assertEqual(job['strategy']['fail-fast'],'false')
  steps=job['steps'];cleanup=next(s for s in steps if 'Always remove' in s.get('name',''));self.assertEqual(cleanup['if'],'always()')
  artifacts=[s for s in steps if s.get('uses','').startswith('actions/upload-artifact@')];self.assertEqual(len(artifacts),2)
  self.assertEqual(artifacts[0]['id'],'request');self.assertEqual(len(artifacts[0]['with']['path'].splitlines()),2)
  self.assertTrue(artifacts[1]['with']['path'].endswith('/selected-json/*.json'));self.assertNotIn('receiver',artifacts[1]['with']['path'])
  for step in steps:
   if 'uses' in step:self.assertRegex(step['uses'],r'@[0-9a-f]{40}$')
 @unittest.skipUnless(yaml,'PyYAML used for review-only shell extraction')
 def test_all_shell_blocks_parse_and_inputs_are_not_interpolated_into_code(self):
  value=yaml.load(self.text,Loader=yaml.BaseLoader)
  for step in value['jobs']['installer']['steps']:
   if 'run' not in step:continue
   self.assertNotIn('${{',step['run']);subprocess.run(['bash','-n'],input=step['run'].encode(),check=True)

if __name__=='__main__':unittest.main()
