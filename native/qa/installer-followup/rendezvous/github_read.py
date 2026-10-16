"""Read-only GitHub observations. No upload, dispatch, credential discovery or logging.
Token is supplied explicitly by caller; never reads credential files/environment.
"""
import io,json,re,stat,time,urllib.error,urllib.parse,urllib.request,zipfile
import protocol as p

API='https://api.github.com'
JSON_LIMIT=2*1024**2
ARTIFACT_LIMIT=1024**2

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

class UrllibTransport:
 def __init__(self):self.opener=urllib.request.build_opener(NoRedirect())
 def get(self,url,headers,limit,sink=None):
  try:
   try:response=self.opener.open(urllib.request.Request(url,headers=headers,method='GET'),timeout=30)
   except urllib.error.HTTPError as error:response=error
   with response:
    status=response.code;head={k.lower():v for k,v in response.headers.items()}
    if status in (301,302,303,307,308):return status,head,b''
    if sink is not None and status==200:
     total=0
     while True:
      block=response.read(min(1024**2,limit-total+1))
      if not block:break
      total+=len(block);p.require(total<=limit,'download limit');sink.write(block)
     return status,head,b''
    data=response.read(min(limit,JSON_LIMIT)+1)
    p.require(len(data)<=min(limit,JSON_LIMIT),'download limit')
    return status,head,data
  except Exception:
   raise ValueError('GitHub read failed; URL and credentials withheld') from None

class Client:
 def __init__(self,token,transport=None):
  p.require(isinstance(token,str) and token and '\n' not in token and '\r' not in token,'explicit token required')
  self._token=token;self.transport=transport or UrllibTransport()
 def __repr__(self):return 'GitHubReadClient(credentials withheld)'
 def _get(self,path,limit,accept='application/vnd.github+json',download=False,sink=None):
  p.require(isinstance(path,str) and path.startswith('/repos/') and not any(x in path for x in ('..','\\','#','://')),'API path')
  headers={'Authorization':'Bearer '+self._token,'Accept':accept,'X-GitHub-Api-Version':'2026-03-10','User-Agent':'Flapart-rendezvous-read'}
  url=API+path
  for step in range(4):
   try:
    status,head,data=self.transport.get(url,headers,limit,sink) if sink is not None else self.transport.get(url,headers,limit)
   except Exception:raise ValueError('GitHub read failed; URL and credentials withheld') from None
   p.require(len(data)<=limit,'download limit')
   if status in (301,302,303,307,308):
    p.require(download,'unexpected API redirect')
    target=head.get('location','');parsed=urllib.parse.urlsplit(target)
    try:port=parsed.port
    except ValueError:raise ValueError('invalid download redirect') from None
    host=parsed.hostname or ''
    p.require(parsed.scheme=='https' and not parsed.username and not parsed.password and not parsed.fragment and port in (None,443) and (host.endswith('.githubusercontent.com') or host.endswith('.blob.core.windows.net')),'unapproved download redirect')
    url=target;headers={'User-Agent':'Flapart-rendezvous-read'} # Never forward API credentials, even on a later redirect.
    continue
   p.require(status==200,'GitHub read returned non-success status '+str(status))
   return data
  raise ValueError('too many download redirects')
 def json(self,path):
  data=self._get(path,JSON_LIMIT)
  # Larger API lists are permitted; duplicate JSON keys remain forbidden.
  def pairs(rows):
   obj={}
   for k,v in rows:p.require(k not in obj,'duplicate API JSON key');obj[k]=v
   return obj
  try:return json.loads(data,object_pairs_hook=pairs)
  except Exception:raise ValueError('invalid GitHub API JSON') from None
 def download(self,path,limit):
  accept='application/vnd.github+json' if re.fullmatch(r'/repos/[^/]+/[^/]+/actions/artifacts/[0-9]+/zip',path) else 'application/octet-stream'
  return self._get(path,limit,accept,True)
 def download_to(self,path,limit,sink):return self._get(path,limit,'application/octet-stream',True,sink)

def integer(value):return type(value) is int and value>0

