"""Private native installer qualification producer. Never publishes a release.
Runs only on an explicit disposable native host/profile. Missing outcomes fail.
"""
import argparse,ctypes,hashlib,json,os,platform,shutil,stat,subprocess,sys,tempfile,time,uuid,zipfile
from pathlib import Path,PurePosixPath


def require(value,message):
 if not value:raise RuntimeError(message)
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def knownfolder(identifier):
 raw=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identifier).bytes_le);value=ctypes.c_wchar_p()
 hr=ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw),0,None,ctypes.byref(value))
 if hr:raise OSError(hr,'KnownFolder lookup failed')
 try:return Path(value.value)
 finally:ctypes.windll.ole32.CoTaskMemFree(value)
def snapshot(paths):
 result={}
 for i,path in enumerate(paths):
  require(not path.is_symlink(),'Snapshot root is a symlink')
  root=path.resolve() if path.is_dir() else path.parent.resolve()
  for p in sorted(path.rglob('*')) if path.is_dir() else [path]:
   key=str(i)+'/'+p.relative_to(root).as_posix()
   if p.is_symlink():
    require(p.resolve(strict=True).is_relative_to(root),'Snapshot symlink escapes tree')
    result[key]={'symlink':os.readlink(p)}
   elif p.is_file():result[key]={'sha256':sha(p),'bytes':p.stat().st_size}
   elif p.exists():require(p.is_dir(),'Unsupported snapshot file type')
 return result

def clean_environment(system,output):
 # Keep only UI/session essentials. Never inherit SDK/search/injection variables.
 allowed=('HOME','USER','LOGNAME','TMPDIR','TMP','TEMP','LANG','LC_ALL','DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','__CF_USER_TEXT_ENCODING','SystemRoot','WINDIR','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMDATA','COMSPEC','PATHEXT','USERNAME','USERDOMAIN','SESSIONNAME')
 env={k:os.environ[k] for k in allowed if k in os.environ}
 env.update(FLAPART_NATIVE='1',FLAPART_QA_EXPECT_COMPILED='1',FLAPART_QA_OUTPUT=str(output),PYTHONDONTWRITEBYTECODE='1')
 env['PATH']=os.pathsep.join([str(Path(os.environ['WINDIR'])/'System32'),os.environ['WINDIR']]) if system=='Windows' else '/usr/bin:/bin:/usr/sbin:/sbin'
 return env

def installed_inventory(archive,root,allowed_extra=()):
 """Compare actual installed bytes/links to every member of the pinned ZIP."""
 root=root.resolve();seen=set();records={}
 with zipfile.ZipFile(archive) as z:
  entries=z.infolist();require(len(entries)<=100000 and sum(x.file_size for x in entries)<=8*1024**3,'Oversized archive')
  for entry in entries:
   name=entry.filename;parts=PurePosixPath(name).parts
   require(name and not name.startswith('/') and '\\' not in name and '..' not in parts and all(ord(c)>=32 for c in name),'Unsafe archive member')
   require(name.casefold() not in seen,'Duplicate archive member');seen.add(name.casefold())
   path=root/name;require(path.resolve(strict=True).is_relative_to(root),'Installed member escapes root')
   mode=stat.S_IFMT(entry.external_attr>>16)
   if entry.is_dir():require(path.is_dir(),'Missing installed directory');continue
   require(mode in (0,stat.S_IFREG,stat.S_IFLNK),'Unsupported archive member')
   if mode==stat.S_IFLNK:
    require(entry.file_size<=4096 and path.is_symlink(),'Installed symlink mismatch')
    target=z.read(entry).decode('utf-8');require(os.readlink(path)==target,'Installed symlink changed');records[name]={'symlink':target}
   else:
    require(path.is_file() and not path.is_symlink(),'Installed regular file mismatch')
    with z.open(entry) as stream:expected=hashlib.file_digest(stream,'sha256').hexdigest()
    require(path.stat().st_size==entry.file_size and sha(path)==expected,'Installed bytes differ: '+name)
    records[name]={'sha256':expected,'bytes':entry.file_size}
 actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
 require(actual-set(records)<=set(allowed_extra),'Unexpected files in installed runtime')
 return records

