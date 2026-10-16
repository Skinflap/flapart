"""Separate complete-chain retention-v2 envelope. No GitHub or native execution.
Descriptor hash is an independent authenticated input, not learned from ciphertext.
"""
import os,shutil,tempfile,time
from pathlib import Path
import protocol as p
import candidate_runner as candidate

transport=candidate.transport
RETENTION=candidate.NATIVE/'distribution/private-retention/retain.py'
MAX_BYTES=8*1024**3
MARGIN=128*1024**2


def fresh(path):
 path=Path(path);p.require(path.is_absolute() and path.parent.is_dir() and not path.exists() and not any(x.is_symlink() for x in (path,*path.parents)),'fresh canonical output required');return path

def space(parent,required):
 p.require(shutil.disk_usage(parent).free>=required,'insufficient measured envelope disk space')

def retention(limit=MAX_BYTES):
 module=candidate.load('bounded_chain_retention',RETENTION);module.LIMIT=limit;return module

def inventory(root):
 root=Path(root);p.require(root.is_absolute() and root.is_dir() and not any(x.is_symlink() for x in (root,*root.parents)),'canonical envelope root')
 meta=p.regular(root/'inventory.json');p.require(meta.stat().st_size<=2*1024**2,'outer inventory bound')
 obj=transport.read(meta,2*1024**2);rows=retention().validate_inventory(obj);actual=set()
 for path in root.rglob('*'):
  p.require(not path.is_symlink(),'envelope symlink')
  if path.is_dir():continue
  p.regular(path);actual.add(path.relative_to(root).as_posix())
 p.require(actual=={'inventory.json',*(row['path'] for row in rows)},'envelope extra/missing files')
 for row in rows:
  path=root/row['path'];p.require(path.stat().st_size==row['bytes'] and p.file_digest(path)==row['sha256'],'envelope bytes altered')
 return obj,rows

def context(request,chain_pin):
 p.require(p.hexstr(chain_pin,64),'independent chain pin')
 return {'schema':1,'kind':'flapart-complete-chain-envelope','request':request,'chain_manifest_sha256':chain_pin,'native_executed':False,'source_closure_complete':False,'release_qualified':False}

def validate_envelope(root,request,chain_pin,now):
 p.check_request(request,now);root=Path(root);obj,rows=inventory(root)
 p.require(p.equal(p.read_metadata(root/'exchange.json'),context(request,chain_pin)),'envelope request/chain binding')
 p.require(p.file_digest(root/'installer-original.json')==request['binding']['manifest_sha256'],'installer original pin')
 allowed={'exchange.json','installer-original.json','retained/inventory.json','retained/transport-v2.json'}
 p.require(all(r['path'] in allowed or (r['path'].startswith('retained/objects/') and p.hexstr(r['path'][len('retained/objects/'):],64)) for r in rows),'unexpected complete-chain envelope member')
 nested=transport.read(root/'retained/inventory.json',2*1024**2);retention().validate_inventory(nested)
 tm=transport.read(root/'retained/transport-v2.json',transport.MANIFEST_LIMIT)
 p.require(isinstance(tm,dict) and set(tm)=={'schema','kind','candidate','files','logical_bytes','unique_bytes','objects'} and type(tm['schema']) is int and tm['schema']==2 and tm['kind']=='flapart-private-content-addressed','transport schema')
 objects,total=transport.rows_checked(tm['files'],tm['candidate'])
 p.require(type(tm['logical_bytes']) is int and type(tm['unique_bytes']) is int and type(tm['objects']) is int and (tm['logical_bytes'],tm['unique_bytes'],tm['objects'])==(total,sum(objects.values()),len(objects)),'transport totals')
 p.require(obj['candidate']=='retained/'+nested['candidate'],'outer candidate object mapping')
 p.require({r['path'] for r in rows}==allowed|{'retained/'+r['path'] for r in nested['files']},'nested retained object set mismatch')
 for row in nested['files']:
  path=root/'retained'/row['path'];p.require(path.stat().st_size==row['bytes'] and p.file_digest(path)==row['sha256'],'nested retained byte mismatch')
 return {'inventory_sha256':p.digest(p.encode(obj)),'payload_bytes':sum(r['bytes'] for r in rows),'files':len(rows),'largest_file_bytes':max(r['bytes'] for r in rows)}