def artifact_members(data):
 p.require(len(data)<=ARTIFACT_LIMIT,'artifact archive size')
 try:
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   entries=z.infolist();p.require(len(entries)==2,'artifact must contain exactly two files')
   names=set();result={}
   for entry in entries:
    p.require(entry.orig_filename==entry.filename and entry.filename in ('request.json','recipient-public.asc') and entry.filename not in names,'unexpected/duplicate artifact member')
    names.add(entry.filename)
    p.require(not entry.is_dir() and stat.S_IFMT(entry.external_attr>>16) in (0,stat.S_IFREG) and not entry.flag_bits&1,'artifact special/encrypted member')
    p.require(0<entry.file_size<=65536,'artifact member size')
    with z.open(entry) as stream:
     content=stream.read(65537);p.require(len(content)==entry.file_size and len(content)<=65536,'artifact member bound')
    result[entry.filename]=content
   return result
 except Exception:raise ValueError('invalid bounded rendezvous artifact ZIP') from None

def request_artifact_name(b):return f"rendezvous-{b['run_id']}-{b['attempt']}-{b['architecture']}-request"
def draft_tag(obj):
 b=obj['binding'];return f"rendezvous-{b['run_id']}-{b['attempt']}-{b['architecture']}-{obj['nonce']}"

def fetch_request(client,expected,artifact_id,now):
 """Caller pins dispatch binding and selected artifact ID, never from peer JSON."""
 started=time.monotonic()
 b=p.binding(expected);p.require(integer(artifact_id),'artifact ID')
 base='/repos/'+b['repository'];run=client.json(base+f"/actions/runs/{b['run_id']}")
 p.require(isinstance(run,dict),'run metadata')
 p.require(run.get('repository',{}).get('full_name')==b['repository'],'run repository')
 p.require(run.get('triggering_actor',{}).get('id')==b['operator_id'],'run triggering operator')
 run_obs={'repository':run['repository']['full_name'],'id':run.get('id'),'attempt':run.get('run_attempt'),'head_sha':run.get('head_sha'),'workflow':run.get('path'),'event':run.get('event'),'actor_id':run.get('actor',{}).get('id'),'status':run.get('status')}
 # Check authenticated job belongs to exact attempt via attempt-specific list.
 listing=client.json(base+f"/actions/runs/{b['run_id']}/attempts/{b['attempt']}/jobs?per_page=100")
 p.require(isinstance(listing,dict) and type(listing.get('total_count')) is int and 0<listing['total_count']<=100 and isinstance(listing.get('jobs'),list) and len(listing['jobs'])==listing['total_count'],'bounded job list')
 matches=[j for j in listing['jobs'] if isinstance(j,dict) and j.get('id')==b['job_id']]
 p.require(len(matches)==1,'attempt job membership');job=matches[0]
 label={'arm64':'macos-15','x86_64':'macos-15-intel'}[b['architecture']]
 p.require(job.get('name')=='installer-'+b['architecture'] and isinstance(job.get('labels'),list) and label in job['labels'],'approved architecture job/runner label')
 job_obs={'id':job.get('id'),'run_id':job.get('run_id'),'attempt':b['attempt'],'architecture':b['architecture'],'status':job.get('status')}
 art=client.json(base+f'/actions/artifacts/{artifact_id}')
 p.require(isinstance(art,dict) and type(art.get('size_in_bytes')) is int and 0<art['size_in_bytes']<=ARTIFACT_LIMIT,'artifact metadata size')
 p.require(art.get('id')==artifact_id and art.get('name')==request_artifact_name(b) and art.get('expired') is False,'artifact identity')
 wr=art.get('workflow_run',{});p.require(wr.get('id')==b['run_id'] and wr.get('head_sha')==b['commit'],'artifact workflow run')
 sha=art.get('digest');p.require(isinstance(sha,str) and re.fullmatch('sha256:[0-9a-f]{64}',sha),'artifact API digest required')
 data=client.download(base+f'/actions/artifacts/{artifact_id}/zip',ARTIFACT_LIMIT)
 p.require(len(data)==art['size_in_bytes'] and 'sha256:'+p.digest(data)==sha,'artifact archive identity')
 members=artifact_members(data);raw=members['request.json'];key=members['recipient-public.asc']
 obs={'id':artifact_id,'run_id':wr['id'],'expired':False,'request_sha256':p.digest(raw),'key_sha256':p.digest(key)}
 obj=p.authenticate_request(raw,key,b,run_obs,job_obs,obs,now+int(time.monotonic()-started))
 return {'request':obj,'request_bytes':raw,'public_key':key,'artifact_id':artifact_id,'artifact_sha256':p.digest(data),'run':run_obs,'job':job_obs,'artifact':obs}

