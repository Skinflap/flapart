#!/usr/bin/env python3
"""Candidate embedded-Python provenance and TLS probe; never a release qualifier alone."""
import argparse,ctypes,hashlib,importlib,importlib.machinery,json,os,platform,re,runpy,stat,subprocess,sys,sysconfig,zipfile
from pathlib import Path,PurePosixPath

def require(ok,message):
 if not ok:raise ValueError(message)
def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def inside(path,root):return Path(path).resolve().is_relative_to(Path(root).resolve())
def require_isolated(root):
 require(sys.flags.isolated==1,'Candidate Python must run isolated (-I or isolated ._pth configuration)')
 require(all(not entry or inside(entry,root) for entry in sys.path),'Python import path escapes candidate runtime root')

def require_embedded(root):
 root=Path(root).resolve()
 require(inside(sys.executable,root),'Refusing host Python: executable is outside runtime root')
 require(inside(sys.base_prefix,root),'Refusing host Python: base prefix is outside runtime root')
 require_isolated(root)
 return root

def archive_inventory(archive,root):
 root=Path(root).resolve();inventory={};links=[]
 with zipfile.ZipFile(archive) as z:
  require(len(z.infolist())<=100000 and sum(i.file_size for i in z.infolist())<=8*1024**3,'Archive exceeds runtime bounds')
  for info in z.infolist():
   name=info.filename;parts=PurePosixPath(name).parts
   require(name and not name.startswith('/') and '\\' not in name and '..' not in parts and not any(ord(c)<32 for c in name),'Unsafe archive path')
   if info.is_dir():continue
   require(name not in inventory,'Duplicate archive entry');path=root/name;mode=(info.external_attr>>16)&0o170000
   require(inside(path,root),'Runtime path resolves outside archive root')
   if mode==stat.S_IFLNK:
    require(info.file_size<=4096,'Oversized symlink');target=z.read(info).decode('utf-8')
    require(path.is_symlink() and os.readlink(path)==target and path.exists(),'Runtime symlink mismatch or dangling link')
    inventory[name]={'symlink':target};links.append(path);continue
   require(mode in (0,stat.S_IFREG) and path.is_file() and not path.is_symlink(),'Runtime regular file missing or substituted')
   with z.open(info) as stream:value=hashlib.file_digest(stream,'sha256').hexdigest()
   require(path.stat().st_size==info.file_size and digest(path)==value,'Runtime file differs from archive: '+name)
   inventory[name]={'sha256':value,'bytes':info.file_size}
 for link in links:require(inside(link,root),'Runtime symlink escapes root')
 return inventory

def bound_file(path,root,inventory):
 path=Path(path).resolve();require(inside(path,root),'Loaded non-system binary outside candidate runtime: '+str(path))
 name=path.relative_to(root).as_posix();record=inventory.get(name)
 require(record and record.get('sha256')==digest(path),'Loaded binary does not match archive: '+name)
 return {'archive_path':name,'sha256':record['sha256']}

