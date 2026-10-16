import copy,io,json,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import Mock
import coordinator_fixture as c
import fixture
import github_read as g
import protocol as p
class Transport:
 def __init__(self):self.routes={}
 def get(self,url,headers,limit,sink=None):
  data=self.routes[url];p.require(len(data)<=limit,'fixture bound')
  if sink is not None:sink.write(data);return 200,{},b''
  return 200,{},data
 def obj(self,path,obj):self.routes[g.API+path]=p.encode(obj)
 def data(self,path,data):self.routes[g.API+path]=data
class Adapter:
 def __init__(self,b,q,key):
  self.b=b;self.q=q;self.t=Transport();self.reader=g.Client('fake-session-not-a-secret',self.t);self.created=[];self.uploads=[];self.deleted=[];self.assets=[];self.rel=None;self.base='/repos/'+b['repository']
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('request.json',p.encode(q));z.writestr('recipient-public.asc',key)
  data=out.getvalue()
  self.run={'repository':{'full_name':b['repository']},'id':b['run_id'],'run_attempt':b['attempt'],'head_sha':b['commit'],'path':b['workflow'],'event':'workflow_dispatch','actor':{'id':b['operator_id']},'triggering_actor':{'id':b['operator_id']},'status':'in_progress'}
  self.t.obj(self.base+'/actions/runs/10',self.run);self.t.obj(self.base+'/actions/runs/10/attempts/1/jobs?per_page=100',{'total_count':1,'jobs':[{'id':20,'run_id':10,'name':'installer-arm64','labels':['macos-15'],'status':'in_progress'}]})
  self.t.obj(self.base+'/actions/artifacts/40',{'id':40,'name':g.request_artifact_name(b),'expired':False,'workflow_run':{'id':10,'head_sha':b['commit']},'size_in_bytes':len(data),'digest':'sha256:'+p.digest(data)});self.t.data(self.base+'/actions/artifacts/40/zip',data)
 def operator_id(self):return self.b['operator_id']
 def sync(self):
  self.t.obj(self.base+'/releases/60',self.rel);self.t.obj(self.base+'/releases/60/assets?per_page=100',self.assets)
 def create(self,repo,payload):
  self.created.append(payload);self.rel={**payload,'id':60,'author':{'id':self.b['operator_id']},'published_at':None};self.sync();return copy.deepcopy(self.rel)
 def upload(self,repo,rid,tag,path):
  raw=path.read_bytes();a={'id':70+len(self.assets),'name':path.name,'state':'uploaded','uploader':{'id':self.b['operator_id']},'size':len(raw),'digest':'sha256:'+p.digest(raw)}
  self.assets.append(a);self.uploads.append((path.name,raw));self.t.data(self.base+f"/releases/assets/{a['id']}",raw);self.sync();return a
 def delete(self,repo,rid):self.deleted.append((repo,rid))
