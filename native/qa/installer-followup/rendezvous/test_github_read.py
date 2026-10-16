import copy,io,json,stat,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import protocol as p
import github_read as g
import test_protocol as fixture

class Transport:
 def __init__(self):self.routes={};self.calls=[]
 def get(self,url,headers,limit,sink=None):
  self.calls.append((url,dict(headers),limit));status,head,data=self.routes[url]
  if sink is not None and status==200:
   p.require(len(data)<=limit,'fixture streaming bound');sink.write(data);data=b''
  return status,head,data
 def obj(self,path,obj):self.routes[g.API+path]=(200,{},p.encode(obj))
 def body(self,path,data):self.routes[g.API+path]=(200,{},data)

class AdapterTests(unittest.TestCase):
 response_fixture=fixture.ProtocolTests.response_fixture
 def setUp(self):
  fixture.ProtocolTests.setUp(self);self.t=Transport();self.c=g.Client('fixture-not-a-secret',self.t);self.base='/repos/owner/repo'
 def archive(self,entries=None):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   for name,data in entries or [('request.json',p.encode(self.q)),('recipient-public.asc',self.key)]:z.writestr(name,data)
  return out.getvalue()
 def setup_request(self):
  data=self.archive();b=self.base
  run={'repository':{'full_name':'owner/repo'},'id':10,'run_attempt':1,'head_sha':'a'*40,'path':self.b['workflow'],'event':'workflow_dispatch','actor':{'id':30},'triggering_actor':{'id':30},'status':'in_progress'}
  jobs={'total_count':1,'jobs':[{'id':20,'run_id':10,'name':'installer-arm64','labels':['macos-15'],'status':'in_progress'}]}
  artifact={'id':40,'name':g.request_artifact_name(self.b),'expired':False,'workflow_run':{'id':10,'head_sha':'a'*40},'size_in_bytes':len(data),'digest':'sha256:'+p.digest(data)}
  self.t.obj(b+'/actions/runs/10',run);self.t.obj(b+'/actions/runs/10/attempts/1/jobs?per_page=100',jobs);self.t.obj(b+'/actions/artifacts/40',artifact);self.t.body(b+'/actions/artifacts/40/zip',data)
  return run,jobs,artifact
 def fetch(self):return g.fetch_request(self.c,self.b,40,200)
 def test_api_request_roundtrip(self):
  self.setup_request();self.assertEqual(self.fetch()['request'],self.q)
 def test_api_artifact_archive_tamper(self):
  self.setup_request();self.t.body(self.base+'/actions/artifacts/40/zip',b'changed')
  with self.assertRaises(ValueError):self.fetch()
 def test_api_attempt_job_injection(self):
  _,jobs,_=self.setup_request();jobs['jobs'][0]['name']='installer-x86_64';self.t.obj(self.base+'/actions/runs/10/attempts/1/jobs?per_page=100',jobs)
  with self.assertRaises(ValueError):self.fetch()
 def test_api_wrong_rerun_operator(self):
  run,_,_=self.setup_request();run['triggering_actor']['id']=31;self.t.obj(self.base+'/actions/runs/10',run)
  with self.assertRaises(ValueError):self.fetch()
 def test_api_wrong_actor(self):
  run,_,_=self.setup_request();run['actor']['id']=31;self.t.obj(self.base+'/actions/runs/10',run)
  with self.assertRaises(ValueError):self.fetch()
 def test_archive_unsafe_extra_duplicate(self):
  for entries in ([('../request.json',b'x'),('recipient-public.asc',b'y')],[('request.json',b'x'),('request.json',b'x')],[('request.json',b'x'),('recipient-public.asc',b'y'),('extra',b'z')]):
   with self.assertRaises(ValueError):g.artifact_members(self.archive(entries))
 def test_archive_symlink_and_bomb(self):
  for mode,data in ((stat.S_IFLNK,b'target'),(stat.S_IFREG,b'x'*65537)):
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    entry=zipfile.ZipInfo('request.json');entry.external_attr=(mode|0o600)<<16;z.writestr(entry,data);z.writestr('recipient-public.asc',b'y')
   with self.assertRaises(ValueError):g.artifact_members(out.getvalue())
 def test_redirect_strips_authorization(self):
  path=self.base+'/actions/artifacts/40/zip';signed='https://example.blob.core.windows.net/file?secret=signed'
  self.t.routes[g.API+path]=(302,{'location':signed},b'');self.t.routes[signed]=(200,{},b'data')
  self.assertEqual(self.c.download(path,4),b'data');self.assertIn('Authorization',self.t.calls[0][1]);self.assertNotIn('Authorization',self.t.calls[1][1]);self.assertEqual(self.t.calls[0][1]['Accept'],'application/vnd.github+json')
 def test_redirect_refuses_untrusted_target(self):
  for target in ('http://example.blob.core.windows.net/file','https://evil.test/file','https://api.github.com/repos/x','https://user:pass@x.blob.core.windows.net/a'):
   self.t.routes[g.API+self.base]=(302,{'location':target},b'')
   with self.assertRaises(ValueError):self.c.download(self.base,20)
 def test_transport_errors_redacted(self):
  class Bad:
   def get(self,*args):raise RuntimeError('signed-secret and token')
  with self.assertRaises(ValueError) as ctx:g.Client('secret',Bad()).download(self.base,100)
  self.assertNotIn('signed-secret',str(ctx.exception));self.assertNotIn('secret',repr(g.Client('secret',Bad())))
 def setup_response(self):
  args=self.response_fixture();raw,_,cipher,rel,a,ra,_=args
  self.t.obj(self.base+'/releases/60',{'id':60,'draft':True,'published_at':None,'tag_name':g.draft_tag(self.q),'target_commitish':'a'*40,'author':{'id':30},'body':p.encode({'schema':1,'request_sha256':p.digest(p.encode(self.q))}).decode()})
  assets=[]
  for obs in (a,ra):assets.append({'id':obs['id'],'name':obs['name'],'state':'uploaded','uploader':{'id':30},'size':obs['bytes'],'digest':'sha256:'+obs['sha256']})
  self.t.obj(self.base+'/releases/60/assets?per_page=100',assets);self.t.body(self.base+'/releases/assets/50',cipher.read_bytes());self.t.body(self.base+'/releases/assets/51',raw)
  return assets
 def get_response(self):return g.fetch_response(self.c,self.q,60,self.root/'download.gpg',200)
 def test_api_response_roundtrip(self):
  self.setup_response();result=self.get_response();self.assertEqual(self.t.calls[-1][1]['Accept'],'application/octet-stream');self.assertEqual(result['response']['asset_id'],50);self.assertEqual((self.root/'download.gpg').read_bytes(),(self.root/'fixture.gpg').read_bytes())
 def test_api_response_operator_mismatch(self):
  assets=self.setup_response();assets[0]['uploader']['id']=31;self.t.obj(self.base+'/releases/60/assets?per_page=100',assets)
  with self.assertRaises(ValueError):self.get_response()
  self.assertFalse((self.root/'download.gpg').exists())
 def test_api_cipher_tamper_no_output(self):
  self.setup_response();self.t.body(self.base+'/releases/assets/50',b'altered')
  with self.assertRaises(ValueError):self.get_response()
  self.assertFalse((self.root/'download.gpg').exists())
 def test_api_existing_destination_preserved(self):
  self.setup_response();dest=self.root/'download.gpg';dest.write_bytes(b'prior')
  with self.assertRaises(ValueError):self.get_response()
  self.assertEqual(dest.read_bytes(),b'prior')
 def test_request_expires_during_download(self):
  self.setup_request()
  with patch.object(g.time,'monotonic',side_effect=[0,1000]):
   with self.assertRaises(ValueError):self.fetch()
 def test_response_expires_during_ciphertext_download(self):
  self.setup_response()
  with patch.object(g.time,'monotonic',side_effect=[0,1,1000]):
   with self.assertRaises(ValueError):self.get_response()
  self.assertFalse((self.root/'download.gpg').exists())
 def test_streaming_failure_removes_only_new_partial(self):
  self.setup_response();original=self.t.get
  def fail(url,headers,limit,sink=None):
   if sink is not None:
    sink.write(b'partial');raise RuntimeError('do not expose signed=secret')
   return original(url,headers,limit)
  self.t.get=fail
  with self.assertRaises(ValueError) as ctx:self.get_response()
  self.assertNotIn('signed=secret',str(ctx.exception));self.assertFalse((self.root/'download.gpg').exists())
 def test_api_response_published_draft_refused(self):
  self.setup_response();path=g.API+self.base+'/releases/60';obj=p.decode(self.t.routes[path][2]);obj['draft']=False;self.t.obj(self.base+'/releases/60',obj)
  with self.assertRaises(ValueError):self.get_response()
 def test_api_download_limits(self):
  self.t.body(self.base,b'x'*11)
  with self.assertRaises(ValueError):self.c.download(self.base,10)

if __name__=='__main__':unittest.main()