def original_check(root,request,manifest,chain_pin,now):
 p.check_request(request,now);root=Path(root);candidate.tree_inventory(root);b=request['binding']
 p.require(p.file_digest(root/'candidate.zip')==b['candidate_sha256'] and (root/'candidate.zip').stat().st_size==b['candidate_bytes'],'original candidate pin')
 p.require(p.file_digest(root/'candidate-inventory.json')==b['inventory_sha256'] and p.file_digest(p.regular(manifest))==b['manifest_sha256'],'original input pins')
 original=p.read_metadata(manifest);p.require(original.get('status')=='ci-candidate' and original.get('sha256')==b['candidate_sha256'] and original.get('platform') in ('macos-universal','macos-universal2') and original.get('kind')=='namespaced-compiled-fork' and original.get('profileNamespace')=='flapart-native','original unqualified manifest')
 cm=p.regular(root/'chain-manifest.json');p.require(p.file_digest(cm)==chain_pin,'chain manifest pin')
 value=candidate.chain.read_json(cm);p.require(value.get('archive')=={'path':'candidate.zip','sha256':b['candidate_sha256']} and value.get('inventory')=={'path':'candidate-inventory.json','sha256':b['inventory_sha256']} and value.get('tree')=='package' and value.get('archive_prefix')=='Flapart Studio.app','chain exact mapping')
 return candidate.chain.verify(value,root)

def pack(root,manifest,request,chain_pin,output,now):
 started=time.monotonic();root=Path(root);manifest=p.regular(manifest);output=fresh(output)
 p.require(not output.is_relative_to(root) and not root.is_relative_to(output) and not manifest.is_relative_to(output),'output/input overlap')
 original_check(root,request,manifest,chain_pin,now)
 info=candidate.tree_inventory(root);space(output.parent,info['physical_bytes']+MARGIN)
 with tempfile.TemporaryDirectory(prefix='.full-chain-',dir=output.parent) as td:
  stage=Path(td)/'root';stage.mkdir(mode=0o700)
  transport.pack(root,root/'inventory.json',stage/'retained')
  shutil.copyfile(manifest,stage/'installer-original.json');(stage/'installer-original.json').chmod(0o600)
  (stage/'exchange.json').write_bytes(p.encode(context(request,chain_pin)))
  nested=transport.read(stage/'retained/inventory.json',2*1024**2)
  rows=[{'path':path.relative_to(stage).as_posix(),'bytes':path.stat().st_size,'sha256':p.file_digest(path)} for path in sorted(stage.rglob('*')) if path.is_file()]
  outer={'schema':1,'candidate':'retained/'+nested['candidate'],'files':rows};retention().validate_inventory(outer)
  (stage/'inventory.json').write_bytes(p.encode(outer));report=validate_envelope(stage,request,chain_pin,now+int(time.monotonic()-started))
  original_check(root,request,manifest,chain_pin,now+int(time.monotonic()-started))
  stage.rename(output)
 return dict(report,chain_manifest_sha256=chain_pin,native_executed=False,release_qualified=False)

