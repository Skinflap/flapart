#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch only hash-pinned official KDE SDK archives into an isolated prefix."""
import argparse,pathlib,json,hashlib,urllib.request,concurrent.futures,tarfile,time,posixpath
p=argparse.ArgumentParser();p.add_argument('--lock',type=pathlib.Path,default=pathlib.Path(__file__).with_name('dependencies.lock.json'));p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--cache',required=True,type=pathlib.Path);p.add_argument('--download-only',action='store_true');a=p.parse_args()
a.cache.mkdir(parents=True,exist_ok=True);a.prefix.mkdir(parents=True,exist_ok=True);root=a.prefix.resolve();lock=json.loads(a.lock.read_text());records=lock['packages']
# The Mac Python framework owns a reviewed directory alias used by PyQt packages.
# Install its owning package first so later files populate that same framework.
if lock.get('platform')=='macos':records=sorted(records,key=lambda r:(r['name']!='ext_python',r['name']))
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def fetch(r):
 target=a.cache/(r['name']+'-'+r['version']+'.tar')
 if target.exists() and sha(target)==r['sha256']:return target
 for attempt in range(3):
  try:
   with urllib.request.urlopen(r['url'],timeout=90) as src,target.with_suffix('.partial').open('wb') as out:
    while b:=src.read(1024*1024):out.write(b)
   partial=target.with_suffix('.partial')
   if partial.stat().st_size!=r['bytes'] or sha(partial)!=r['sha256']:raise ValueError('archive hash/size mismatch: '+r['name'])
   partial.replace(target);print('Verified',r['name'],flush=True);return target
  except Exception:
   if attempt==2:raise
   time.sleep(2)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:archives=list(pool.map(fetch,records))
if not a.download_only:
 if not hasattr(tarfile,'data_filter'):raise SystemExit('Use Python3.12+ (or a security-updated Python with tarfile.data_filter) for extraction.')
 # Check the complete archive set BEFORE writing anything to the SDK prefix.
 # Different packages may share identical files, but cannot silently replace bytes.
 if any(root.iterdir()):raise SystemExit('SDK prefix is not empty; use a new isolated prefix.')
 inventory={};duplicates=0
 aliases={'lib/python3.13':'lib/Python.framework/Versions/3.13/lib/python3.13'} if lock.get('platform')=='macos' else {}
 for archive in archives:
  with tarfile.open(archive) as tar:
   for member in tar:
    name=pathlib.PurePosixPath(member.name).as_posix().removeprefix('./')
    if name in ('','.'):continue
    if member.isdir():kind=('directory',)
    elif member.isfile():
     h=hashlib.sha256();stream=tar.extractfile(member)
     while b:=stream.read(1024*1024):h.update(b)
     kind=('file',h.hexdigest())
    elif member.issym():kind=('symlink',member.linkname)
    elif member.islnk():kind=('hardlink',member.linkname)
    else:raise SystemExit('Unsupported SDK archive member: '+name)
    for alias,target in aliases.items():
     if name==alias:
      if kind[0]=='symlink':
       if posixpath.normpath(posixpath.join(posixpath.dirname(alias),kind[1]))!=target:raise SystemExit('Unexpected Python framework alias target')
       kind=('directory',)
      elif kind[0]!='directory':raise SystemExit('Unexpected Python framework alias member type')
      name=target
     elif name.startswith(alias+'/'):name=target+name[len(alias):]
    key=name.casefold() if lock.get('platform') in ('macos','windows') else name
    previous=inventory.get(key)
    if previous and previous[0]!=kind:raise SystemExit('Conflicting SDK member '+name+' in '+previous[1]+' and '+archive.name)
    if previous and kind[0]!='directory':duplicates+=1
    inventory[key]=(kind,archive.name)
 print('Verified archive collision inventory:',len(inventory),'paths;',duplicates,'identical duplicates',flush=True)
 for archive in archives:
  print('Extracting',archive.name,flush=True)
  with tarfile.open(archive) as tar:tar.extractall(root,filter='data')
 (root/'flapart-sdk-inventory.json').write_text(json.dumps({'paths':len(inventory),'identical_duplicates':duplicates,'conflicts':0},indent=2)+'\n')
 (root/'flapart-dependency-lock.json').write_text(a.lock.read_text())
print('Pinned SDK ready:',root,flush=True)
