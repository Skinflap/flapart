#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve a historical official KDE SDK snapshot to immutable archive hashes."""
import pathlib,json,urllib.request,concurrent.futures,argparse
p=argparse.ArgumentParser();p.add_argument('--platform',choices=['macos','windows'],default='macos');p.add_argument('--output',type=pathlib.Path,default=pathlib.Path('dependencies.lock.json'));a=p.parse_args()
base='https://invent.kde.org/api/v4/projects/teams%2Fci-artifacts%2Fkrita-'+a.platform+'/'
cutoff='2026-09-30T10:59:49Z';packages=[]
for page in range(1,40):
 rows=json.load(urllib.request.urlopen(base+'packages?per_page=100&page='+str(page),timeout=90));packages.extend(rows)
 if len(rows)<100:break
selected={}
for row in packages:
 if not row['version'].startswith('master-') or row['created_at']>cutoff or 'debug' in row['name'] or 'asan' in row['name']:continue
 if row['name'] not in selected or row['created_at']>selected[row['name']]['created_at']:selected[row['name']]=row

def record(row):
 name=row['name'];version=row['version'];url=base+'packages/generic/'+name+'/'+version+'/'
 m=json.load(urllib.request.urlopen(url+'metadata.json',timeout=90))
 files=json.load(urllib.request.urlopen(base+'packages/'+str(row['id'])+'/package_files',timeout=90));f=next(x for x in files if x['file_name']=='archive.tar')
 return {'name':name,'version':version,'url':url+'archive.tar','sha256':f['file_sha256'],'bytes':f['size'],'recipe_commit':m['gitRevision'],'dependencies':m['dependencies']}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(record,sorted(selected.values(),key=lambda x:x['name'])))
a.output.write_text(json.dumps({'platform':a.platform,'branch':'master (Qt5 stable)','cutoff':cutoff,'upstream_source_commit':'bd6e8d061d2f0388c5b10278786cf0fe62e3135f','packages':records},indent=2)+'\n')
print(len(records),'packages;',sum(r['bytes'] for r in records),'bytes; lock',a.output)
