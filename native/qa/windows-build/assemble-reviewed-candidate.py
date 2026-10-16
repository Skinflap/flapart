#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a fresh Windows candidate with exact notices; never qualify a release."""
import argparse,hashlib,json,stat,zipfile
from pathlib import Path,PurePosixPath

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def relative(name):
 p=PurePosixPath(name)
 require(bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name and not any(ord(c)<32 for c in name),'Unsafe path')
 require(str(p)==name.rstrip('/'),'Noncanonical path')
 for part in p.parts:
  require(not part.endswith(('.', ' ')),'Windows filename has trailing dot or space')
  stem=part.split('.',1)[0].upper()
  require(stem not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]},'Reserved Windows filename')
 return p

def assemble(archive,pin,notices,notice_pin,output):
 require(not output.exists(),'Use a fresh output directory')
 require(sha(archive)==pin,'Archive pin mismatch')
 manifest=notices/'notice-manifest.json';require(sha(manifest)==notice_pin,'Notice manifest pin mismatch')
 rows=json.loads(manifest.read_text())['files'];selected={};case=set()
 for r in rows:
  name=r['path'];p=relative(name)
  require(name in ('CREDITS.html','credits.css') or p.parts[0]=='third-party-notices','Unexpected notice payload')
  require(name.casefold() not in case,'Duplicate notice');case.add(name.casefold())
  src=notices/name
  require(src.is_file() and not any(x.is_symlink() for x in (src,*src.parents)),'Linked notice input')
  require(src.stat().st_size==r['bytes'] and sha(src)==r['sha256'],'Notice bytes changed');selected[name]=r
 require({'CREDITS.html','credits.css'}<=set(selected),'Missing credits presentation')
 removed='Flapart-Studio/bin/symsrv.yes';members={};before={}
 with zipfile.ZipFile(archive) as z:
  require(len(z.infolist())<=100000 and sum(i.file_size for i in z.infolist())<=8*1024**3,'Oversized candidate')
  seen=set()
  for i in z.infolist():
   p=relative(i.filename);require(p.parts[0]=='Flapart-Studio','Unexpected candidate root')
   require(i.filename.rstrip('/').casefold() not in seen,'Duplicate candidate path');seen.add(i.filename.rstrip('/').casefold())
   require(stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR),'Linked/special candidate member')
   if i.is_dir():continue
   require(not i.filename.startswith('Flapart-Studio/licenses/'),'Existing notice tree requires explicit review')
   members[i.filename]=i
  require('Flapart-Studio/bin/krita.exe' in members,'Missing native entrypoint')
  output.mkdir(parents=True);target=output/'Flapart-Studio.zip';inventory=[]
  with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as dest:
   def write(name,data):
    info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
    dest.writestr(info,data);inventory.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
   for name in sorted(members):
    raw=z.read(name);before[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    if name!=removed:write(name,raw)
   for name in sorted(selected):
    r=selected[name];raw=(notices/name).read_bytes();require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'Notice changed during copy');write('Flapart-Studio/licenses/'+name,raw)
 require(sha(archive)==pin and sha(manifest)==notice_pin,'Inputs changed during assembly')
 with zipfile.ZipFile(target) as z:
  require(set(z.namelist())=={r['path'] for r in inventory},'Output inventory mismatch')
  for r in inventory:require(hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256'],'Output member mismatch')
 result={'schema':1,'original_archive_sha256':pin,'notice_manifest_sha256':notice_pin,'archive_sha256':sha(target),'bytes':target.stat().st_size,'removed':[{'path':removed,**before[removed]}] if removed in before else [],'preserved_original_files':len(before)-(removed in before),'added_notice_files':len(selected),'terms_accepted':False,'runtime_tested':False,'release_qualified':False,'files':inventory}
 (output/'assembly.json').write_text(json.dumps(result,indent=2)+'\n');return result

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('archive','notices','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--archive-sha256',required=True);p.add_argument('--notice-manifest-sha256',required=True);a=p.parse_args()
 r=assemble(a.archive,a.archive_sha256,a.notices,a.notice_manifest_sha256,a.output)
 print(json.dumps({k:v for k,v in r.items() if k!='files'}))
if __name__=='__main__':main()
