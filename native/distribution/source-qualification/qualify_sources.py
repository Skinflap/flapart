#!/usr/bin/env python3
"""Fail-closed, read-only source correspondence producer for Windows/Mac archives."""
import argparse,hashlib,json,re,stat,zipfile,posixpath
from pathlib import Path,PurePosixPath
from native_metadata import parse,check

PLATFORMS={'windows-x86_64':('windows',{'x86_64'}),'macos-x86_64':('macos',{'x86_64'}),'macos-arm64':('macos',{'arm64'}),'macos-universal2':('macos',{'x86_64','arm64'})}
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def safe(name):return isinstance(name,str) and bool(name) and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name and not any(ord(c)<32 for c in name)
class Evidence:
 def __init__(self,root):self.root=Path(root).resolve();self.artifacts={}
 def path(self,ref):
  check(isinstance(ref,dict) and set(ref)=={'path','sha256'} and safe(ref['path']),'Invalid artifact reference');path=(self.root/ref['path']).resolve();check(path.is_relative_to(self.root) and path.is_file(),'Artifact missing or outside evidence root');check(re.fullmatch('[a-f0-9]{64}',ref['sha256']) and sha(path)==ref['sha256'],'Artifact hash mismatch: '+ref['path']);return path
 def json(self,ref):
  path=self.path(ref);check(path.stat().st_size<=64*1024**2,'Oversized JSON evidence');return json.loads(path.read_text())
 def artifact(self,ref,kind):
  self.path(ref);key=(ref['path'],ref['sha256'],kind);self.artifacts[key]={'kind':kind,**ref};return ref

def critical(path,package=''):
 name=PurePosixPath(path).name.lower()
 # Exact SDK PyQt bindings are preserved, not fictional QtNetwork rebuilds.
 if package in ('ext_pyqt5','ext_python-modules') and re.fullmatch(r'qtnetwork(?:\.pyd|\.(?:abi3|cpython-[a-z0-9_-]+)\.so)',name):return False
 return package in ('ext_openssl','ext_python') or bool(re.search(r'krita|q(?:t[56]?)?network|bearer|(?:lib)?ssl|(?:lib)?crypto|python|libgcc|libstdc\+\+|libwinpthread|msvcp|vcruntime|clang_rt|libc\+\+',name))

SYSTEM_DLLS=set(('advapi32 bcrypt bcryptprimitives cabinet cfgmgr32 comctl32 comdlg32 crypt32 cryptbase cryptsp d2d1 d3d9 d3d11 d3d12 dcomp dbghelp dnsapi dwrite dwmapi dxgi dxguid gdi32 glu32 hid imm32 iphlpapi kernel32 kernelbase mpr mscms msimg32 msvcrt ncrypt netapi32 ntdll ole32 oleaut32 opengl32 powrprof propsys psapi rpcrt4 secur32 setupapi shell32 shlwapi synchronization ucrtbase user32 userenv usp10 uxtheme version windowscodecs winhttp wininet winmm wintrust ws2_32 wtsapi32').split())
def system_import(name,family):
 if family=='macos':return name.startswith(('/System/Library/','/usr/lib/')) and '..' not in PurePosixPath(name).parts
 lower=name.lower()
 if lower=='d3dcompiler_47.dll':return True  # Windows 10/11 OS component; reviewed target evidence still required below.
 return lower=='winspool.drv' or bool(re.fullmatch(r'(?:api-ms-win-|ext-ms-win-)[a-z0-9-]+\.dll',lower)) or lower.endswith('.dll') and lower[:-4] in SYSTEM_DLLS

