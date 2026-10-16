#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch only hash-pinned official KDE SDK archives into an isolated prefix."""
import argparse,pathlib,json,hashlib,urllib.request,concurrent.futures,tarfile,time
p=argparse.ArgumentParser();p.add_argument('--lock',type=pathlib.Path,default=pathlib.Path(__file__).with_name('dependencies.lock.json'));p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--cache',required=True,type=pathlib.Path);p.add_argument('--download-only',action='store_true');a=p.parse_args()
a.cache.mkdir(parents=True,exist_ok=True);a.prefix.mkdir(parents=True,exist_ok=True);root=a.prefix.resolve();records=json.loads(a.lock.read_text())['packages']
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
 for archive in archives:
  print('Extracting',archive.name,flush=True)
  with tarfile.open(archive) as tar:tar.extractall(root,filter='data')
 (root/'flapart-dependency-lock.json').write_text(a.lock.read_text())
print('Pinned SDK ready:',root,flush=True)
