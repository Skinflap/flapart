#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify and unpack portable build tools; does not install Python or alter PATH."""
import argparse,pathlib,json,hashlib,zipfile,urllib.request
p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=pathlib.Path);p.add_argument('--destination',required=True,type=pathlib.Path);p.add_argument('--offline',action='store_true');a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent;records=json.loads((r/'tools.lock.json').read_text())['tools'];a.cache.mkdir(parents=True,exist_ok=True);a.destination.mkdir(parents=True,exist_ok=True)
for x in records:
 if not x['name'].endswith('.zip') or x['name'].startswith('python-'):continue
 path=a.cache/x['name']
 if not path.exists():
  if a.offline:raise SystemExit('Missing cached tool: '+x['name'])
  with urllib.request.urlopen(x['url'],timeout=90) as src,path.open('wb') as dst:
   while b:=src.read(1024*1024):dst.write(b)
 if path.stat().st_size!=x['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=x['sha256']:raise SystemExit('Tool hash mismatch: '+x['name'])
 with zipfile.ZipFile(path) as z:
  for name in z.namelist():
   dest=(a.destination/name).resolve()
   if not dest.is_relative_to(a.destination.resolve()):raise SystemExit('Unsafe archive path')
  z.extractall(a.destination)
 print('Verified/unpacked',x['name'],flush=True)