def loaded_paths():
 if sys.platform=='win32':
  from ctypes import wintypes
  kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
  kernel.GetCurrentProcess.restype=wintypes.HANDLE;process=kernel.GetCurrentProcess();needed=wintypes.DWORD();array=(wintypes.HMODULE*8192)()
  psapi.EnumProcessModulesEx.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.DWORD]
  require(psapi.EnumProcessModulesEx(process,array,ctypes.sizeof(array),ctypes.byref(needed),3) and needed.value<=ctypes.sizeof(array),'Cannot enumerate loaded modules')
  psapi.GetModuleFileNameExW.argtypes=[wintypes.HANDLE,wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
  paths=[]
  for handle in array[:needed.value//ctypes.sizeof(wintypes.HMODULE)]:
   buf=ctypes.create_unicode_buffer(32768);require(psapi.GetModuleFileNameExW(process,handle,buf,len(buf)),'Cannot identify loaded module');paths.append(buf.value)
  return paths
 if sys.platform=='darwin':
  lib=ctypes.CDLL(None);lib._dyld_image_count.restype=ctypes.c_uint32;lib._dyld_get_image_name.argtypes=[ctypes.c_uint32];lib._dyld_get_image_name.restype=ctypes.c_char_p
  return [lib._dyld_get_image_name(i).decode() for i in range(lib._dyld_image_count())]
 if sys.platform.startswith('linux'):
  paths=set()
  for line in Path('/proc/self/maps').read_text().splitlines():
   fields=line.split(None,5)
   if len(fields)==6 and fields[5].startswith('/'):
    require(not fields[5].endswith(' (deleted)'),'Loaded deleted binary mapping');paths.add(fields[5])
  return sorted(paths)
 raise ValueError('Unsupported mapping platform')

def system_path(path):
 path=Path(path).resolve()
 if sys.platform=='darwin':roots=['/usr/lib','/System/Library']
 elif sys.platform=='win32':
  buf=ctypes.create_unicode_buffer(32768);require(ctypes.windll.kernel32.GetWindowsDirectoryW(buf,len(buf)),'Cannot identify Windows directory');roots=[str(Path(buf.value)/'System32'),str(Path(buf.value)/'SysWOW64')]
 else:roots=['/usr/lib','/lib','/lib64']
 return any(path.is_relative_to(Path(root).resolve()) for root in roots)

def validate_defender_attestation(record,path,sha):
 require(record.get('path')==str(path) and record.get('sha256','').lower()==sha,'Defender attestation path/hash mismatch')
 require(record.get('status')=='Valid' and record.get('signature_type') in ('Catalog','Authenticode'),'Defender signature is not trusted')
 require(record.get('signer')=='CN=Microsoft Windows, O=Microsoft Corporation, L=Redmond, S=Washington, C=US','Unexpected Defender signer')
 require(record.get('description')=='IOfficeAntiVirus Module' and re.fullmatch('[0-9A-Fa-f]{40}',record.get('thumbprint','')),'Unexpected Defender module identity')
 return record

def windows_defender_attestation(path):
 if sys.platform!='win32' or Path(path).name.lower()!='mpoav.dll':return None
 import uuid
 from ctypes import wintypes
 guid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('905e63b6-c1bf-494e-b29c-65b732d3d21a').bytes_le)
 shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32');value=ctypes.c_void_p()
 shell.SHGetKnownFolderPath.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p)]
 require(shell.SHGetKnownFolderPath(ctypes.byref(guid),0,None,ctypes.byref(value))==0,'Cannot identify canonical Program Files')
 try:program_files=Path(ctypes.wstring_at(value))
 finally:ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoTaskMemFree(value)
 expected=program_files/'Windows Defender'/'MpOAV.dll';path=Path(path)
 require(expected.resolve()==expected and path==expected,'Unexpected Defender module path or reparse point')
 buf=ctypes.create_unicode_buffer(32768);require(ctypes.windll.kernel32.GetSystemDirectoryW(buf,len(buf)),'Cannot identify system tools')
 ps=Path(buf.value)/'WindowsPowerShell/v1.0/powershell.exe';require(ps.is_file(),'Missing system signature verifier')
 before=digest(path);env=dict(os.environ);env['FLAPART_ATTEST_FILE']=str(path);env['PSModulePath']=str(ps.parent/'Modules')
 script="""$ErrorActionPreference='Stop'; $p=$env:FLAPART_ATTEST_FILE; $s=Microsoft.PowerShell.Security\\Get-AuthenticodeSignature -LiteralPath $p; $f=Microsoft.PowerShell.Management\\Get-Item -LiteralPath $p; $h=Microsoft.PowerShell.Utility\\Get-FileHash -LiteralPath $p -Algorithm SHA256; [ordered]@{path=$f.FullName;sha256=$h.Hash;status=[string]$s.Status;signature_type=[string]$s.SignatureType;signer=$s.SignerCertificate.Subject;issuer=$s.SignerCertificate.Issuer;thumbprint=$s.SignerCertificate.Thumbprint;description=$f.VersionInfo.FileDescription} | Microsoft.PowerShell.Utility\\ConvertTo-Json -Compress"""
 result=subprocess.run([str(ps),'-NoLogo','-NoProfile','-NonInteractive','-Command',script],env=env,capture_output=True,text=True,timeout=60,check=True)
 record=validate_defender_attestation(json.loads(result.stdout),path,before)
 require(digest(path)==before,'Defender module changed during attestation')
 return {**record,'verification':'Windows default-trust Get-AuthenticodeSignature','verifier_path':str(ps),'verifier_sha256':digest(ps)}

