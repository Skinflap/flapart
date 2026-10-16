"""Authenticated full-chain descriptor response, distinct from fixture protocol."""
import time
from pathlib import Path
import protocol as p,github_read as g,full_chain as f


def tag(request):return 'full-chain-'+g.draft_tag(request)
def body(request,chain_pin,descriptor):
 pin=p.digest(p.encode(descriptor));f.check_descriptor(descriptor,pin,request,chain_pin)
 return {'schema':1,'kind':'flapart-complete-chain-response','request_sha256':p.digest(p.encode(request)),'chain_manifest_sha256':chain_pin,'descriptor_sha256':pin,'descriptor':descriptor}

def release_checked(raw,request,chain_pin,release_id=None,expected_body=None):
 b=request['binding'];rid=raw.get('id');p.require(g.integer(rid) and (release_id is None or rid==release_id),'full-chain release ID')
 p.require(raw.get('draft') is True and raw.get('published_at') is None and raw.get('tag_name')==tag(request),'full-chain draft identity')
 p.require(raw.get('author',{}).get('id')==b['operator_id'] and raw.get('target_commitish')==b['commit'],'full-chain draft operator/commit')
 value=p.decode(raw.get('body','').encode());p.require(isinstance(value,dict) and set(value)=={'schema','kind','request_sha256','chain_manifest_sha256','descriptor_sha256','descriptor'},'full-chain body fields')
 f.check_descriptor(value['descriptor'],value['descriptor_sha256'],request,chain_pin)
 p.require(p.equal(value,body(request,chain_pin,value['descriptor'])),'full-chain body binding')
 if expected_body is not None:p.require(p.equal(value,expected_body),'full-chain draft body changed')
 return rid,value

def assets_checked(raw,request,rid):
 p.require(isinstance(raw,list) and len(raw)==2,'exact complete-chain asset set')
 rows={}
 for a in raw:
  p.require(isinstance(a,dict) and a.get('name') in ('candidate.gpg','response.json') and a['name'] not in rows,'complete-chain asset names')
  p.require(g.integer(a.get('id')) and a.get('state')=='uploaded' and a.get('uploader',{}).get('id')==request['binding']['operator_id'],'complete-chain asset operator')
  limit=p.LIMIT if a['name']=='candidate.gpg' else 65536
  p.require(type(a.get('size')) is int and 0<a['size']<=limit and isinstance(a.get('digest'),str) and a['digest'].startswith('sha256:') and p.hexstr(a['digest'][7:],64),'complete-chain asset bytes')
  rows[a['name']]={'id':a['id'],'release_id':rid,'name':a['name'],'uploader_id':a['uploader']['id'],'bytes':a['size'],'sha256':a['digest'][7:],'state':'uploaded'}
 p.require(len({a['id'] for a in rows.values()})==2,'duplicate complete-chain asset IDs')
 return rows

def response_value(request,chain_pin,descriptor,rid,cipher_asset_id):
 p.require(g.integer(rid) and g.integer(cipher_asset_id),'response IDs')
 return dict(body(request,chain_pin,descriptor),release_id=rid,ciphertext_asset_id=cipher_asset_id)

def fetch(client,request,chain_pin,artifact_id,release_id,destination,now):
 """Authenticate API body/asset authors before trusting descriptor and streaming."""
 start=time.monotonic();p.check_request(request,now);b=request['binding'];p.require(g.integer(release_id),'release ID')
 observed=g.fetch_request(client,b,artifact_id,now);p.require(p.equal(observed['request'],request),'original request artifact changed')
 base='/repos/'+b['repository'];rid,value=release_checked(client.json(base+f'/releases/{release_id}'),request,chain_pin,release_id)
 rows=assets_checked(client.json(base+f'/releases/{rid}/assets?per_page=100'),request,rid);cipher=rows['candidate.gpg'];meta=rows['response.json'];descriptor=value['descriptor']
 p.require(cipher['sha256']==descriptor['ciphertext_sha256'] and cipher['bytes']==descriptor['ciphertext_bytes'],'descriptor vs authenticated ciphertext')
 raw=client.download(base+f"/releases/assets/{meta['id']}",65536)
 p.require(len(raw)==meta['bytes'] and p.digest(raw)==meta['sha256'] and p.equal(p.decode(raw),response_value(request,chain_pin,descriptor,rid,cipher['id'])),'authenticated full-chain response')
 dest=f.fresh(destination);f.space(dest.parent,cipher['bytes']+3*descriptor['payload_bytes']+f.MARGIN)
 p.check_request(request,now+int(time.monotonic()-start));created=False
 try:
  with dest.open('xb') as stream:
   created=True;dest.chmod(0o600);client.download_to(base+f"/releases/assets/{cipher['id']}",cipher['bytes'],stream)
  p.require(dest.stat().st_size==cipher['bytes'] and p.file_digest(dest)==cipher['sha256'],'downloaded full-chain ciphertext')
  release_checked(client.json(base+f'/releases/{rid}'),request,chain_pin,rid,value)
  p.require(p.equal(assets_checked(client.json(base+f'/releases/{rid}/assets?per_page=100'),request,rid),rows),'full-chain assets changed during download')
  observed2=g.fetch_request(client,b,artifact_id,now+int(time.monotonic()-start));p.require(p.equal(observed2['request'],request) and observed2['artifact_sha256']==observed['artifact_sha256'],'request changed during transfer')
  p.check_request(request,now+int(time.monotonic()-start))
  return {'descriptor':descriptor,'descriptor_sha256':value['descriptor_sha256'],'release_id':rid,'assets':rows,'request_artifact_sha256':observed['artifact_sha256'],'native_executed':False,'release_qualified':False}
 except Exception:
  if created:dest.unlink(missing_ok=True)
  raise
