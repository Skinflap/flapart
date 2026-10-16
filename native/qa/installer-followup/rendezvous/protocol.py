"""Offline rendezvous checks. Caller supplies authenticated API observations.
No networking, key generation, encryption, native execution or release authority.
"""
import hashlib,json,re,shutil,tempfile
from pathlib import Path

LIMIT=2*1024**3-1
FILES=('candidate.zip','candidate-inventory.json','candidate-manifest.json')
BINDING={'repository','workflow','run_id','attempt','commit','job_id','architecture','operator_id','candidate_sha256','candidate_bytes','inventory_sha256','manifest_sha256'}

def require(ok,message):
 if not ok:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def file_digest(path):
 with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def encode(obj):return (json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
def equal(a,b):return encode(a)==encode(b)
def read_metadata(path):
 require(path.stat().st_size<=65536,'metadata too large')
 return decode(path.read_bytes())
def decode(data):
 require(len(data)<=65536,'metadata too large')
 def pairs(rows):
  result={}
  for k,v in rows:
   require(k not in result,'duplicate JSON key');result[k]=v
  return result
 return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'nonfinite JSON'))
def hexstr(value,n):return isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(n)+'}',value) is not None
def binding(value):
 require(isinstance(value,dict) and set(value)==BINDING,'binding fields')
 require(isinstance(value['repository'],str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value['repository']),'repository')
 require(isinstance(value['workflow'],str) and re.fullmatch(r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml',value['workflow']),'workflow')
 for k in ('run_id','attempt','job_id','operator_id','candidate_bytes'):require(type(value[k]) is int and value[k]>0,k)
 require(value['candidate_bytes']<=LIMIT,'candidate limit')
 require(hexstr(value['commit'],40),'commit')
 for k in ('candidate_sha256','inventory_sha256','manifest_sha256'):require(hexstr(value[k],64),k)
 require(value['architecture'] in ('arm64','x86_64'),'architecture')
 return value

def request(binding_value,key_bytes,fingerprint,nonce,created,expires):
 obj={'schema':1,'binding':binding(binding_value),'key_sha256':digest(key_bytes),'fingerprint':fingerprint,'nonce':nonce,'created':created,'expires':expires}
 check_request(obj,created)
 require(0<len(key_bytes)<=65536 and b'PRIVATE KEY' not in key_bytes,'public key input')
 return obj

def check_request(obj,now):
 require(isinstance(obj,dict) and set(obj)=={'schema','binding','key_sha256','fingerprint','nonce','created','expires'} and type(obj['schema']) is int and obj['schema']==1,'request fields')
 binding(obj['binding'])
 require(hexstr(obj['key_sha256'],64) and hexstr(obj['nonce'],64),'key/nonce')
 require(isinstance(obj['fingerprint'],str) and re.fullmatch('[A-F0-9]{40}',obj['fingerprint']),'full fingerprint')
 require(type(now) is int and type(obj['created']) is int and type(obj['expires']) is int,'timestamps')
 require(obj['created']<=now<obj['expires'] and 0<obj['expires']-obj['created']<=3600,'expired/future request')
 return obj

def authenticate_request(raw,key,expected,run,job,artifact,now):
 """run/job/artifact MUST come from authenticated GitHub API, not payload JSON.
 Artifact observations are normalized by a separate network adapter; digest here
 means SHA of the downloaded artifact archive, independently checked by adapter.
 """
 obj=check_request(decode(raw),now);b=binding(expected)
 require(equal(obj['binding'],b),'dispatch binding mismatch')
 require(digest(key)==obj['key_sha256'] and 0<len(key)<=65536 and b'PRIVATE KEY' not in key,'key bytes')
 require(equal(run,{'repository':b['repository'],'id':b['run_id'],'attempt':b['attempt'],'head_sha':b['commit'],'workflow':b['workflow'],'event':'workflow_dispatch','actor_id':b['operator_id'],'status':'in_progress'}),'authenticated run mismatch')
 require(equal(job,{'id':b['job_id'],'run_id':b['run_id'],'attempt':b['attempt'],'architecture':b['architecture'],'status':'in_progress'}),'authenticated job mismatch')
 require(set(artifact)=={'id','run_id','request_sha256','key_sha256','expired'} and type(artifact['id']) is int and artifact['id']>0 and artifact['run_id']==b['run_id'] and artifact['expired'] is False and artifact['request_sha256']==digest(raw) and artifact['key_sha256']==digest(key),'authenticated artifact mismatch')
 return obj

def regular(path):
 path=Path(path)
 require(path.is_absolute(),'absolute file path required')
 require(not any(p.is_symlink() for p in (path,*path.parents)) and path.is_file(),'regular confined input required')
 return path

def pack(obj,inputs,output,now):
 """Create a fresh retention input root; no tar/ZIP extraction or native launch."""
 check_request(obj,now);require(set(inputs)==set(FILES),'exact inputs required')
 output=Path(output);require(output.is_absolute() and not output.exists(),'fresh output required')
 parent=output.parent;require(parent.is_dir() and not any(p.is_symlink() for p in (parent,*parent.parents)),'output parent')
 sources={name:regular(path) for name,path in inputs.items()}
 require(all(not p.is_relative_to(output) and not output.is_relative_to(p.parent) for p in sources.values()),'output/input overlap')
 b=obj['binding'];pins=(b['candidate_sha256'],b['inventory_sha256'],b['manifest_sha256'])
 for name,pin in zip(FILES,pins):
  require(file_digest(sources[name])==pin,'input pin mismatch')
  require(sources[name].stat().st_size<=LIMIT,'input size')
 require(sources['candidate.zip'].stat().st_size==b['candidate_bytes'],'candidate bytes')
 with tempfile.TemporaryDirectory(prefix='.rendezvous-',dir=parent) as tmp:
  staged=Path(tmp)/'root';staged.mkdir(mode=0o700)
  for name,path in sources.items():shutil.copyfile(path,staged/name);(staged/name).chmod(0o600)
  (staged/'exchange.json').write_bytes(encode({'schema':1,'request':obj,'native_executed':False,'release_qualified':False}))
  rows=[{'path':p.name,'bytes':p.stat().st_size,'sha256':file_digest(p)} for p in sorted(staged.iterdir())]
  require(sum(r['bytes'] for r in rows)<=LIMIT,'transfer size')
  (staged/'inventory.json').write_bytes(encode({'schema':1,'candidate':'candidate.zip','files':rows}))
  validate_pack(staged,obj,now)
  require(all(file_digest(sources[n])==p for n,p in zip(FILES,pins)),'input changed during copy')
  staged.rename(output)
 return output

def validate_pack(root,obj,now):
 check_request(obj,now);root=Path(root)
 require(root.is_absolute() and root.is_dir() and not any(p.is_symlink() for p in (root,*root.parents)),'pack root')
 require({p.name for p in root.iterdir()}==set(FILES)|{'exchange.json','inventory.json'},'unexpected pack entries')
 for p in root.iterdir():regular(p)
 inv=read_metadata(root/'inventory.json')
 require(set(inv)=={'schema','candidate','files'} and inv['schema']==1 and inv['candidate']=='candidate.zip' and isinstance(inv['files'],list) and len(inv['files'])==4,'inventory')
 rows=inv['files'];seen=set();total=0
 for row in rows:
  require(set(row)=={'path','bytes','sha256'} and row['path'] in (*FILES,'exchange.json') and row['path'] not in seen,'inventory member')
  seen.add(row['path']);p=root/row['path']
  require(type(row['bytes']) is int and 0<=row['bytes']<=LIMIT and p.stat().st_size==row['bytes'] and file_digest(p)==row['sha256'],'changed member');total+=row['bytes']
 require(total<=LIMIT,'transfer size')
 require(equal(read_metadata(root/'exchange.json'),{'schema':1,'request':obj,'native_executed':False,'release_qualified':False}),'exchange mismatch')
 b=obj['binding']
 for name,pin in zip(FILES,(b['candidate_sha256'],b['inventory_sha256'],b['manifest_sha256'])):require(file_digest(root/name)==pin,'candidate pin mismatch')
 require((root/'candidate.zip').stat().st_size==b['candidate_bytes'],'candidate size mismatch')
 return inv

def response(obj,ciphertext,asset_id,release_id,now):
 check_request(obj,now);p=regular(ciphertext)
 require(0<p.stat().st_size<=LIMIT,'ciphertext size')
 require(type(asset_id) is int and asset_id>0 and type(release_id) is int and release_id>0,'asset identity')
 return {'schema':1,'request_sha256':digest(encode(obj)),'release_id':release_id,'asset_id':asset_id,'asset_name':'candidate.gpg','bytes':p.stat().st_size,'sha256':file_digest(p)}

def validate_response(raw,obj,ciphertext,release,asset,response_asset,now):
 """API observations are caller-trusted inputs; JSON claims never authenticate."""
 check_request(obj,now);r=decode(raw)
 require(isinstance(r,dict) and set(r)=={'schema','request_sha256','release_id','asset_id','asset_name','bytes','sha256'},'response fields')
 require(equal(r,response(obj,ciphertext,r['asset_id'],r['release_id'],now)),'response/ciphertext mismatch')
 b=obj['binding'];require(equal(release,{'id':r['release_id'],'draft':True,'published_at':None,'author_id':b['operator_id'],'target_commitish':b['commit'],'request_sha256':digest(encode(obj))}),'authenticated draft mismatch')
 require(equal(asset,{'id':r['asset_id'],'release_id':r['release_id'],'name':'candidate.gpg','uploader_id':b['operator_id'],'state':'uploaded','bytes':r['bytes'],'sha256':r['sha256']}),'authenticated ciphertext asset mismatch')
 require(set(response_asset)=={'id','release_id','name','uploader_id','state','bytes','sha256'} and type(response_asset['id']) is int and response_asset['id']>0 and response_asset['id']!=r['asset_id'] and equal(response_asset,dict(id=response_asset['id'],release_id=r['release_id'],name='response.json',uploader_id=b['operator_id'],state='uploaded',bytes=len(raw),sha256=digest(raw))),'authenticated response asset mismatch')
 return r