def architecture():
 normalize=lambda a:{'AMD64':'x86_64','aarch64':'arm64','ARM64':'arm64'}.get(a,a)
 process=normalize(platform.machine());hardware=process;mode='native'
 if sys.platform=='win32':
  proc=ctypes.c_ushort();host=ctypes.c_ushort();k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=ctypes.c_void_p;k.IsWow64Process2.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ushort),ctypes.POINTER(ctypes.c_ushort)]
  require(k.IsWow64Process2(k.GetCurrentProcess(),ctypes.byref(proc),ctypes.byref(host)),'Cannot identify process architecture')
  names={0x8664:'x86_64',0xaa64:'arm64'};hardware=names.get(host.value);process=names.get(proc.value or host.value)
 elif sys.platform=='darwin':
  lib=ctypes.CDLL(None);value=ctypes.c_int();size=ctypes.c_size_t(ctypes.sizeof(value))
  if lib.sysctlbyname(b'sysctl.proc_translated',ctypes.byref(value),ctypes.byref(size),None,0)==0 and value.value==1:hardware='arm64';process='x86_64'
 if process!=hardware:mode='translated'
 require(process in ('arm64','x86_64') and hardware in ('arm64','x86_64'),'Unsupported architecture')
 return {'process_architecture':process,'hardware_architecture':hardware,'execution_mode':mode}

