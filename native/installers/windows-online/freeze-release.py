#!/usr/bin/env python3
"""Freeze a locally shipped installer pin only after real package evidence exists.
Does not build, sign, upload, or claim tests were run. Run in release preparation.
"""
import argparse,hashlib,json,re,zipfile,struct,stat,posixpath
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
PLUGIN='7401d694e5a0b408663f87548cc856f7f39de2790bbdc9f19021e6610e5094c2'
# Final-release receipt contract. CI candidate flows do not call this gate.
# Evidence schema v2:
# {schema:2, payload_sha256, platform, profile_namespace, signature?(Mac),
#  receipts:{inventory:{path,sha256},source_closure:{path,sha256},
#            relocation:[ref],installer:[ref],tls:[ref],python:[ref]}}
# Every receipt pins payload_sha256 and target_platform. Native receipts also
# record process_architecture, hardware_architecture, execution_mode and runtime_scope (relocated-package/installed-runtime).
# Universal2 requires a separate real run on each architecture. Receipt hashes
# attest reviewed captured data, not proof that arbitrary JSON is trustworthy.
PLATFORMS={'windows-x86_64':('windows-x86_64',{'x86_64'}),
 'macos-x86_64':('macos-x86_64',{'x86_64'}),'macos-arm64':('macos-arm64',{'arm64'}),
 'macos-universal':('macos-universal2',{'x86_64','arm64'}),
 'macos-universal2':('macos-universal2',{'x86_64','arm64'})}
def binary_architectures(data):
 # Parse CPU fields rather than treating Java CAFEBABE as a universal binary.
 cpu={0x1000007:'x86_64',0x100000c:'arm64'}
 if data[:2]==b'MZ':
  require(len(data)>=64,'Truncated PE header');offset=struct.unpack_from('<I',data,60)[0]
  require(offset+6<=len(data) and data[offset:offset+4]==b'PE\0\0','Invalid PE header')
  machine=struct.unpack_from('<H',data,offset+4)[0]
  require(machine in (0x8664,0xaa64),'Unsupported PE architecture');return {0x8664:'x86_64',0xaa64:'arm64'}[machine],
 thin={b'\xfe\xed\xfa\xcf':'>',b'\xcf\xfa\xed\xfe':'<',b'\xfe\xed\xfa\xce':'>',b'\xce\xfa\xed\xfe':'<'}
 if data[:4] in thin:
  require(len(data)>=28,'Truncated Mach-O header');value=struct.unpack_from(thin[data[:4]]+'I',data,4)[0]
  require(value in cpu,'Unsupported Mach-O architecture');return cpu[value],
 fat={b'\xca\xfe\xba\xbe':('>',20),b'\xbe\xba\xfe\xca':('<',20),b'\xca\xfe\xba\xbf':('>',32),b'\xbf\xba\xfe\xca':('<',32)}
 if data[:4] in fat and len(data)>=8:
  endian,stride=fat[data[:4]];count=struct.unpack_from(endian+'I',data,4)[0]
  if not 1<=count<=16:return () # Java class version, not a fat architecture table.
  require(len(data)>=8+stride*count,'Truncated fat Mach-O table');arches=[]
  for i in range(count):
   base=8+i*stride;value=struct.unpack_from(endian+'I',data,base)[0]
   require(value in cpu,'Unsupported fat Mach-O architecture')
   offset,size=struct.unpack_from(endian+('II' if stride==20 else 'QQ'),data,base+8)
   require(offset>=8+stride*count and size>=28 and offset+size<=len(data),'Invalid fat Mach-O slice bounds')
   require(binary_architectures(data[offset:offset+size])==(cpu[value],),'Fat Mach-O slice CPU mismatch');arches.append(cpu[value])
  require(len(set(arches))==len(arches),'Duplicate fat Mach-O architecture');return tuple(arches)
 return ()
def require(value,message):
 if not value:raise ValueError(message)
