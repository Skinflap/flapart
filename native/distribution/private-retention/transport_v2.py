#!/usr/bin/env python3
"""Bounded content-addressed private transport; never release qualification."""
import argparse,hashlib,json,os,re,shutil,tempfile
from pathlib import Path
import importlib.util
_spec=importlib.util.spec_from_file_location("transport_retention",Path(__file__).with_name("retain.py"));retain=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(retain)
MAX_PATHS=16384
LOGICAL_LIMIT=32*1024**3
MAX_OBJECTS=4095
MANIFEST_LIMIT=8*1024**2

def check(ok,msg):
 if not ok:raise ValueError(msg)
def encode(x):return (json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
def unique(pairs):
 result={}
 for k,v in pairs:
  check(k not in result,'duplicate JSON key');result[k]=v
 return result
def read(path,limit):
 check(path.stat().st_size<=limit,'manifest too large')
 return json.loads(path.read_bytes(),object_pairs_hook=unique)
def name(value):
 check(isinstance(value,str) and 0<len(value.encode())<=1024,'invalid path length')
 check(not any(ord(x)<32 for x in value) and ':' not in value,'invalid path characters')
 if value!='inventory.json':retain.safe_name(value)
 return value
def rows_checked(rows,candidate,maximum=MAX_PATHS):
 check(isinstance(rows,list) and 2<=len(rows)<=maximum,'invalid path count');seen={};total=0;objects={}
 for r in rows:
  check(isinstance(r,dict) and set(r)=={'path','bytes','sha256'},'invalid row')
  n=name(r['path']);key=n.casefold();check(key not in seen,'duplicate/casefold path');seen[key]=n
  check(type(r['bytes']) is int and 0<=r['bytes']<=retain.LIMIT,'invalid size')
  check(isinstance(r['sha256'],str) and re.fullmatch('[0-9a-f]{64}',r['sha256']),'invalid digest')
  check(r['sha256'] not in objects or objects[r['sha256']]==r['bytes'],'digest size collision')
  objects[r['sha256']]=r['bytes'];total+=r['bytes']
 check(total<=LOGICAL_LIMIT and candidate in seen.values(),'logical limit or candidate missing')
 for key in seen:
  parts=key.split('/')
  check(all('/'.join(parts[:i]) not in seen for i in range(1,len(parts))),'parent collision')
 check(len(objects)<=MAX_OBJECTS and sum(objects.values())<=retain.LIMIT,'unique storage limit')
 return objects,total

def validate_original(obj):
 check(isinstance(obj,dict) and set(obj)=={'schema','candidate','files'} and type(obj['schema']) is int and obj['schema']==1,'invalid original inventory')
 check(isinstance(obj['candidate'],str),'invalid candidate')
 rows_checked(obj['files'],obj['candidate'],MAX_PATHS-1)
 check(all(r['path']!='inventory.json' for r in obj['files']),'reserved inventory path')
 return obj['files']
def input_root(value):
 root=Path(value).absolute()
 for p in (root,*root.parents):check(not p.is_symlink(),'symlink input root/ancestor')
 check(root.is_dir(),'input root absent');return root.resolve(strict=True)

def fresh(output):
 output=Path(output).absolute()
 check(not output.exists() and not output.is_symlink(),'output exists')
 for p in (output.parent,*output.parent.parents):check(not p.is_symlink(),'symlink output parent')
 check(output.parent.is_dir(),'output parent absent');return output

def expose(staged,output):
 output.mkdir(mode=0o700)
 try:
  for child in staged.iterdir():child.rename(output/child.name)
 except BaseException:
  shutil.rmtree(output);raise

def pack(root,inventory,output):
 root=input_root(root);inventory=Path(inventory).absolute();output=fresh(output)
 check(inventory==root/'inventory.json','inventory must be root inventory.json');retain.regular(root,'inventory.json')
 check(not output.is_relative_to(root),'output overlaps input')
 check(inventory.stat().st_size<=MANIFEST_LIMIT,'original inventory too large')
 raw=inventory.read_bytes();check(len(raw)<=MANIFEST_LIMIT,'original inventory too large')
 original=json.loads(raw,object_pairs_hook=unique);rows=list(validate_original(original))
 check(inventory.resolve()==(root/'inventory.json').resolve(),'inventory must be input inventory.json')
 rows.append({'path':'inventory.json','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 objects,total=rows_checked(rows,original['candidate'])
 manifest={'schema':2,'kind':'flapart-private-content-addressed','candidate':original['candidate'],'files':rows,'logical_bytes':total,'unique_bytes':sum(objects.values()),'objects':len(objects)}
 manifest_raw=encode(manifest);check(len(manifest_raw)<=MANIFEST_LIMIT,'transport manifest too large')
 check(sum(objects.values())+len(manifest_raw)<=retain.LIMIT,'stored-byte limit')
 with tempfile.TemporaryDirectory(prefix='.transport-v2-',dir=output.parent) as td:
  staged=Path(td)/'root';staged.mkdir(mode=0o700);(staged/'objects').mkdir(mode=0o700)
  for r in rows:
   source=retain.regular(root,r['path']);check(source.stat().st_size==r['bytes'] and retain.digest(source)==r['sha256'],'source mismatch')
   dest=staged/'objects'/r['sha256']
   if not dest.exists():
    shutil.copyfile(source,dest);dest.chmod(0o600)
    check(dest.stat().st_size==r['bytes'] and retain.digest(dest)==r['sha256'],'source changed during copy')
  (staged/'transport-v2.json').write_bytes(manifest_raw);(staged/'transport-v2.json').chmod(0o600)
  outer={'schema':1,'candidate':'objects/'+next(r['sha256'] for r in rows if r['path']==original['candidate']),'files':[{'path':'objects/'+h,'bytes':size,'sha256':h} for h,size in sorted(objects.items())]+[{'path':'transport-v2.json','bytes':len(manifest_raw),'sha256':hashlib.sha256(manifest_raw).hexdigest()}]}
  retain.validate_inventory(outer);outer_raw=encode(outer);check(len(outer_raw)<=2*1024**2,'outer inventory too large')
  (staged/'inventory.json').write_bytes(outer_raw);(staged/'inventory.json').chmod(0o600)
  expose(staged,output)
 return {'transport_schema':2,'original_paths':len(rows),'objects':len(objects),'logical_bytes':total,'unique_object_bytes':sum(objects.values()),'manifest_bytes':len(manifest_raw),'outer_inventory_bytes':len(outer_raw),'pack_staging_logical_bytes':sum(objects.values())+len(manifest_raw)+len(outer_raw),'stored_bytes':sum(objects.values())+len(manifest_raw),'largest_object_bytes':max(objects.values()),'release_qualified':False}

def restore(root,output):
 root=input_root(root);output=fresh(output);check(not output.is_relative_to(root),'output overlaps input')
 outer=read(retain.regular(root,'inventory.json'),2*1024**2);retain.validate_inventory(outer)
 actual=set()
 for p in root.rglob('*'):
  check(not p.is_symlink(),'transport symlink')
  if p.is_file():actual.add(p.relative_to(root).as_posix())
  else:check(p.is_dir() and p==root/'objects','unexpected directory')
 check(actual=={'inventory.json',*(r['path'] for r in outer['files'])},'extra or missing objects')
 for r in outer['files']:
  p=retain.regular(root,r['path']);check(p.stat().st_size==r['bytes'] and retain.digest(p)==r['sha256'],'outer object mismatch')
 m=read(retain.regular(root,'transport-v2.json'),MANIFEST_LIMIT)
 check(set(m)=={'schema','kind','candidate','files','logical_bytes','unique_bytes','objects'} and type(m['schema']) is int and m['schema']==2 and m['kind']=='flapart-private-content-addressed','invalid transport manifest')
 objects,total=rows_checked(m['files'],m['candidate'])
 check(type(m['logical_bytes']) is int and type(m['unique_bytes']) is int and type(m['objects']) is int and (m['logical_bytes'],m['unique_bytes'],m['objects'])==(total,sum(objects.values()),len(objects)),'manifest totals mismatch')
 check({r['path'] for r in outer['files']}=={'transport-v2.json',*('objects/'+h for h in objects)},'unreferenced or missing object')
 for h,size in objects.items():check((root/'objects'/h).stat().st_size==size and retain.digest(root/'objects'/h)==h,'object digest mismatch')
 inv=next((r for r in m['files'] if r['path']=='inventory.json'),None);check(inv is not None,'original inventory missing')
 original=read(root/'objects'/inv['sha256'],MANIFEST_LIMIT);validate_original(original)
 check(original['candidate']==m['candidate'] and original['files']==[r for r in m['files'] if r['path']!='inventory.json'],'original inventory differs')
 check(outer['candidate']=='objects/'+next(r['sha256'] for r in m['files'] if r['path']==m['candidate']),'outer candidate differs')
 with tempfile.TemporaryDirectory(prefix='.restore-v2-',dir=output.parent) as td:
  staged=Path(td)/'root';staged.mkdir(mode=0o700);copies={}
  for r in m['files']:
   p=staged/r['path'];p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   if r['sha256'] in copies:os.link(copies[r['sha256']],p)
   else:
    shutil.copyfile(root/'objects'/r['sha256'],p);p.chmod(0o600)
    check(p.stat().st_size==r['bytes'] and retain.digest(p)==r['sha256'],'object changed during restoration');copies[r['sha256']]=p
  expose(staged,output)
 return {'restored_paths':len(m['files']),'logical_bytes':total,'unique_copy_bytes':sum(objects.values()),'release_qualified':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['pack','restore']);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 print(json.dumps(pack(a.root,a.root/'inventory.json',a.output) if a.command=='pack' else restore(a.root,a.output)))
if __name__=='__main__':main()