class Coordinator(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.home=cls.base/'keys';cls.home.mkdir(mode=0o700)
  c.retention.gpg(cls.home,'--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Disposable coordinator test','rsa2048','encr','1d')
  cls.fpr=next(x.split(':')[9] for x in c.retention.gpg(cls.home,'--with-colons','--list-keys').stdout.decode().splitlines() if x.startswith('fpr:'));cls.key=c.retention.gpg(cls.home,'--armor','--export',cls.fpr).stdout
 @classmethod
 def tearDownClass(cls):
  subprocess.run(['gpgconf','--homedir',str(cls.home),'--kill','all'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);cls.tmp.cleanup()
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=self.base);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.out=self.root/'coordinator'
  self.b={'repository':'fixture/repository','workflow':'.github/workflows/fixture.yml','run_id':10,'attempt':1,'job_id':20,'commit':'a'*40,'architecture':'arm64','operator_id':30,**fixture.pins()}
  self.q=p.request(self.b,self.key,self.fpr,'b'*64,100,1000);self.adapter=Adapter(self.b,self.q,self.key)
 def run_coordinator(self):return c.coordinate(self.b,40,self.out,self.adapter,lambda:200)
 def test_authenticated_fixture_roundtrip_and_scoped_cleanup(self):
  receipt=self.run_coordinator();self.assertTrue(receipt['ready']);self.assertEqual(len(self.adapter.uploads),2)
  recovered=self.root/'recovered';c.retention.decrypt(self.out/'candidate.gpg',p.file_digest(self.out/'candidate.gpg'),self.home,self.fpr,recovered);p.validate_pack(recovered,self.q,200)
  for name,data in fixture.payloads().items():self.assertEqual((recovered/name).read_bytes(),data)
  cleaned=c.cleanup(self.b,40,self.out/'coordinator-receipt.json',self.adapter);self.assertTrue(cleaned['cleanup_complete']);self.assertEqual(self.adapter.deleted,[(self.b['repository'],60)])
 def test_nonfixture_rejected_before_any_action(self):
  self.b['candidate_sha256']='0'*64
  with self.assertRaises(ValueError):self.run_coordinator()
  self.assertFalse(self.out.exists());self.assertFalse(self.adapter.created)
 def test_wrong_authenticated_attempt_no_mutation(self):
  self.adapter.run['run_attempt']=2;self.adapter.t.obj(self.adapter.base+'/actions/runs/10',self.adapter.run)
  with self.assertRaises(ValueError):self.run_coordinator()
  self.assertFalse(self.adapter.created)
 def test_expired_request_no_mutation(self):
  with self.assertRaises(ValueError):c.coordinate(self.b,40,self.out,self.adapter,lambda:1000)
  self.assertFalse(self.adapter.created)
 def test_wrong_operator_no_mutation(self):
  self.adapter.operator_id=lambda:31
  with self.assertRaises(ValueError):self.run_coordinator()
  self.assertFalse(self.adapter.created)
 def test_fingerprint_mismatch_never_creates_draft(self):
  self.q['fingerprint']='C'*40;self.adapter=Adapter(self.b,self.q,self.key)
  with self.assertRaises(ValueError):self.run_coordinator()
  self.assertFalse(self.adapter.created)
 def test_cleanup_rejects_published_foreign_or_unrecorded_asset(self):
  self.run_coordinator();original=copy.deepcopy(self.adapter.rel)
  for patch in [{'draft':False,'published_at':'2026-01-01'}, {'author':{'id':999}},{'target_commitish':'c'*40},{'tag_name':'unrelated'}]:
   self.adapter.rel={**original,**patch};self.adapter.sync()
   with self.assertRaises(ValueError):c.cleanup(self.b,40,self.out/'coordinator-receipt.json',self.adapter)
  self.adapter.rel=original;self.adapter.assets.append({'id':999,'name':'unrelated'});self.adapter.sync()
  with self.assertRaises(ValueError):c.cleanup(self.b,40,self.out/'coordinator-receipt.json',self.adapter)
  self.assertFalse(self.adapter.deleted)
 def test_cleanup_wrong_binding_or_artifact(self):
  self.run_coordinator();wrong={**self.b,'attempt':2}
  for b,artifact in [(wrong,40),(self.b,41)]:
   with self.assertRaises(ValueError):c.cleanup(b,artifact,self.out/'coordinator-receipt.json',self.adapter)
  self.assertFalse(self.adapter.deleted)
 def test_upload_failure_preserves_recorded_draft_without_automatic_delete(self):
  def fail(*args):raise RuntimeError('signedURL and token must stay hidden')
  self.adapter.upload=fail
  with self.assertRaises(ValueError) as error:self.run_coordinator()
  self.assertNotIn('signedURL',str(error.exception));receipt=p.read_metadata(self.out/'coordinator-receipt.json');self.assertEqual(receipt['release_id'],60);self.assertFalse(receipt['ready']);self.assertFalse(self.adapter.deleted)
 def test_gh_adapter_uses_structured_temp_input_and_redacts_failures(self):
  calls=[]
  def run(args,**kwargs):
   calls.append(args)
   if '--input' in args:
    payload=json.loads(Path(args[args.index('--input')+1]).read_text());self.assertEqual(payload,{'draft':True})
   return subprocess.CompletedProcess(args,0,p.encode({'id':60}),b'')
  gh=c.GhAdapter(run);self.assertEqual(gh.create('fixture/repository',{'draft':True}),{'id':60});self.assertFalse(Path(calls[0][-1]).exists())
  bad=c.GhAdapter(lambda *a,**k:subprocess.CompletedProcess(a,1,b'secret',b'signed-url'))
  with self.assertRaises(ValueError) as error:bad.operator_id()
  self.assertNotIn('signed-url',str(error.exception))
if __name__=='__main__':unittest.main(verbosity=2)
