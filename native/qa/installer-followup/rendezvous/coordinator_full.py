"""Explicit full-chain coordinator; use injected adapters until separately authorized.
No credential/private-key access here. Existing GhAdapter can be passed explicitly.
"""
import time
from pathlib import Path
import protocol as p,github_read as g,full_chain as f,response_full as response
from coordinator_fixture import fresh,save,asset_checked


def coordinate(expected,artifact_id,original_root,original_manifest,chain_pin,output,adapter,clock=lambda:int(time.time())):
 b=p.binding(expected);p.require(g.integer(artifact_id) and p.hexstr(chain_pin,64),'independent artifact/chain pins');output=fresh(output)
 receipt={'schema':1,'kind':'full-chain-coordinator','binding':b,'artifact_id':artifact_id,'chain_manifest_sha256':chain_pin,'release_id':None,'assets':[],'ready':False,'cleanup_complete':False,'native_executed':False,'release_qualified':False}
 save(output/'coordinator-receipt.json',receipt)
 try:
  p.require(adapter.operator_id()==b['operator_id'],'authenticated full-chain operator')
  observed=g.fetch_request(adapter.reader,b,artifact_id,clock());request=observed['request'];receipt.update(request=request,request_artifact_sha256=observed['artifact_sha256']);save(output/'coordinator-receipt.json',receipt)
  f.pack(Path(original_root),Path(original_manifest),request,chain_pin,output/'envelope',clock())
  key=output/'recipient-public.asc';key.write_bytes(observed['public_key']);key.chmod(0o600)
  descriptor=f.encrypt(output/'envelope',request,chain_pin,key,output/'candidate.gpg',clock());metadata=response.body(request,chain_pin,descriptor)
  receipt.update(descriptor=descriptor,descriptor_sha256=metadata['descriptor_sha256']);save(output/'coordinator-receipt.json',receipt)
  current=g.fetch_request(adapter.reader,b,artifact_id,clock());p.require(p.equal(current['request'],request) and current['artifact_sha256']==observed['artifact_sha256'],'request changed before draft')
  payload={'tag_name':response.tag(request),'target_commitish':b['commit'],'name':'Private Flapart complete-chain test exchange','body':p.encode(metadata).decode(),'draft':True,'prerelease':True,'generate_release_notes':False,'make_latest':'false'}
  created=adapter.create(b['repository'],payload)
  if g.integer(created.get('id')):receipt['release_id']=created['id'];save(output/'coordinator-receipt.json',receipt)
  rid,_=response.release_checked(created,request,chain_pin,expected_body=metadata)
  for name in ('candidate.gpg','response.json'):
   p.check_request(request,clock());response.release_checked(adapter.reader.json('/repos/'+b['repository']+f'/releases/{rid}'),request,chain_pin,rid,metadata)
   path=output/name
   if name=='response.json':path.write_bytes(p.encode(response.response_value(request,chain_pin,descriptor,rid,receipt['assets'][0]['id'])));path.chmod(0o600)
   a=adapter.upload(b['repository'],rid,response.tag(request),path);receipt['assets'].append(asset_checked(a,request,rid,path));save(output/'coordinator-receipt.json',receipt)
  # Read back authenticated metadata and bytes before declaring exchange ready.
  verified=response.fetch(adapter.reader,request,chain_pin,artifact_id,rid,output/'verified-candidate.gpg',clock())
  p.require(p.equal(verified['descriptor'],descriptor),'authenticated descriptor readback differs')
  receipt['ready']=True;save(output/'coordinator-receipt.json',receipt);return receipt
 except Exception as error:
  receipt['failure_type']=type(error).__name__;save(output/'coordinator-receipt.json',receipt)
  raise ValueError('Full-chain coordinator failed; scoped receipt retained, diagnostics withheld') from None


def cleanup(expected,artifact_id,chain_pin,receipt_path,adapter):
 b=p.binding(expected);path=p.regular(Path(receipt_path));r=p.read_metadata(path)
 p.require(r.get('schema')==1 and r.get('kind')=='full-chain-coordinator' and p.equal(r.get('binding'),b) and r.get('artifact_id')==artifact_id and r.get('chain_manifest_sha256')==chain_pin and r.get('cleanup_complete') is False,'full-chain cleanup binding')
 request=r.get('request');p.check_request(request,request['created']);p.require(p.equal(request['binding'],b),'cleanup request binding')
 p.require(adapter.operator_id()==b['operator_id'] and g.integer(r.get('release_id')),'cleanup operator/draft')
 metadata=response.body(request,chain_pin,r['descriptor']);p.require(metadata['descriptor_sha256']==r['descriptor_sha256'],'cleanup descriptor pin');rid=r['release_id'];base='/repos/'+b['repository']
 response.release_checked(adapter.reader.json(base+f'/releases/{rid}'),request,chain_pin,rid,metadata)
 raw=adapter.reader.json(base+f'/releases/{rid}/assets?per_page=100');p.require(isinstance(raw,list) and len(raw)==len(r['assets']) and len(raw)<=2,'unrecorded cleanup asset')
 rows=[{'id':a.get('id'),'release_id':rid,'name':a.get('name'),'uploader_id':a.get('uploader',{}).get('id'),'state':a.get('state'),'bytes':a.get('size'),'sha256':a.get('digest','').removeprefix('sha256:')} for a in raw]
 p.require(p.equal(sorted(rows,key=lambda x:x['id']),sorted(r['assets'],key=lambda x:x['id'])),'cleanup exact asset mismatch')
 response.release_checked(adapter.reader.json(base+f'/releases/{rid}'),request,chain_pin,rid,metadata);adapter.delete(b['repository'],rid)
 r.update(cleanup_complete=True,cleanup_basis='authenticated DELETE success after exact draft/assets recheck');save(path,r);return r