def produce(archive,pin,platform,inputs,evidence):
 check(platform in PLATFORMS,'Unknown canonical platform');family,arches=PLATFORMS[platform];check(sha(archive)==pin,'Candidate archive SHA mismatch');e=Evidence(evidence)
 required={'inventory','correspondence','sdk_lock','source_plan','url_receipt','recipes','selections'};check(set(inputs)==required,'Missing pinned producer inputs');docs={k:e.json(v) for k,v in inputs.items()}
 inventory=docs['inventory'];check(inventory['platform']==platform,'Inventory platform mismatch');lock=docs['sdk_lock'];check(lock['platform']==family,'SDK lock platform mismatch');review=docs['selections'];check(review['platform']==family,'Selection platform mismatch')
 records=inventory['files'];index={r['path']:r for r in records};check(len(index)==len(records),'Duplicate inventory paths');output_files=[];natives={};assets=[];unresolved=[]
 with zipfile.ZipFile(archive) as z:
  entries=[i for i in z.infolist() if not i.is_dir()];check(len(entries)<=100000 and sum(i.file_size for i in entries)<=8*1024**3,'Oversized candidate archive');check(len({i.filename for i in entries})==len(entries) and set(index)=={i.filename for i in entries},'Archive/inventory file set mismatch')
  for info in entries:
   name=info.filename;check(safe(name),'Unsafe archive path');record=index[name];mode=(info.external_attr>>16)&0o170000
   if mode==stat.S_IFLNK:
    check(info.file_size<=4096,'Oversized symlink');target=z.read(info).decode();check(record.get('symlink')==target,'Symlink inventory mismatch');resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),target));check(not target.startswith('/') and '\\' not in target and safe(resolved) and (resolved in index or any(n.startswith(resolved+'/') for n in index)),'Symlink escapes archive or is dangling');output_files.append(record);continue
   check(mode in (0,stat.S_IFREG),'Unsupported archive file type');data=z.read(info);value=hashlib.sha256(data).hexdigest();check(record.get('sha256')==value and record.get('bytes')==len(data),'Inventory byte mismatch: '+name)
   row={'path':name,'bytes':len(data),'sha256':value}
   try:metadata=parse(data)
   except ValueError as error:unresolved.append({'path':name,'reason':'native-metadata-invalid','detail':str(error)});metadata=None
   if metadata:
    row.update(metadata);natives[name]=row
    if set(metadata['architectures'])!=arches or metadata['format']!=('pe' if family=='windows' else 'macho'):unresolved.append({'path':name,'reason':'native-platform-slices-mismatch'})
   else:
    assets.append(name)
    if PurePosixPath(name).suffix.lower() in ('.dll','.exe','.pyd','.dylib','.so') or '/Contents/MacOS/' in name:unresolved.append({'path':name,'reason':'native-looking-file-has-no-supported-native-header'})
   output_files.append(row)
 check(natives,'No native binaries in candidate')
 packages={(p['name'],p['recipe_commit'],p['sha256']) for p in lock['packages']};origins=docs['correspondence'];source_plan=docs['source_plan'];urls=docs['url_receipt'];recipes=docs['recipes'];native_sources={};matched=[]
 selections={(p['package'],p['recipe_commit']):p for p in review.get('packages',[])};check(len(selections)==len(review.get('packages',[])),'Ambiguous selected package recipes')
 def source_artifacts(selection,package,commit):
  check(selection['platform']==family,'Wrong recipe branch platform');recipe=selection['recipe'];check(any(r['commit']==commit and r['sha256']==recipe['sha256'] and PurePosixPath(recipe['path']).name==r['archive'] for r in recipes),'Recipe does not match exact recipe archive')
  branch=e.json(selection['branch_evidence']);check(branch['platform']==family and branch['package']==package and branch['recipe_commit']==commit and branch['recipe_sha256']==recipe['sha256'] and isinstance(branch.get('selection_basis'),str) and branch['selection_basis'].strip(),'Missing reviewed platform recipe branch evidence')
  plans=[p for p in source_plan if p['platform']==family and p['name']==package and p['recipe_commit']==commit];check(len(plans)==1,'Missing/ambiguous platform source plan');plan=plans[0];sources=selection['sources'];check(sources and branch['selected_sources']==sources,'Source selections differ from reviewed branch')
  refs=[e.artifact(recipe,'recipe')]
  for source in sources:
   artifact=source['artifact'];path=e.path(artifact)
   if source.get('kind','url')=='url':
    entry={k:source[k] for k in ('url','algorithm','digest')};check(entry in plan['urls_all_platform_branches'],'Source is not from selected recipe plan')
    check(any(all(u.get(k)==v for k,v in entry.items()) and u.get('sha256')==artifact['sha256'] and u.get('path')==artifact['path'] and u.get('status') in ('verified-existing','verified-new') for u in urls),'Missing verified URL source receipt')
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,source['algorithm'].lower()).hexdigest()
    check(actual==source['digest'],'Original recipe source digest mismatch')
   else:
    check(source['kind']=='git' and {'url':source['url'],'revision':source['revision']} in plan['git_all_platform_branches'],'Git source not in platform recipe')
    checkout=e.json(source['checkout_provenance']);check(checkout['url']==source['url'] and checkout['requested_revision']==source['revision'] and re.fullmatch('[0-9a-f]{40}',checkout['resolved_commit']) and checkout['snapshot_sha256']==artifact['sha256'],'Missing exact git checkout/snapshot provenance');e.artifact(source['checkout_provenance'],'provenance')
   refs.append(e.artifact(artifact,'source'))
  notices=selection.get('license_notices',[]);check(notices,'Missing actual license/notice artifacts')
  refs += [e.artifact(r,'license') for r in notices];e.artifact(selection['branch_evidence'],'provenance');return refs
 def built(name,row,ref):
  proof=e.json(ref);check(proof['target_platform']==platform and {'archive_path':name,'sha256':row['sha256']} in proof['outputs'],'Rebuild provenance output is not this packaged binary')
  check(proof.get('component') and proof.get('commands') and proof.get('build_environment'),'Missing rebuild command/environment provenance')
  e.artifact(proof['build_log'],'provenance');e.artifact(proof['toolchain'],'provenance');e.artifact(ref,'provenance');refs=[]
  for kind,key in [('source','sources'),('license','license_notices'),('recipe','recipes')]:
   check(proof.get(key),'Rebuilt component lacks '+key);refs.extend(e.artifact(r,kind) for r in proof[key])
  return refs
 for name,row in natives.items():
  try:
   rebuild=review.get('rebuilt',{}).get(name)
   if rebuild:
    native_sources[name]=built(name,row,rebuild);matched.append({'path':name,'method':'explicit-rebuilt-output','sha256':row['sha256']});continue
   candidates=[o for o in origins if o['sha256']==row['sha256']];method='byte-exact-sha256'
   if not candidates and row['macho_uuids'] and len(row['macho_uuids'])==len(row['architectures']):
    candidates=[o for o in origins if sorted(o.get('macho_uuids',[]))==row['macho_uuids']];method='all-slice-uuid-with-transformation'
   identities={(o['package'],o['recipe_commit'],o['archive_sha256']) for o in candidates};check(len(identities)==1,'Unknown or ambiguous binary origin; explicit rebuilt provenance required');package,commit,sdk_sha=next(iter(identities));check((package,commit,sdk_sha) in packages,'Correspondence does not match pinned SDK lock')
   check(not critical(name,package),'Rebuilt/maintained application, TLS, Python, QtNetwork/bearer or toolchain provenance pending')
   if method!='byte-exact-sha256':
    ref=review.get('transformations',{}).get(name);check(ref,'UUID identity alone cannot prove unchanged code');proof=e.json(ref)
    check(proof['target_platform']==platform and proof['output_sha256']==row['sha256'] and proof['input_sha256'] in {o['sha256'] for o in candidates} and proof.get('commands'),'Missing controlled package transformation provenance');e.artifact(proof['log'],'provenance');e.artifact(ref,'provenance')
   selection=selections.get((package,commit));check(selection,'Platform-specific source/notice selection pending');native_sources[name]=source_artifacts(selection,package,commit);matched.append({'path':name,'method':method,'package':package,'recipe_commit':commit,'sdk_archive_sha256':sdk_sha})
  except (ValueError,KeyError,TypeError,OSError) as error:unresolved.append({'path':name,'reason':'source-provenance-pending','detail':str(error)})
 # Exact import resolution is reviewed separately from origin correspondence.
 for name,row in natives.items():
  resolutions=review.get('dependencies',{}).get(name,{})
  for dependency in row['native_dependencies']:
   try:
    resolution=resolutions.get(dependency);check(resolution,'Unresolved native import')
    if 'archive_path' in resolution:
     target=resolution['archive_path'];check(target in natives,'Imported library absent from packaged native inventory')
     if family=='windows':check(PurePosixPath(target).name.lower()==dependency.lower(),'PE import resolves to a differently named library')
     else:
      aliases=[]
      for alias in index:
       current=alias;seen=set()
       while 'symlink' in index.get(current,{}):
        check(current not in seen,'Cyclic package alias');seen.add(current);current=posixpath.normpath(posixpath.join(posixpath.dirname(current),index[current]['symlink']))
       if current==target:aliases.append(alias)
      if dependency.startswith('@rpath/'):check(any(alias.endswith('/'+dependency[7:]) for alias in aliases),'RPATH import does not match target alias')
      elif dependency.startswith('@loader_path/'):check(posixpath.normpath(posixpath.join(posixpath.dirname(name),dependency[13:])) in aliases,'Loader-relative import target mismatch')
      elif dependency.startswith('@executable_path/'):
       entry=inventory.get('entrypoint');check(entry and posixpath.normpath(posixpath.join(posixpath.dirname(entry),dependency[17:])) in aliases,'Executable-relative import target mismatch')
      else:check(False,'Absolute/unknown bundled dependency needs actual relocation')
    else:
     proof=e.json(resolution['system_evidence']);check(proof['platform']==family and proof['dependency']==dependency and proof.get('basis'),'Missing reviewed system import evidence')
     allowed=system_import(dependency,family) and (family=='macos' or proof.get('windows_system_component') is True)
     if family=='windows' and dependency.lower()=='d3dcompiler_47.dll':allowed=allowed and proof.get('minimum_windows') in ('10','11')
     check(allowed,'Non-system dependency cannot be exempted');e.artifact(resolution['system_evidence'],'provenance')
   except (ValueError,KeyError,TypeError,OSError) as error:unresolved.append({'path':name,'dependency':dependency,'reason':'dependency-unresolved','detail':str(error)})
 for name in assets:
  try:
   notices=review.get('asset_notices',{}).get(name);check(notices,'Non-native asset notice coverage pending')
   for ref in notices:e.artifact(ref,'license')
  except (ValueError,KeyError,TypeError,OSError) as error:unresolved.append({'path':name,'reason':'asset-notices-pending','detail':str(error)})
 check(sha(archive)==pin,'Archive changed during source qualification')
 common={'payload_sha256':pin,'target_platform':platform};closure={**common,'schema':2,'complete':not unresolved and set(native_sources)==set(natives),'artifacts':list(e.artifacts.values()),'native_sources':native_sources,'unresolved':unresolved,'matched':matched,'input_refs':inputs,'release_qualified':False}
 return {**common,'platform':platform,'runtime_collected':True,'files':output_files},closure

def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--platform',choices=PLATFORMS,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--evidence-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();check(not a.output.exists(),'Output directory must be new')
 inventory,closure=produce(a.archive,a.sha256,a.platform,json.loads(a.inputs.read_text()),a.evidence_root);a.output.mkdir(parents=True)
 for name,data in [('inventory',inventory),('source_closure',closure)]:(a.output/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 print(json.dumps({'complete':closure['complete'],'native_binaries':len(closure['matched']),'unresolved':len(closure['unresolved']),'release_qualified':False}));return 0 if closure['complete'] else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,KeyError,TypeError,OSError) as error:raise SystemExit('Source qualification refused: '+str(error))
