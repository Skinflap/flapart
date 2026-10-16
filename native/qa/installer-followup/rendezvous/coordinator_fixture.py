#!/usr/bin/env python3
"""Explicit harmless-fixture coordinator. No native candidate or long-lived key access.

coordinate --binding <independently pinned binding.json> --artifact-id ID --output
<fresh private directory> uses the existing gh session only when explicitly run.
The request is authenticated by github_read; only fixture.payloads bytes are packed.
The ephemeral public recipient is parsed/pinned by unchanged retention encryption.
Response is uploaded last, followed by authenticated ciphertext/response readback.

cleanup --binding <same binding> --artifact-id ID --receipt <local receipt> rechecks
only the recorded draft and exact recorded assets before authenticated DELETE.
It works after request expiry for recovery, but does not weaken draft identity.
A partial unknown asset, changed author/tag/commit or published release is refused.
Successful DELETE is recorded; no GET404 absence proof is claimed. No automatic
cleanup is attempted after failures. No workflow dispatch or native execution.

Adapter injection permits entirely offline tests. No private retention key path is
accepted; credentials and signed URLs are never written to receipts or diagnostics.
"""
import argparse,importlib.util,json,os,subprocess,tempfile,time
from pathlib import Path
import fixture
import github_read as g
import protocol as p
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture_retention',HERE.parents[2]/'distribution/private-retention/retain.py');retention=importlib.util.module_from_spec(spec);spec.loader.exec_module(retention)
CIPHER_LIMIT=128*1024

def fixture_binding(value):
 b=p.binding(value)
 for key,pin in fixture.pins().items():p.require(b[key]==pin,'nonfixture candidate refused')
 return b

def save(path,obj):
 raw=p.encode(obj);tmp=path.with_suffix('.tmp')
 with tmp.open('xb') as out:out.write(raw)
 tmp.chmod(0o600);os.replace(tmp,path)

def fresh(value):
 value=Path(value).absolute();p.require(not value.exists() and not value.is_symlink(),'fresh output required')
 p.require(value.parent.is_dir() and not any(x.is_symlink() for x in (value.parent,*value.parent.parents)),'output ancestor')
 value.mkdir(mode=0o700);return value