def require_process_exited(pid,system):
 require(type(pid) is int and pid>1 and pid!=os.getpid(),'Invalid actual child process ID')
 if system=='Windows':
  kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.OpenProcess.restype=ctypes.c_void_p
  handle=kernel.OpenProcess(0x100000|0x1000,False,pid)
  if not handle:
   require(ctypes.get_last_error()==87,'Cannot verify child process exit');return
  kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.WaitForSingleObject.restype=ctypes.c_uint32
  kernel.CloseHandle.argtypes=[ctypes.c_void_p]
  try:require(kernel.WaitForSingleObject(handle,0)==0,'Launcher returned while actual native child is still running')
  finally:kernel.CloseHandle(handle)
 else:
  try:os.kill(pid,0)
  except ProcessLookupError:return
  except PermissionError:raise RuntimeError('Cannot verify native child process exit')
  raise RuntimeError('Launcher returned while actual native child is still running')

def validate_child(native,architecture,system,executable,expected):
 require('error' not in native,'Native probe failed: '+str(native.get('error')))
 require(native.get('process_architecture')==architecture,'Actual child architecture differs from requested architecture')
 hardware=native.get('hardware_architecture');mode=native.get('execution_mode')
 require(hardware in ('x86_64','arm64') and (mode=='native' and hardware==architecture or system=='Darwin' and hardware=='arm64' and architecture=='x86_64' and mode=='translated'),'Unsupported actual process/hardware execution')
 image=native.get('process_image',{})
 require(Path(image.get('path','')).resolve()==executable.resolve() and image.get('sha256')==expected and sha(executable)==expected,'Launched native image is not the installed pinned executable')
 require(Path(image.get('qt_application_file_path','')).resolve()==executable.resolve(),'Qt application path differs from actual native image')
 life=native.get('lifecycle',{})
 require(all(life.get(k) is True for k in ('cleanup_started','qa_documents_closed','qt_exit_requested','about_to_quit')),'Native Qt lifecycle did not close normally')
 for key in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action','action_reopens'):require(native.get(key) is True,'Missing native outcome: '+key)
 require(native.get('canvas')==[64,64] and native.get('round_trip')==[64,64,'Draw here'] and native.get('round_trip_pixel')==[70,110,191,255],'Canvas/KRA roundtrip failed')
 require(native.get('browser_handoff')==['https://flaptown.com/flapart/?from=native&destination=profile'] and native.get('application_font')=='Syne Mono','Studio handoff/font failed')
 return {k:native[k] for k in ('process_architecture','hardware_architecture','execution_mode')}