def fetch_response(client,obj,release_id,ciphertext_path,now):
 """Download ciphertext only to a fresh explicit path; return verified observations."""
 from pathlib import Path
 started=time.monotonic()
 p.check_request(obj,now);p.require(integer(release_id),'release ID')
 b=obj['binding'];base='/repos/'+b['repository'];rel=client.json(base+f'/releases/{release_id}')
 p.require(isinstance(rel,dict) and rel.get('id')==release_id and rel.get('draft') is True and rel.get('published_at') is None and rel.get('tag_name')==draft_tag(obj),'draft identity')
 # Authenticated API draft body is operator-owned metadata, compared with local request pin.
 body=p.decode(rel.get('body','').encode());p.require(p.equal(body,{'schema':1,'request_sha256':p.digest(p.encode(obj))}),'draft exchange binding')
 release_obs={'id':rel['id'],'draft':rel['draft'],'published_at':rel['published_at'],'author_id':rel.get('author',{}).get('id'),'target_commitish':rel.get('target_commitish'),'request_sha256':body['request_sha256']}
 p.require(p.equal(release_obs,{'id':release_id,'draft':True,'published_at':None,'author_id':b['operator_id'],'target_commitish':b['commit'],'request_sha256':p.digest(p.encode(obj))}),'draft operator/commit mismatch')
 # Separate complete listing prevents relying on an embedded truncated assets list.
 assets=client.json(base+f'/releases/{release_id}/assets?per_page=100')
 p.require(isinstance(assets,list) and len(assets)==2,'exact response asset set')
 byname={a.get('name'):a for a in assets if isinstance(a,dict)}
 p.require(set(byname)=={'candidate.gpg','response.json'},'response asset names')
 observations={}
 for name,a in byname.items():
  p.require(integer(a.get('id')) and a.get('state')=='uploaded' and a.get('uploader',{}).get('id')==b['operator_id'],'asset authenticated identity')
  limit=65536 if name=='response.json' else p.LIMIT
  p.require(type(a.get('size')) is int and 0<a['size']<=limit,'asset size')
  sha=a.get('digest');p.require(isinstance(sha,str) and re.fullmatch('sha256:[0-9a-f]{64}',sha),'asset API digest required')
  observations[name]={'id':a['id'],'release_id':release_id,'name':name,'uploader_id':a['uploader']['id'],'state':a['state'],'bytes':a['size'],'sha256':sha[7:]}
 p.require(observations['candidate.gpg']['id']!=observations['response.json']['id'],'duplicate asset IDs')
 def download(name):
  a=observations[name];data=client.download(base+f"/releases/assets/{a['id']}",a['bytes'])
  p.require(len(data)==a['bytes'] and p.digest(data)==a['sha256'],'downloaded asset mismatch');return data
 raw=download('response.json');r=p.decode(raw);a=observations['candidate.gpg']
 p.require(p.equal(r,{'schema':1,'request_sha256':p.digest(p.encode(obj)),'release_id':release_id,'asset_id':a['id'],'asset_name':'candidate.gpg','bytes':a['bytes'],'sha256':a['sha256']}),'response admission mismatch')
 path=Path(ciphertext_path);p.require(path.is_absolute() and path.parent.is_dir() and not any(x.is_symlink() for x in (path,*path.parents)) and not path.exists(),'fresh ciphertext path')
 p.check_request(obj,now+int(time.monotonic()-started))
 # Exclusive create; never remove a preexisting competing destination on failure.
 created=False
 try:
  with path.open('xb') as stream:
   created=True;path.chmod(0o600);client.download_to(base+f"/releases/assets/{a['id']}",a['bytes'],stream)
  p.require(path.stat().st_size==a['bytes'] and p.file_digest(path)==a['sha256'],'downloaded asset mismatch')
  validated=p.validate_response(raw,obj,path,release_obs,a,observations['response.json'],now+int(time.monotonic()-started))
  return {'response':validated,'response_bytes':raw,'release':release_obs,'asset':a,'response_asset':observations['response.json']}
 except Exception:
  if created:path.unlink(missing_ok=True)
  raise