def baseline(path,pin):
 require(re.fullmatch('[0-9a-f]{64}',pin or '') and digest(path)==pin,'Baseline manifest hash mismatch')
 data=json.loads(Path(path).read_text());names=data.get('extensions',data.get('extension_modules',{}).get('baseline'))
 require(isinstance(names,list) and names and len(names)<=1000 and len(set(names))==len(names) and all(isinstance(n,str) and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',n) for n in names),'Invalid baseline extension manifest')
 return names

def module_role(path):
 name=Path(path).name.lower()
 if name.startswith('_ssl.'):return 'python_ssl'
 if re.match(r'(?:lib)?ssl(?:[-.0-9_]|$)',name):return 'ssl'
 if re.match(r'(?:lib)?crypto(?:[-.0-9_]|$)',name):return 'crypto'
 if re.fullmatch(r'(?:lib)?qt[56]?network(?:\.so(?:\.[0-9]+)*|(?:\.[0-9]+)*\.dylib|\.dll)?',name):return 'qt_network'
 if name=='python313.dll' or re.fullmatch(r'libpython3\.13(?:\.so(?:\.[0-9]+)*|\.dylib)',name) or name=='python' and 'Python.framework/Versions/3.13/Python' in Path(path).as_posix():return 'python'
 return None

def windows_tls_backend_pair(role,first,second):
 # Official CPython and MinGW Qt use distinct maintained OpenSSL DLL ABIs.
 # Admit only this measured layout within the same packaged application.
 if sys.platform!='win32' or role not in ('ssl','crypto'):return False
 a=PurePosixPath(first);b=PurePosixPath(second)
 if len(a.parts)<3 or len(b.parts)<3 or a.parents[1]!=b.parents[1]:return False
 expected={('python','lib'+role+'-3.dll'),('bin','lib'+role+'-3-x64.dll')}
 return {(a.parent.name,a.name),(b.parent.name,b.name)}==expected

def mapped_receipt(paths,root,inventory,required=None):
 rows=[];system=[];roles={}
 for raw in sorted(set(paths)):
  path=Path(raw).resolve();role=module_role(path)
  if inside(path,root):
   record=bound_file(path,root,inventory);record['loaded_path']=str(path)
   if role:
    record['role']=role
    require(role not in roles or roles[role]['archive_path']==record['archive_path'] or windows_tls_backend_pair(role,roles[role]['archive_path'],record['archive_path']),'Ambiguous loaded '+role+' library')
    if role not in roles:roles[role]=dict(record)
   rows.append(record)
  else:
   require(role is None,'Host/SDK runtime dependency loaded: '+str(path))
   if system_path(path):system.append({'path':str(path),'sha256':digest(path) if path.is_file() else None,'shared_cache_only':sys.platform=='darwin' and not path.is_file()})
   else:
    attestation=windows_defender_attestation(path)
    require(attestation is not None,'Host/SDK runtime dependency loaded: '+str(path))
    system.append({'path':str(path),'sha256':attestation['sha256'].lower(),'windows_security_module_attestation':attestation})
 require(({'ssl','crypto','python_ssl','qt_network','python'} if required is None else required)<=set(roles),'Missing mapped SSL/crypto/Python/Qt native libraries')
 return rows,system,roles

def tls_child(args):
 # The unchanged helper runs in this child, so mapping capture is from the exact
 # process which performed TLS checks (not a separate import-only process).
 if args.https_proxy:
  from urllib.parse import urlsplit
  from PyQt5.QtNetwork import QNetworkProxy,QNetworkProxyFactory
  parsed=urlsplit(args.https_proxy)
  require(parsed.scheme=='http' and parsed.hostname and parsed.port and not parsed.username and not parsed.password,'Use an explicit HTTP CONNECT proxy without embedded credentials')
  class TransportProxy(QNetworkProxyFactory):
   def queryProxy(self,query):
    if query.url().host() in ('localhost','127.0.0.1','::1'):return [QNetworkProxy(QNetworkProxy.NoProxy)]
    return [QNetworkProxy(QNetworkProxy.HttpProxy,parsed.hostname,parsed.port)]
  QNetworkProxyFactory.setApplicationProxyFactory(TransportProxy())
 helper=Path(args.tls_helper).resolve();sys.argv=[str(helper),'--openssl',args.openssl,'--output',args.child_tls,'--official-url',args.official_url]
 code=1
 try:
  runpy.run_path(str(helper),run_name='__main__')
 except SystemExit as error:code=error.code if isinstance(error.code,int) else 1
 finally:Path(args.child_maps).write_text(json.dumps({'paths':loaded_paths(),**architecture()}))
 return code

def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path);p.add_argument('--runtime-root',type=Path);p.add_argument('--baseline-extension-manifest',type=Path);p.add_argument('--baseline-extension-sha256');p.add_argument('--openssl');p.add_argument('--output',type=Path);p.add_argument('--runtime-scope',choices=['relocated-package','installed-runtime']);p.add_argument('--target-platform',choices=['windows-x86_64','macos-x86_64','macos-arm64','macos-universal2','linux-x86_64']);p.add_argument('--tls-helper',default=str(Path(__file__).resolve().parents[1]/'tls-evaluation'/'https-validation-probe.py'));p.add_argument('--official-url',default='https://www.python.org/');p.add_argument('--https-proxy');p.add_argument('--child-tls');p.add_argument('--child-maps');args=p.parse_args()
 if args.child_tls:return tls_child(args)
 require(all((args.archive,args.runtime_root,args.baseline_extension_manifest,args.baseline_extension_sha256,args.openssl,args.output,args.runtime_scope,args.target_platform)),'Missing required candidate arguments')
 root=require_embedded(args.runtime_root);require(not args.output.exists(),'Output directory must be new');archive_sha=digest(args.archive);inventory=archive_inventory(args.archive,root)
 bound_file(sys.executable,root,inventory);bound_file(args.openssl,root,inventory);names=baseline(args.baseline_extension_manifest,args.baseline_extension_sha256)
 arch=architecture();os_prefix={'win32':'windows','darwin':'macos'}.get(sys.platform,'linux' if sys.platform.startswith('linux') else None);require(args.target_platform.split('-')[0]==os_prefix,'Target platform does not match executing OS');require(args.target_platform.endswith(arch['process_architecture']) or args.target_platform=='macos-universal2','Process architecture does not match target')
 common={'payload_sha256':archive_sha,'target_platform':args.target_platform,**arch,'native_execution':True,'runtime_scope':args.runtime_scope}
 imported=[]
 for name in names:
  module=importlib.import_module(name);origin=getattr(module,'__file__',None)
  require(origin is None and name in sys.builtin_module_names or origin and any(origin.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES),'Baseline entry is not an extension: '+name)
  if origin:bound_file(origin,root,inventory)
  imported.append(name)
 import ssl,_ssl
 from PyQt5 import QtCore,QtNetwork
 bound_file(_ssl.__file__,root,inventory);bound_file(QtCore.__file__,root,inventory);bound_file(QtNetwork.__file__,root,inventory)
 args.output.mkdir(parents=True);raw=args.output/'tls-raw.json';maps=args.output/'tls-maps.json';env=dict(os.environ)
 if args.https_proxy:
  require(args.https_proxy.startswith(('http://','https://')),'Invalid explicit HTTPS proxy');env['https_proxy']=args.https_proxy;env['HTTPS_PROXY']=args.https_proxy
 # Keep local controlled TLS fixtures off transport proxies; no certificate bypass.
 env['NO_PROXY']=env['no_proxy']='localhost,127.0.0.1,::1'
 command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--child-tls',str(raw),'--child-maps',str(maps),'--tls-helper',args.tls_helper,'--openssl',args.openssl,'--official-url',args.official_url]
 if sys.platform=='darwin':command=['/usr/bin/arch','-'+arch['process_architecture'],*command]
 if args.https_proxy:command+=['--https-proxy',args.https_proxy]
 result=subprocess.run(command,env=env,timeout=180)
 tls=json.loads(raw.read_text());child=json.loads(maps.read_text());require(all(child[k]==arch[k] for k in arch),'TLS child architecture changed')
 rows,system,roles=mapped_receipt(child['paths'],root,inventory)
 parent_rows,parent_system,_=mapped_receipt(loaded_paths(),root,inventory,required=set())
 tls.update(common,loaded_libraries=[row for row in rows if row.get('role') in ('ssl','crypto','python_ssl','qt_network')],probe_sha256=digest(__file__),https_helper_sha256=digest(args.tls_helper),transport_proxy_explicit=bool(args.https_proxy))
 version=platform.python_version();python={**common,'version':version,'abi':'cp'+str(sys.version_info.major)+str(sys.version_info.minor),'soabi':sysconfig.get_config_var('SOABI'),'passed':sys.version_info[:3]>=(3,13,16) and sys.version_info[:2]==(3,13),'extension_modules':{'baseline':names,'candidate':imported,'missing':[]},'interpreter_library':roles['python'],'baseline_manifest_sha256':args.baseline_extension_sha256,'native_plugin_imports_evidence':'Not measured here; requires separate application probe.'}
 for name,data in [('tls',tls),('python',python),('provenance',{'archive_sha256':common['payload_sha256'],'runtime_root':str(root),'loaded_binaries':rows,'system_libraries':system,'parent_loaded_binaries':parent_rows,'parent_system_libraries':parent_system,'app_probe_required':True,'release_qualified':False})]:(args.output/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
 require(digest(args.archive)==common['payload_sha256'],'Archive changed during probe')
 require(result.returncode==0 and tls.get('passed') is True and python['passed'],'Candidate runtime validation failed')
 return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError,subprocess.SubprocessError) as error:raise SystemExit('Package runtime probe refused: '+str(error))
