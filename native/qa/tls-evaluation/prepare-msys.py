#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unpack hash-pinned build-only MSYS tools into a fresh private root; no install scripts."""
import argparse,pathlib,hashlib,json,urllib.request,concurrent.futures,subprocess,shutil,tarfile
p=argparse.ArgumentParser();p.add_argument('--destination',type=pathlib.Path,required=True);p.add_argument('--cache',type=pathlib.Path,required=True);p.add_argument('--sevenzip');a=p.parse_args()
root=a.destination.resolve();assert not root.exists(),'Fresh MSYS root required';a.cache.mkdir(parents=True,exist_ok=True)
rows=json.loads(pathlib.Path(__file__).with_name('msys-tools.lock.json').read_text())['packages']
seven=a.sevenzip or shutil.which('7z') or 'C:/Program Files/7-Zip/7z.exe'
def fetch(row):
 f=a.cache/row['file']
 if not f.exists():
  with urllib.request.urlopen(row['url'],timeout=90) as src,f.open('wb') as dst:shutil.copyfileobj(src,dst)
 assert f.stat().st_size==row['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'],row['name']
 tar=f.with_suffix('')
 with tar.open('wb') as out:subprocess.run([seven,'x','-so',str(f)],stdout=out,stderr=subprocess.PIPE,check=True)
 return tar
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:archives=list(pool.map(fetch,rows))
# Package-manager metadata is retained in the lock, not executed or merged.
inventory={}
for archive in archives:
 with tarfile.open(archive) as t:
  for m in t:
   if m.name.startswith('.'):continue
   path=pathlib.PurePosixPath(m.name);assert not path.is_absolute() and '..' not in path.parts
   assert m.isdir() or m.isfile(),('Unexpected package link/device',m.name)
   if m.isfile():
    digest=hashlib.sha256(t.extractfile(m).read()).hexdigest();key=path.as_posix().casefold()
    assert key not in inventory or inventory[key]==digest,('Package collision',m.name)
    inventory[key]=digest
root.mkdir(parents=True)
for archive in archives:
 with tarfile.open(archive) as t:t.extractall(root,members=[m for m in t if not m.name.startswith('.')],filter='data')
for name in ['etc','tmp','home']: (root/name).mkdir(exist_ok=True)
(root/'flapart-msys-receipt.json').write_text(json.dumps({'packages':rows,'files_verified':len(inventory),'install_scripts_executed':False,'build_only_not_for_runtime_distribution':True},indent=2)+'\n')
print('Verified isolated MSYS tools:',len(rows),'packages;',len(inventory),'files')