def file_hash(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def referenced(ref,root,json_document=True):
 require(isinstance(ref,dict) and set(ref)=={'path','sha256'},'Use a path/hash receipt reference')
 name=ref['path'];require(isinstance(name,str) and name and '\\' not in name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,'Unsafe evidence reference')
 path=(root/name).resolve();require(path.is_relative_to(root) and path.is_file(),'Missing/outside evidence file')
 require(re.fullmatch('[a-f0-9]{64}',str(ref['sha256'])) and file_hash(path)==ref['sha256'],'Evidence file hash mismatch')
 if not json_document:return path
 require(path.stat().st_size<=4*1024**2,'Oversized receipt')
 data=json.loads(path.read_text());require(isinstance(data,dict),'Receipt must be an object');return data

def version_number(value,label):
 match=re.search(r'(?:^|\s)(\d+)\.(\d+)\.(\d+)(?:\s|$)',str(value))
 require(match is not None,'Missing '+label+' version');return tuple(map(int,match.groups()))

def validate_evidence(archive,evidence,platform,digest,evidence_root):
 require(platform in PLATFORMS,'Unknown platform')
 target,architectures=PLATFORMS[platform];root=evidence_root.resolve()
 require(evidence.get('schema')==2,'Final release needs schema2 structured receipts')
 require(evidence.get('payload_sha256')==digest and evidence.get('platform') in (target,platform) and evidence.get('profile_namespace')=='flapart-native','Evidence must pin this exact platform and archive')
 refs=evidence.get('receipts');require(isinstance(refs,dict) and set(refs)=={'inventory','source_closure','relocation','installer','tls','python'},'Missing final release receipt set')
 def bound(ref):
  data=referenced(ref,root)
  require(data.get('payload_sha256')==digest and data.get('target_platform')==target,'Receipt belongs to a different archive/platform')
  return data
 inventory=bound(refs['inventory']);require(inventory.get('platform')==target and inventory.get('runtime_collected') is True,'Missing collected runtime inventory')
 entries=inventory.get('files');require(isinstance(entries,list) and entries,'Missing package file inventory')
 indexed={}
 for item in entries:
  require(isinstance(item,dict) and isinstance(item.get('path'),str) and item['path'] not in indexed,'Invalid/duplicate inventory entry');indexed[item['path']]=item
 package_hashes={};native=set();symlinks={}
 with zipfile.ZipFile(archive) as z:
  files=[i for i in z.infolist() if not i.is_dir()]
  require(len(files)<=100000 and sum(i.file_size for i in files)<=8*1024**3,'Oversized runtime')
  require(len({i.filename for i in files})==len(files) and set(indexed)=={i.filename for i in files},'Inventory does not cover exact archive file set')
  for item in files:
   record=indexed[item.filename];mode=(item.external_attr>>16)&0o170000
   if mode==stat.S_IFLNK:
    require(target.startswith('macos') and item.file_size<=4096,'Invalid runtime symlink')
    link=z.read(item).decode('utf-8');require(record.get('symlink')==link and link and not link.startswith('/') and '\\' not in link,'Symlink inventory mismatch')
    resolved=posixpath.normpath(posixpath.join(posixpath.dirname(item.filename),link))
    require(resolved.startswith('Flapart Studio.app/') and (resolved in indexed or any(n.startswith(resolved+'/') for n in indexed)),'Symlink escapes bundle or is dangling')
    symlinks[item.filename]=link
    continue
   require(mode in (0,stat.S_IFREG) and 'symlink' not in record,'Unsupported runtime file type')
   with z.open(item) as stream:
    head=stream.read(4);sha=hashlib.sha256(head)
    while block:=stream.read(1024*1024):sha.update(block)
   value=sha.hexdigest();package_hashes[item.filename]=value
   require(record.get('sha256')==value and record.get('bytes')==item.file_size,'Inventory file differs from archive')
   arches=binary_architectures(z.read(item)) if head[:2]==b'MZ' or head in (b'\xfe\xed\xfa\xce',b'\xce\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf',b'\xbf\xba\xfe\xca') else ()
   if arches:
    native.add(item.filename)
    require(set(arches)==architectures and set(record.get('architectures',[]))==architectures,'Native binary architecture/slice mismatch')
    imports=record.get('native_dependencies');require(isinstance(imports,list) and all(isinstance(n,str) for n in imports),'Missing native dependency audit')
    require(not any(re.search(r'(?:libssl|libcrypto)[^/\\]*1[._-][01]|ssleay32|libeay32',n,re.I) for n in imports),'Legacy OpenSSL import in packaged native binary')
 # Resolve chains using filesystem order: symlink directories precede '..'.
 for name in symlinks:
  pending=name.split('/');parts=[];hops=0
  while pending:
   part=pending.pop(0)
   if part in ('','.'):continue
   if part=='..':
    require(len(parts)>1,'Symlink traversal escapes app bundle');parts.pop();continue
   parts.append(part);current='/'.join(parts)
   if current in symlinks:
    hops+=1;require(hops<=40,'Cyclic/excessive runtime symlink chain')
    parts.pop();pending=symlinks[current].split('/')+pending
  resolved='/'.join(parts)
  require(resolved.startswith('Flapart Studio.app/') and (resolved in package_hashes or any(n.startswith(resolved+'/') for n in indexed)),'Dangling resolved runtime symlink')
 require(native,'No native runtime binaries in inventory')
 closure=bound(refs['source_closure']);require(closure.get('complete') is True,'Source closure is incomplete')
 artifacts=closure.get('artifacts');require(isinstance(artifacts,list),'Missing source closure artifacts');kinds=set()
 for artifact in artifacts:
  require(isinstance(artifact,dict) and set(artifact)=={'kind','path','sha256'},'Invalid source closure artifact')
  kinds.add(artifact['kind']);referenced({k:artifact[k] for k in ('path','sha256')},root,False)
 require({'source','license','recipe'}<=kinds,'Source closure needs source, license and build recipe files')
 mappings=closure.get('native_sources');require(isinstance(mappings,dict) and set(mappings)==native,'Every packaged native binary needs corresponding source closure')
 artifact_keys={(a['path'],a['sha256']):a['kind'] for a in artifacts}
 for path,links in mappings.items():
  require(isinstance(links,list),'Invalid native source mapping');mapped=set()
  for link in links:
   require(isinstance(link,dict) and set(link)=={'path','sha256'} and (link['path'],link['sha256']) in artifact_keys,'Unknown source artifact mapping')
   mapped.add(artifact_keys[link['path'],link['sha256']])
  require({'source','license','recipe'}<=mapped,'Native binary lacks source/license/recipe mapping')
 collected={}
 for kind in ('relocation','installer','tls','python'):
  rows=refs[kind];require(isinstance(rows,list) and len(rows)==len(architectures),'Missing per-architecture '+kind+' evidence');runs={}
  for ref in rows:
   data=bound(ref);arch=data.get('process_architecture')
   require(arch in architectures and arch not in runs,'Duplicate/wrong native test architecture')
   require(data.get('native_execution') is True and data.get('runtime_scope') in ('relocated-package','installed-runtime'),'SDK/synthetic evidence is not final runtime qualification')
   hardware=data.get('hardware_architecture');mode=data.get('execution_mode')
   require(hardware in ('x86_64','arm64') and (mode=='native' and hardware==arch or mode=='translated' and target.startswith('macos') and hardware=='arm64' and arch=='x86_64'),'Missing/inconsistent process vs hardware execution evidence')
   runs[arch]=data
  require(set(runs)==architectures,'Not all architectures were executed');collected[kind]=runs
 for arch in architectures:
  relocation=collected['relocation'][arch]
  for key in ('relocated_package_test','compiled_fork','original_krita_sentinels_preserved','build_environment_absent'):
   require(relocation.get(key) is True,'Missing relocation gate: '+key)
  installer=collected['installer'][arch]
  require(installer['runtime_scope']=='installed-runtime','Installer proof must use actual installed launcher')
  for key in ('installer_passed','native_runtime_tested','profile_isolation_verified','ordinary_krita_unchanged','native_canvas_png_kra_passed','studio_menu_reopens','failed_upgrade_preserved_receipt','failed_upgrade_preserved_artwork_and_settings','successful_upgrade_preserved_artwork_and_settings','previous_runtime_retained','upgraded_runtime_tested','upgraded_native_child_exit_observed'):
   require(installer.get(key) is True,'Missing installed-launcher gate: '+key)
  require(installer.get('security_approval_automated') is False,'System security approval must not be automated')
  tls=collected['tls'][arch];require(tls.get('passed') is True,'TLS validation did not pass')
  for key in ('python_openssl','qt_openssl_runtime'):
   require(version_number(tls.get(key),key)>=(3,5,9),'Packaged TLS runtime predates reviewed maintained baseline')
  cases=tls.get('cases');require(isinstance(cases,dict),'Missing TLS certificate cases')
  for name,ok in (('valid',True),('unknown_ca',False),('hostname_mismatch',False),('expired',False)):
   case=cases.get(name,{});require(case.get('python_ok') is ok and case.get('qt_ok') is ok and case.get('qt_finished') is True,'TLS case failed: '+name)
   if ok:require(case.get('qt_error')==0 and case.get('qt_ssl_errors')==[],'Trusted TLS request failed')
   else:require(case.get('python_certificate_rejected') is True and bool(case.get('qt_ssl_errors')) and case.get('qt_error')!=0,'Certificate failure was not verified')
  require(cases['expired'].get('python_verify_code')==10 and 6 in cases['expired'].get('qt_ssl_error_codes',[]),'Expired certificate was not specifically rejected')
  py=tls.get('official_python',{});qt=tls.get('official_qt',{})
  require(py.get('verified') is True and isinstance(py.get('status'),int) and 200<=py['status']<400 and qt.get('finished') is True and qt.get('error')==0 and qt.get('ssl_errors')==[] and isinstance(qt.get('status'),int) and 200<=qt['status']<400,'Real HTTPS default trust did not pass')
  loaded=tls.get('loaded_libraries');require(isinstance(loaded,list),'Missing packaged TLS loaded-library hashes');roles=set()
  for lib in loaded:
   require(isinstance(lib,dict) and lib.get('archive_path') in native and package_hashes[lib['archive_path']]==lib.get('sha256'),'Loaded TLS library is not the reviewed packaged file')
   roles.add(lib.get('role'))
  require({'ssl','crypto','python_ssl','qt_network'}<=roles,'Missing SSL/crypto/Python/Qt mapped-library evidence')
  python=collected['python'][arch];version=version_number(python.get('version'),'Python')
  require(version[:2]==(3,13) and version>=(3,13,16),'Packaged CPython does not meet maintained cp313 baseline')
  require(python.get('passed') is True and python.get('abi')=='cp313' and python.get('soabi')==('cp313-win_amd64' if target=='windows-x86_64' else 'cpython-313-darwin') and python.get('native_plugin_imports_passed') is True,'Python/Krita extension compatibility not proven')
  modules=python.get('extension_modules',{});baseline=modules.get('baseline');candidate=modules.get('candidate')
  require(isinstance(baseline,list) and baseline and isinstance(candidate,list) and all(isinstance(x,str) and x for x in baseline+candidate) and set(baseline)<=set(candidate) and modules.get('missing')==[],'Python extension coverage regressed')
  core=python.get('interpreter_library',{});require(core.get('archive_path') in native and package_hashes[core['archive_path']]==core.get('sha256'),'Python interpreter mapping is not the reviewed package')
 return {'inventory_platform':target,'installer_platform':'macos-universal' if target=='macos-universal2' else target,'process_architectures':sorted(architectures),'execution':{kind:{arch:{key:row[key] for key in ('process_architecture','hardware_architecture','execution_mode')} for arch,row in runs.items()} for kind,runs in collected.items()},'receipt_hashes':refs}

def freeze(archive,evidence,platform,version,url,executable=None,evidence_root=None):
 if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',version):raise ValueError('Invalid version')
 parsed=urlsplit(url)
 if parsed.scheme!='https' or parsed.netloc!='accounts.flaptown.com' or not re.fullmatch(r'/flapsoft/downloads/[A-Za-z0-9][A-Za-z0-9._-]{0,150}',parsed.path) or parsed.query or parsed.fragment:raise ValueError('Use the reviewed Flapsoft HTTPS artifact location')
 with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 validated=validate_evidence(archive,evidence,platform,digest,Path(evidence_root) if evidence_root else archive.parent)
 platform=validated['installer_platform']
 plugin=Path(__file__).with_name('studio-plugin.zip')
 if hashlib.sha256(plugin.read_bytes()).hexdigest()!=PLUGIN:raise ValueError('Frozen Studio plugin changed')
 with zipfile.ZipFile(archive) as z,zipfile.ZipFile(plugin) as expected:
  names=z.namelist()
  if len(names)>100000 or sum(i.file_size for i in z.infolist())>8*1024**3:raise ValueError('Oversized runtime')
  for name in names:
   path=PurePosixPath(name)
   if path.is_absolute() or '..' in path.parts or '\\' in name or any(ord(c)<32 for c in name):raise ValueError('Unsafe runtime path')
  for name in expected.namelist():
   suffix='/actions/flapart.action' if name=='flapart.action' else '/pykrita/'+name
   matches=[n for n in names if n.endswith(suffix)]
   if len(matches)!=1 or z.read(matches[0])!=expected.read(name):raise ValueError('Runtime does not contain exact frozen Studio file: '+name)
  if platform=='windows-x86_64':
   if not executable or executable not in names or not executable.endswith('/krita.exe'):raise ValueError('Pin the packaged native executable')
  elif platform in ('macos-x86_64','macos-arm64','macos-universal'):
   if 'Flapart Studio.app/Contents/MacOS/krita' not in names or any(not n.startswith('Flapart Studio.app/') for n in names):raise ValueError('Expected one deployable Flapart Studio app bundle')
   if evidence.get('signature') not in ('unsigned','adhoc','developer-id'):raise ValueError('Record real signature status without implying notarization')
  else:raise ValueError('Unknown platform')
 out={'status':'qualified','kind':'namespaced-compiled-fork','version':version,'platform':platform,'profileNamespace':'flapart-native','url':url,'sha256':digest,'studioPluginSha256':PLUGIN,'qualification':validated}
 if platform.startswith('macos'):out.update(app='Flapart Studio.app',signature=evidence['signature'])
 else:out['executable']=executable
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--platform',required=True);p.add_argument('--version',required=True);p.add_argument('--url',required=True);p.add_argument('--executable');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=freeze(a.archive,json.loads(a.evidence.read_text()),a.platform,a.version,a.url,a.executable,a.evidence.parent)
 if a.output.exists():raise SystemExit('Write a new frozen manifest; do not overwrite an existing released pin')
 a.output.write_text(json.dumps(result,indent=2)+'\n');print('Release pin written after exact-payload evidence checks. No upload performed.')
