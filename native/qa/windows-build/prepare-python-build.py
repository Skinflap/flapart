#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin build-only SIP prerequisites in a private target, never global Python."""
import argparse,hashlib,json,pathlib,subprocess,sys,urllib.request,zipfile,stat,shutil,os
p=argparse.ArgumentParser();p.add_argument('--cache',type=pathlib.Path,required=True);p.add_argument('--destination',type=pathlib.Path,required=True);p.add_argument('--offline',action='store_true');a=p.parse_args()
lock=json.loads(pathlib.Path(__file__).with_name('python-build.lock.json').read_text());a.cache.mkdir(parents=True,exist_ok=True)
rows=[r for r in lock['artifacts'] if r['kind']=='bdist_wheel'];assert len(rows)==2
for row in rows:
 path=a.cache/row['filename']
 if not path.exists():
  assert not a.offline,('Missing cached wheel',path)
  with urllib.request.urlopen(row['url'],timeout=90) as response:path.write_bytes(response.read())
 assert path.stat().st_size==row['size'] and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],('Build dependency hash mismatch',path)
receipt=a.destination/'flapart-build-python.json'
if a.destination.exists():
 assert receipt.is_file() and json.loads(receipt.read_text())['wheels']==rows,'Existing build dependency target is not this locked candidate'
else:
 # These pinned pure-Python wheels need no scripts, native code, or pip install.
 stage=a.destination.with_name(a.destination.name+'.staging');assert not stage.exists();stage.mkdir(parents=True)
 seen=set()
 for row in rows:
  with zipfile.ZipFile(a.cache/row['filename']) as z:
   assert sum(i.file_size for i in z.infolist())<40_000_000
   for entry in z.infolist():
    rel=pathlib.PurePosixPath(entry.filename);key=entry.filename.casefold()
    assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in entry.filename and ':' not in entry.filename
    assert not any(part.endswith('.data') for part in rel.parts), 'Wheel data layout needs explicit handling'
    assert not stat.S_ISLNK(entry.external_attr>>16) and key not in seen;seen.add(key)
    dest=stage/rel;assert dest.resolve().is_relative_to(stage.resolve())
    if entry.is_dir():dest.mkdir(parents=True,exist_ok=True)
    else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(entry))
 stage.rename(a.destination)
 receipt.write_text(json.dumps({'build_only':True,'wheels':rows},indent=2)+'\n')
print(a.destination)