class GhAdapter:
 """Only explicit invocation uses existing gh session. Never returns credentials."""
 def __init__(self,run=subprocess.run):self._run=run;self._reader=None
 def __repr__(self):return 'FixtureGhAdapter(credentials withheld)'
 def execute(self,args):
  try:r=self._run(['gh',*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
  except Exception:raise ValueError('GitHub operation failed; diagnostics withheld') from None
  p.require(r.returncode==0,'GitHub operation failed; diagnostics withheld');return r.stdout
 @property
 def reader(self):
  if self._reader is None:
   token=self.execute(['auth','token','--hostname','github.com']).decode().strip();self._reader=g.Client(token)
  return self._reader
 def operator_id(self):return p.decode(self.execute(['api','user']))['id']
 def create(self,repository,payload):
  with tempfile.TemporaryDirectory(prefix='flapart-fixture-api-') as td:
   path=Path(td)/'body.json';path.write_bytes(p.encode(payload));path.chmod(0o600)
   return p.decode(self.execute(['api','--method','POST','repos/'+repository+'/releases','--input',str(path)]))
 def upload(self,repository,release_id,tag,path):
  self.execute(['release','upload',tag,str(path),'--repo',repository])
  rows=self.reader.json('/repos/'+repository+f'/releases/{release_id}/assets?per_page=100')
  p.require(isinstance(rows,list) and len(rows)<=2,'asset list bound')
  found=[x for x in rows if x.get('name')==path.name];p.require(len(found)==1,'uploaded asset ambiguous');return found[0]
 def delete(self,repository,release_id):self.execute(['api','--method','DELETE',f'repos/{repository}/releases/{release_id}','--silent'])

def release_checked(raw,obj,release_id=None):
 b=obj['binding'];rid=raw.get('id')
 p.require(type(rid) is int and rid>0 and (release_id is None or rid==release_id),'release ID')
 p.require(raw.get('draft') is True and raw.get('published_at') is None and raw.get('tag_name')==g.draft_tag(obj),'draft identity')
 p.require(raw.get('target_commitish')==b['commit'] and raw.get('author',{}).get('id')==b['operator_id'],'draft owner/commit')
 p.require(p.equal(p.decode(raw.get('body','').encode()),{'schema':1,'request_sha256':p.digest(p.encode(obj))}),'draft request binding')
 return rid

def asset_checked(raw,obj,rid,path):
 p.require(type(raw.get('id')) is int and raw['id']>0 and raw.get('name')==path.name and raw.get('state')=='uploaded' and raw.get('uploader',{}).get('id')==obj['binding']['operator_id'],'asset identity')
 p.require(raw.get('size')==path.stat().st_size and raw.get('digest')=='sha256:'+p.file_digest(path),'asset bytes')
 return {'id':raw['id'],'release_id':rid,'name':path.name,'uploader_id':raw['uploader']['id'],'state':'uploaded','bytes':raw['size'],'sha256':p.file_digest(path)}

def coordinate(expected,artifact_id,output,adapter,clock=lambda:int(time.time())):
 b=fixture_binding(expected);p.require(type(artifact_id) is int and artifact_id>0,'artifact ID');output=fresh(output)
 receipt={'schema':1,'fixture_only':True,'binding':b,'artifact_id':artifact_id,'release_id':None,'assets':[],'ready':False,'cleanup_complete':False}
 save(output/'coordinator-receipt.json',receipt)
 try:
  p.require(adapter.operator_id()==b['operator_id'],'authenticated operator mismatch')
  observed=g.fetch_request(adapter.reader,b,artifact_id,clock());obj=observed['request']
  receipt.update(request=obj,request_artifact_sha256=observed['artifact_sha256']);save(output/'coordinator-receipt.json',receipt)
  source=output/'fixture-input';source.mkdir(mode=0o700)
  inputs={}
  for name,data in fixture.payloads().items():
   path=source/name;path.write_bytes(data);path.chmod(0o600);inputs[name]=path
  # protocol prohibits output below input parent; use a sibling under same private root.
  packed=output/'packed';p.pack(obj,inputs,packed,clock())
  key=output/'recipient-public.asc';key.write_bytes(observed['public_key']);key.chmod(0o600)
  ciphertext=output/'candidate.gpg';retention.encrypt(packed,packed/'inventory.json',key,obj['fingerprint'],ciphertext)
  p.require(ciphertext.stat().st_size<=CIPHER_LIMIT,'fixture ciphertext bound');p.check_request(obj,clock())
  # Reauthenticate the full request/run/attempt/job/artifact immediately before mutation.
  current=g.fetch_request(adapter.reader,b,artifact_id,clock());p.require(p.equal(current['request'],obj) and current['artifact_sha256']==receipt['request_artifact_sha256'],'request changed')
  body={'tag_name':g.draft_tag(obj),'target_commitish':b['commit'],'name':'Harmless Flapart rendezvous fixture','body':p.encode({'schema':1,'request_sha256':p.digest(p.encode(obj))}).decode(),'draft':True,'prerelease':True,'generate_release_notes':False}
  created=adapter.create(b['repository'],body)
  if type(created.get('id')) is int and created['id']>0:
   receipt['release_id']=created['id'];save(output/'coordinator-receipt.json',receipt)
  rid=release_checked(created,obj)
  for path in [ciphertext,output/'response.json']:
   p.check_request(obj,clock());release_checked(adapter.reader.json('/repos/'+b['repository']+f'/releases/{rid}'),obj,rid)
   if path.name=='response.json':path.write_bytes(p.encode(p.response(obj,ciphertext,receipt['assets'][0]['id'],rid,clock())));path.chmod(0o600)
   raw=adapter.upload(b['repository'],rid,g.draft_tag(obj),path);receipt['assets'].append(asset_checked(raw,obj,rid,path));save(output/'coordinator-receipt.json',receipt)
  # Existing authenticated read path independently downloads and validates both assets.
  verified=g.fetch_response(adapter.reader,obj,rid,output/'verified-candidate.gpg',clock())
  p.require(verified['asset']['sha256']==p.file_digest(ciphertext),'readback ciphertext mismatch')
  receipt['ready']=True;save(output/'coordinator-receipt.json',receipt);return receipt
 except Exception as error:
  receipt['failure_type']=type(error).__name__;save(output/'coordinator-receipt.json',receipt)
  raise ValueError('Fixture coordinator failed; scoped receipt retained, diagnostics withheld') from None

def cleanup(expected,artifact_id,receipt_path,adapter):
 b=fixture_binding(expected);path=p.regular(Path(receipt_path).absolute());r=p.read_metadata(path)
 p.require(r.get('schema')==1 and r.get('fixture_only') is True and p.equal(r.get('binding'),b) and r.get('artifact_id')==artifact_id,'cleanup receipt binding')
 obj=r.get('request');p.check_request(obj,obj['created']);p.require(p.equal(obj['binding'],b),'cleanup request binding')
 p.require(r.get('cleanup_complete') is False and type(r.get('release_id')) is int and r['release_id']>0,'recorded draft required')
 p.require(adapter.operator_id()==b['operator_id'],'cleanup operator')
 rid=r['release_id'];release_checked(adapter.reader.json('/repos/'+b['repository']+f'/releases/{rid}'),obj,rid)
 rows=adapter.reader.json('/repos/'+b['repository']+f'/releases/{rid}/assets?per_page=100');p.require(isinstance(rows,list) and len(rows)<=2 and len(rows)==len(r['assets']),'unrecorded asset: cleanup refused')
 observed=[]
 for a in rows:
  observed.append({'id':a.get('id'),'release_id':rid,'name':a.get('name'),'uploader_id':a.get('uploader',{}).get('id'),'state':a.get('state'),'bytes':a.get('size'),'sha256':a.get('digest','').removeprefix('sha256:')})
 p.require(p.equal(sorted(observed,key=lambda x:x['id']),sorted(r['assets'],key=lambda x:x['id'])),'cleanup asset identity mismatch')
 release_checked(adapter.reader.json('/repos/'+b['repository']+f'/releases/{rid}'),obj,rid)
 adapter.delete(b['repository'],rid)
 # Successful authenticated DELETE is recorded, not falsely upgraded to GET404 proof.
 r['cleanup_complete']=True;r['cleanup_basis']='authenticated DELETE success after exact draft/assets recheck';save(path,r);return r

def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['coordinate','cleanup']);parser.add_argument('--binding',type=Path,required=True);parser.add_argument('--artifact-id',type=int,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--receipt',type=Path);a=parser.parse_args();b=p.read_metadata(p.regular(a.binding.absolute()));adapter=GhAdapter()
 result=coordinate(b,a.artifact_id,a.output,adapter) if a.command=='coordinate' else cleanup(b,a.artifact_id,a.receipt,adapter)
 print(json.dumps({'fixture_only':True,'ready':result['ready'],'cleanup_complete':result['cleanup_complete'],'release_id':result['release_id']}))
if __name__=='__main__':main()
