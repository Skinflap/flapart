#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve only the pinned upstream seed's transitive dependency graph."""
import pathlib,json,urllib.request,urllib.parse,concurrent.futures,argparse
p=argparse.ArgumentParser();p.add_argument('--platform',choices=['macos','windows'],default='macos');p.add_argument('--output',type=pathlib.Path,default=pathlib.Path('dependencies.lock.json'));a=p.parse_args()
base='https://invent.kde.org/api/v4/projects/teams%2Fci-artifacts%2Fkrita-'+a.platform+'/'
cutoff='2026-09-30T23:59:59Z';seed=json.loads(pathlib.Path(__file__).with_name('dependency-seeds.json').read_text());pending=set(seed['platforms'][a.platform]);records={}
def get(url):return json.load(urllib.request.urlopen(url,timeout=90))
def record(name):
 selected=None
 for page in range(1,100):
  rows=get(base+'packages?per_page=100&package_name='+urllib.parse.quote(name)+'&page='+str(page))
  for row in rows:
   if row['name']==name and row['version'].startswith('master-') and row['created_at']<=cutoff and (selected is None or row['created_at']>selected['created_at']):selected=row
  if len(rows)<100:break
 else:raise RuntimeError('Pagination limit reached for '+name)
 if selected is None:raise RuntimeError('No historical package for required '+name)
 version=selected['version'];url=base+'packages/generic/'+name+'/'+version+'/'
 m=get(url+'metadata.json');files=get(base+'packages/'+str(selected['id'])+'/package_files');f=next(x for x in files if x['file_name']=='archive.tar')
 return {'name':name,'version':version,'url':url+'archive.tar','sha256':f['file_sha256'],'bytes':f['size'],'recipe_commit':m['gitRevision'],'dependencies':m['dependencies'],'runtime_dependencies':m.get('runtime-dependencies',{})}
while pending:
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for r in pool.map(record,sorted(pending)):records[r['name']]=r;print(r['name'],r['version'],flush=True)
 pending={n for r in records.values() for n in list(r['dependencies'])+list(r['runtime_dependencies']) if n not in records}
a.output.write_text(json.dumps({'platform':a.platform,'branch':'master (Qt5 stable)','cutoff':cutoff,'upstream_source_commit':'bd6e8d061d2f0388c5b10278786cf0fe62e3135f','seed_recipe_commit':seed['recipe_commit'],'seed_path':seed['source_path'],'required_roots':seed['platforms'][a.platform],'packages':sorted(records.values(),key=lambda x:x['name'])},indent=2)+'\n')
print(len(records),'packages;',sum(r['bytes'] for r in records.values()),'bytes')