DESCRIPTOR={'schema','kind','request_sha256','chain_manifest_sha256','envelope_inventory_sha256','payload_bytes','files','ciphertext_sha256','ciphertext_bytes','recipient'}
def check_descriptor(value,expected_sha,request,chain_pin):
 p.require(isinstance(value,dict) and set(value)==DESCRIPTOR and type(value['schema']) is int and value['schema']==1 and value['kind']=='flapart-full-chain-transfer','descriptor fields')
 p.require(p.hexstr(expected_sha,64) and p.digest(p.encode(value))==expected_sha,'independent descriptor pin')
 p.require(value['request_sha256']==p.digest(p.encode(request)) and value['chain_manifest_sha256']==chain_pin and value['recipient']==request['fingerprint'],'descriptor exchange identity')
 for k in ('envelope_inventory_sha256','ciphertext_sha256'):p.require(p.hexstr(value[k],64),'descriptor hash')
 p.require(type(value['payload_bytes']) is int and 0<value['payload_bytes']<=MAX_BYTES and type(value['files']) is int and 2<=value['files']<=4096,'descriptor payload bound')
 p.require(type(value['ciphertext_bytes']) is int and 0<value['ciphertext_bytes']<=p.LIMIT,'descriptor ciphertext bound')
 return value

def encrypt(root,request,chain_pin,public_key,output,now):
 started=time.monotonic();output=fresh(output);root=Path(root);p.require(not output.is_relative_to(root),'ciphertext overlaps input')
 report=validate_envelope(root,request,chain_pin,now);public_key=p.regular(public_key);p.require(p.file_digest(public_key)==request['key_sha256'],'request public key bytes')
 space(output.parent,3*report['payload_bytes']+report['largest_file_bytes']+MARGIN)
 with tempfile.TemporaryDirectory(prefix='.encrypt-chain-',dir=output.parent) as td:
  encrypted=Path(td)/'candidate.gpg';result=retention().encrypt(root,root/'inventory.json',public_key,request['fingerprint'],encrypted)
  p.require(result['encrypted_bytes']<=p.LIMIT,'ciphertext exceeds single-asset protocol bound')
  p.require(validate_envelope(root,request,chain_pin,now+int(time.monotonic()-started))==report,'envelope changed during encryption')
  descriptor={'schema':1,'kind':'flapart-full-chain-transfer','request_sha256':p.digest(p.encode(request)),'chain_manifest_sha256':chain_pin,'envelope_inventory_sha256':report['inventory_sha256'],'payload_bytes':report['payload_bytes'],'files':report['files'],'ciphertext_sha256':result['encrypted_sha256'],'ciphertext_bytes':result['encrypted_bytes'],'recipient':request['fingerprint']}
  check_descriptor(descriptor,p.digest(p.encode(descriptor)),request,chain_pin);os.link(encrypted,output)
 return descriptor

def decrypt_restore_admit(encrypted,home,request,chain_pin,descriptor,descriptor_sha256,output,now):
 started=time.monotonic();p.check_request(request,now);check_descriptor(descriptor,descriptor_sha256,request,chain_pin)
 encrypted=p.regular(encrypted);output=fresh(output)
 p.require(encrypted.stat().st_size==descriptor['ciphertext_bytes'] and p.file_digest(encrypted)==descriptor['ciphertext_sha256'],'ciphertext changed')
 # Payload tar, decrypted unique-object tree, restored unique-byte tree coexist.
 space(output.parent,3*descriptor['payload_bytes']+MARGIN)
 with tempfile.TemporaryDirectory(prefix='.receive-chain-',dir=output.parent) as td:
  stage=Path(td)/'root';stage.mkdir(mode=0o700)
  retention(descriptor['payload_bytes']).decrypt(encrypted,descriptor['ciphertext_sha256'],Path(home),request['fingerprint'],stage/'envelope')
  report=validate_envelope(stage/'envelope',request,chain_pin,now+int(time.monotonic()-started))
  p.require(report['inventory_sha256']==descriptor['envelope_inventory_sha256'] and report['payload_bytes']==descriptor['payload_bytes'] and report['files']==descriptor['files'],'decrypted descriptor mismatch')
  transport.restore(stage/'envelope/retained',stage/'recovered')
  admitted=candidate.admit(stage/'recovered',request,stage/'envelope/installer-original.json',chain_pin,encrypted,descriptor['ciphertext_sha256'],now+int(time.monotonic()-started))
  (stage/'admission.json').write_bytes(p.encode(admitted));stage.rename(output)
 return admitted