def main():
 parser=argparse.ArgumentParser()
 for name in ('archive','manifest','probe','output'):parser.add_argument('--'+name,required=True,type=Path)
 parser.add_argument('--archive-sha256',required=True);parser.add_argument('--architecture',required=True,choices=('arm64','x86_64'))
 parser.add_argument('--disposable-native-host',action='store_true',help='Explicit private disposable native host; never use an existing user profile')
 parser.add_argument('--timeout',type=int,default=200);args=parser.parse_args()
 root=Path(__file__).resolve().parent;output=args.output.resolve()
 require(not output.is_relative_to(args.probe.resolve()),'Evidence must not be inside probe inputs')
 require(not output.exists() or not any(output.iterdir()),'Use a fresh empty evidence directory');output.mkdir(parents=True,exist_ok=True)
 result={'schema':2,'passed':False,'native_execution':False,'upgraded_runtime_tested':False,'upgraded_native_child_exit_observed':False,'runtime_scope':'installed-runtime','release_qualified':False,'binary_published':False,'security_approval_automated':False,'downloaded_user_security_approval_tested':False,'stages':[],'artifacts':{},'requested_process_architecture':args.architecture}
 def write():
  temporary=output/'installer-e2e.pending.json';temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(output/'installer-e2e.json')
 def artifact(name,path):
  result['artifacts'][name]={'path':path.relative_to(output).as_posix(),'sha256':sha(path),'bytes':path.stat().st_size}
 def save(name,value):
  path=output/(name+'.json');path.write_text(json.dumps(value,indent=2)+'\n');artifact(name,path);return path
 def run(name,command,env=None,timeout=900):
  log=output/(name+'.log');tool=Path(command[0]).resolve(strict=True);stage={'name':name,'argv':command,'tool_sha256_before':sha(tool),'completed':False};result['stages'].append(stage);write()
  try:
   with log.open('w') as stream:
    process=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
    try:stage['returncode']=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
     stage['timed_out']=True;process.terminate()
     try:process.wait(timeout=10)
     except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
     raise RuntimeError('Stage timeout; child app may still need disposable-host cleanup. No security approval automated.')
   stage['completed']=True;return stage['returncode']
  finally:
   if log.exists():artifact(name+'_log',log)
   stage['tool_sha256_after']=sha(tool)
   write()
   require(stage['tool_sha256_before']==stage['tool_sha256_after'],'Stage executable changed during execution')
 write()
 try:
  system=platform.system();require(system in ('Windows','Darwin'),'Native Mac or Windows host required')
  hosted=os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('CI')=='true'
  require(hosted or args.disposable_native_host,'Explicit disposable native host required')
  result.update(host_type='github-actions' if hosted else 'explicit-private-disposable',platform=platform.platform())
  archive=args.archive.resolve();manifest=json.loads(args.manifest.read_text());original_sha=sha(archive)
  require(original_sha==args.archive_sha256==manifest.get('sha256'),'Archive does not match explicit candidate pin')
  result['payload_sha256']=original_sha
  target={'macos-universal':'macos-universal2','macos-universal2':'macos-universal2','macos-arm64':'macos-arm64','macos-x86_64':'macos-x86_64','windows-x86_64':'windows-x86_64'}.get(manifest.get('platform'))
  require(target and target.startswith('macos' if system=='Darwin' else 'windows'),'Candidate platform differs from host')
  require(target=='macos-universal2' or target.endswith(args.architecture),'Candidate does not include requested architecture');result['target_platform']=target
  require(manifest.get('kind')=='namespaced-compiled-fork' and manifest.get('profileNamespace')=='flapart-native' and manifest.get('status') in ('ci-candidate','qualified'),'Invalid candidate manifest')
  save('candidate-manifest',manifest)
  # Test-only unlock, never a release pin. Original manifest remains above.
  manifest['status']='qualified'
  if manifest['platform']=='macos-universal2':manifest['platform']='macos-universal'
  if system=='Windows':
   config=knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');data=knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D');ordinary=[config/'kritarc',config/'kritadisplayrc',config/'kritashortcutsrc',data/'krita',config/'krita.log',config/'krita-sysinfo.log']
  else:
   config=Path.home()/'Library/Preferences';data=Path.home()/'Library/Application Support';ordinary=[config/'kritarc',config/'kritadisplayrc',config/'kritashortcutsrc',data/'krita',data/'krita.log',data/'krita-sysinfo.log']
  settings=config/'flapartnativerc';profile=data/'flapart-native'
  require(not settings.exists() and not profile.exists(),'Use a fresh profile; existing Flapart settings are never replaced')
  config.mkdir(parents=True,exist_ok=True)
  for path in ordinary:
   if path.name=='krita':path=path/'INSTALLER_QA_KEEP.txt'
   path.parent.mkdir(parents=True,exist_ok=True)
   if not path.exists():path.write_bytes(b'ORIGINAL-KRITA-INSTALLER-SENTINEL\n')
  ordinary_before=snapshot(ordinary);save('ordinary-before',ordinary_before)
  # Retain installed tree only privately while the probe executes. Never upload it.
  with tempfile.TemporaryDirectory(prefix='flapart-installer-e2e-',dir=os.environ.get('RUNNER_TEMP')) as work:
   work=Path(work).resolve();source=work/'installer';source.mkdir();dest=work/'installed';artwork=output/'native-first';artwork.mkdir()
   inputs={str(Path(__file__).name):sha(Path(__file__)),'original-manifest':sha(args.manifest),'candidate-archive':original_sha}
   for pattern in ('*.exe','*.command','*.ttf'):
    for f in root.glob(pattern):shutil.copy2(f,source/f.name);inputs[f.name]=sha(f)
   inputs['probe']=snapshot([args.probe]);save('input-hashes',inputs)
   (source/'release.json').write_text(json.dumps(manifest));save('test-only-manifest',manifest)
   def install(name,payload):
    command=[str(source/'Install Flapart.exe'),'--quiet','--archive',str(payload),'--destination',str(dest),'--no-shortcut'] if system=='Windows' else ['/bin/bash',str(source/'Install Flapart.command'),str(payload),str(dest)]
    return run(name,command)
   require(install('install',archive)==0,'Installation failed; inspect install.log');result['installer_passed']=True
   receipt=dest/'flapart-install.json';record=json.loads(receipt.read_text());save('initial-install',record)
   require(record.get('sha256')==original_sha and record.get('profileNamespace')=='flapart-native','Installed receipt pin/namespace mismatch')
   release=record['release'];require(isinstance(release,str) and release not in ('.','..') and '/' not in release and '\\' not in release,'Unsafe installed release name')
   final=dest/'releases'/release;extras=('Flapart Studio.exe','SyneMono-Regular.ttf') if system=='Windows' else ('signature-assessment.txt','gatekeeper-assessment.txt');inventory=installed_inventory(archive,final,extras);save('installed-archive-members',inventory)
   executable=final/(record['executable'] if system=='Windows' else 'Flapart Studio.app/Contents/MacOS/krita')
   member=executable.relative_to(final).as_posix();require(member in inventory and 'sha256' in inventory[member],'Missing installed native executable');expected=inventory[member]['sha256']
   require(snapshot(ordinary)==ordinary_before,'Ordinary Krita changed during install')
   plugins=profile/'pykrita';plugins.mkdir(parents=True);settings.write_text('[python]\nenable_flapart=true\nenable_flapart_probe=true\n')
   shutil.copy2(args.probe/'flapart_probe.desktop',plugins/'flapart_probe.desktop');shutil.copytree(args.probe/'flapart_probe',plugins/'flapart_probe',ignore=shutil.ignore_patterns('__pycache__'))
   launcher=final/'Flapart Studio.exe' if system=='Windows' else dest/'Flapart Studio.command'
   source_launcher=source/'Install Flapart.exe' if system=='Windows' else source/'Flapart Studio.command'
   require(sha(launcher)==sha(source_launcher),'Installed launcher differs from tested input')
   save('installed-launcher',{'sha256':sha(launcher),'source_input':source_launcher.name})
   if system=='Windows' and (source/'SyneMono-Regular.ttf').exists():require(sha(final/'SyneMono-Regular.ttf')==sha(source/'SyneMono-Regular.ttf'),'Installed font differs from input')
   env=clean_environment(system,artwork);save('runtime-environment-keys',sorted(env))
   command=[str(final/'Flapart Studio.exe'),'--launch','--wait'] if system=='Windows' else ['/bin/bash',str(dest/'Flapart Studio.command'),'--flapart-qa-architecture',args.architecture]
   require(run('launcher',command,env,args.timeout)==0,'Installed launcher did not exit successfully')
   native_path=artwork/'result.json';require(native_path.is_file(),'No native probe receipt; inspect security review manually')
   native=json.loads(native_path.read_text());identity=validate_child(native,args.architecture,system,executable,expected)
   require_process_exited(native.get('process_id'),system)
   result['native_child_exit_observed']=True
   result.update(identity,native_execution=True,native_runtime_tested=True,native_canvas_png_kra_passed=True,studio_menu_reopens=True,installed_executable={'archive_path':member,'sha256':expected},native_probe_sha256=sha(native_path));artifact('native_probe',native_path)
   require(snapshot(ordinary)==ordinary_before,'Ordinary Krita changed during launch');result.update(profile_isolation_verified=True,ordinary_krita_unchanged=True)
   creations=snapshot([artwork]);profile_paths=[profile,*sorted(config.glob('flapartnative*'))];user_profile=snapshot(profile_paths);old_runtime=snapshot([final]);before=receipt.read_bytes()
   save('artwork-before-upgrade',creations);save('profile-before-upgrade',user_profile);save('runtime-before-upgrade',old_runtime)
   corrupt=work/'corrupt.zip';corrupt.write_bytes(b'not the pinned payload')
   require(install('failed-upgrade',corrupt)!=0,'Corrupt upgrade was accepted')
   require(receipt.read_bytes()==before,'Failed upgrade changed install receipt');result['failed_upgrade_preserved_receipt']=True
   after_art=snapshot([artwork]);after_profile=snapshot(profile_paths);save('artwork-after-failure',after_art);save('profile-after-failure',after_profile)
   require(after_art==creations and after_profile==user_profile,'Failed upgrade changed artwork/settings');result['failed_upgrade_preserved_artwork_and_settings']=True
   require(snapshot([final])==old_runtime,'Failed upgrade changed previous runtime')
   manifest['version']+='-ci-upgrade';(source/'release.json').write_text(json.dumps(manifest));save('upgrade-test-only-manifest',manifest)
   require(install('upgrade',archive)==0,'Upgrade failed');upgraded=json.loads(receipt.read_text());save('upgraded-install',upgraded)
   require(upgraded.get('sha256')==original_sha and upgraded.get('profileNamespace')=='flapart-native','Upgraded install receipt pin/namespace differs')
   next_release=upgraded.get('release')
   require(isinstance(next_release,str) and next_release not in ('.','..') and '/' not in next_release and '\\' not in next_release,'Unsafe upgraded release name')
   save('upgraded-archive-members',installed_inventory(archive,dest/'releases'/next_release,extras))
   after_art=snapshot([artwork]);after_profile=snapshot(profile_paths);save('artwork-after-upgrade',after_art);save('profile-after-upgrade',after_profile);save('ordinary-after',snapshot(ordinary));save('runtime-after-upgrade',snapshot([final]))
   require(after_art==creations and after_profile==user_profile and snapshot(ordinary)==ordinary_before,'Upgrade changed artwork/settings/Krita');result['successful_upgrade_preserved_artwork_and_settings']=True
   require(snapshot([final])==old_runtime and upgraded['release']!=record['release'],'Previous runtime changed or upgrade not selected');result['previous_runtime_retained']=True
   # Exercise the newly selected edition through its real installed launcher.
   # The first launch alone cannot establish that upgrade selection is usable.
   upgraded_final=dest/'releases'/next_release
   upgraded_executable=upgraded_final/(upgraded['executable'] if system=='Windows' else 'Flapart Studio.app/Contents/MacOS/krita')
   upgraded_inventory=installed_inventory(archive,upgraded_final,extras)
   upgraded_member=upgraded_executable.relative_to(upgraded_final).as_posix()
   require(upgraded_member in upgraded_inventory and 'sha256' in upgraded_inventory[upgraded_member],'Missing upgraded native executable')
   upgraded_expected=upgraded_inventory[upgraded_member]['sha256']
   upgraded_artwork=output/'native-upgrade';upgraded_artwork.mkdir()
   upgraded_launcher=upgraded_final/'Flapart Studio.exe' if system=='Windows' else dest/'Flapart Studio.command'
   require(sha(upgraded_launcher)==sha(source_launcher),'Upgraded launcher differs from tested input')
   upgraded_command=[str(upgraded_launcher),'--launch','--wait'] if system=='Windows' else ['/bin/bash',str(upgraded_launcher),'--flapart-qa-architecture',args.architecture]
   require(run('upgrade-launcher',upgraded_command,clean_environment(system,upgraded_artwork),args.timeout)==0,'Upgraded launcher did not exit successfully')
   upgraded_native_path=upgraded_artwork/'result.json';require(upgraded_native_path.is_file(),'No upgraded native probe receipt')
   upgraded_native=json.loads(upgraded_native_path.read_text())
   upgraded_identity=validate_child(upgraded_native,args.architecture,system,upgraded_executable,upgraded_expected)
   require(upgraded_identity==identity,'Upgraded process identity changed')
   require_process_exited(upgraded_native.get('process_id'),system)
   require(snapshot(ordinary)==ordinary_before,'Ordinary Krita changed during upgraded launch')
   require(snapshot([artwork])==creations,'Upgraded launch changed prior artwork')
   require(snapshot([final])==old_runtime,'Upgraded launch changed previous runtime')
   artifact('upgraded_native_probe',upgraded_native_path)
   result.update(upgraded_runtime_tested=True,upgraded_native_child_exit_observed=True,upgraded_executable={'archive_path':upgraded_member,'sha256':upgraded_expected},upgraded_native_probe_sha256=sha(upgraded_native_path))
   require(sha(archive)==original_sha,'Candidate archive changed during qualification');result['passed']=True
 except Exception as exc:
  result['error']=str(exc);raise
 finally:write()
 print('Installed runtime journey passed. No source closure or release qualification claimed.')
if __name__=='__main__':main()
