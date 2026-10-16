"""Disposable native installer -> real launcher -> painting/profile preservation.
No SDK environment, network mocks, signing bypass or automated security approval.
Local test manifests are never release qualification or publication.
"""
import argparse,ctypes,hashlib,json,os,platform,shutil,subprocess,sys,tempfile,time,uuid
from pathlib import Path

def knownfolder(identifier):
 raw=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identifier).bytes_le);value=ctypes.c_wchar_p()
 hr=ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw),0,None,ctypes.byref(value))
 if hr:raise OSError(hr,'KnownFolder lookup failed')
 try:return Path(value.value)
 finally:ctypes.windll.ole32.CoTaskMemFree(value)
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def snapshot(paths):
 result={}
 for path in paths:
  if path.is_dir():result.update({str(p):sha(p) for p in path.rglob('*') if p.is_file() and not p.is_symlink()})
  elif path.is_file():result[str(path)]=sha(path)
 return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--manifest',required=True,type=Path);parser.add_argument('--probe',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--timeout',type=int,default=200);args=parser.parse_args()
 system=platform.system();assert system in ('Windows','Darwin') and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('CI')=='true','Disposable native hosted runner only'
 root=Path(__file__).parent;output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);result={'platform':platform.platform(),'scope':'actual installed native runtime; no SDK fallback','release_qualified':False,'binary_published':False,'security_approval_automated':False,'downloaded_user_security_approval_tested':False}
 manifest=json.loads(args.manifest.read_text());assert manifest['sha256']==sha(args.archive) and manifest['kind']=='namespaced-compiled-fork' and manifest['profileNamespace']=='flapart-native'
 assert manifest['status'] in ('ci-candidate','qualified')
 # CI-only local eligibility enables the mechanics under test; freeze-release.py
 # separately requires full exact-payload evidence and corresponding-source closure.
 manifest['status']='qualified'
 if system=='Windows':
  config=knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');data=knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D');ordinary=[config/'kritarc',config/'kritadisplayrc',config/'kritashortcutsrc',data/'krita',config/'krita.log',config/'krita-sysinfo.log']
 else:
  config=Path.home()/'Library/Preferences';data=Path.home()/'Library/Application Support';ordinary=[config/'kritarc',config/'kritadisplayrc',config/'kritashortcutsrc',data/'krita',data/'krita.log',data/'krita-sysinfo.log']
 settings=config/'flapartnativerc';profile=data/'flapart-native'
 assert not settings.exists() and not profile.exists(),'Use a fresh CI profile; existing Flapart settings are never replaced'
 config.mkdir(parents=True,exist_ok=True)
 for p in ordinary:
  if p.name=='krita':p=p/'INSTALLER_QA_KEEP.txt'
  p.parent.mkdir(parents=True,exist_ok=True)
  if not p.exists():p.write_bytes(b'ORIGINAL-KRITA-INSTALLER-SENTINEL\n')
 ordinary_before=snapshot(ordinary)
 with tempfile.TemporaryDirectory(prefix='flapart-installer-e2e-',dir=os.environ['RUNNER_TEMP']) as work:
  work=Path(work);source=work/'installer';source.mkdir();dest=work/'installed';artwork=output/'native-first';artwork.mkdir()
  for pattern in ('*.exe','*.command','*.ttf'):
   for f in root.glob(pattern):shutil.copy2(f,source/f.name)
  (source/'release.json').write_text(json.dumps(manifest))
  def install(archive):
   if system=='Windows':command=[str(source/'Install Flapart.exe'),'--quiet','--archive',str(archive.resolve()),'--destination',str(dest),'--no-shortcut']
   else:command=['/bin/bash',str(source/'Install Flapart.command'),str(archive.resolve()),str(dest)]
   return subprocess.run(command,capture_output=True,text=True,timeout=900)
  installed=install(args.archive);(output/'install.log').write_text(installed.stdout+installed.stderr);assert installed.returncode==0,'See install.log'
  receipt=dest/'flapart-install.json';record=json.loads(receipt.read_text());final=dest/'releases'/record['release'];assert snapshot(ordinary)==ordinary_before
  plugins=profile/'pykrita';plugins.mkdir(parents=True);settings.write_text('[python]\nenable_flapart=true\nenable_flapart_probe=true\n')
  shutil.copy2(args.probe/'flapart_probe.desktop',plugins/'flapart_probe.desktop');shutil.copytree(args.probe/'flapart_probe',plugins/'flapart_probe',ignore=shutil.ignore_patterns('__pycache__'))
  env=dict(os.environ,FLAPART_NATIVE='1',FLAPART_QA_EXPECT_COMPILED='1',FLAPART_QA_OUTPUT=str(artwork))
  # Runtime must locate its own Python, Qt and DLL/frameworks after deployment.
  for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','DYLD_FRAMEWORK_PATH','DYLD_FALLBACK_LIBRARY_PATH','LD_LIBRARY_PATH'):env.pop(key,None)
  # Avoid SDK tools accidentally satisfying runtime dependency search.
  if system=='Windows':env['PATH']=os.pathsep.join([str(Path(os.environ['WINDIR'])/'System32'),os.environ['WINDIR']])
  else:env['PATH']='/usr/bin:/bin:/usr/sbin:/sbin'
  if system=='Windows':command=[str(final/'Flapart Studio.exe'),'--launch','--wait']
  else:command=['/bin/bash',str(dest/'Flapart Studio.command')]
  with (output/'launcher.log').open('w') as log:
   process=subprocess.Popen(command,env=env,stdout=log,stderr=log)
   try:process.wait(timeout=args.timeout)
   except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10);raise RuntimeError('Launcher timeout; no system security approval was automated')
  deadline=time.monotonic()+args.timeout
  while not (artwork/'result.json').exists() and time.monotonic()<deadline:time.sleep(.5)
  if not (artwork/'result.json').exists():
   result.update(installer_passed=True,native_runtime_tested=False,blocked='No native probe receipt through normal launch. Inspect launcher.log and system security review; do not bypass it.')
   (output/'installer-e2e.json').write_text(json.dumps(result,indent=2)+'\n');raise RuntimeError(result['blocked'])
  native=json.loads((artwork/'result.json').read_text());assert 'error' not in native,native.get('error')
  for key in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action','action_reopens'):assert native.get(key) is True,key
  assert native['canvas']==[64,64] and native['round_trip']==[64,64,'Draw here'] and native['round_trip_pixel']==[70,110,191,255]
  assert native['browser_handoff']==['https://flaptown.com/flapart/?from=native&destination=profile'];assert native['application_font']=='Syne Mono'
  assert snapshot(ordinary)==ordinary_before,'Ordinary Krita changed'
  creations=snapshot([artwork]);profile_paths=[profile,*config.glob('flapartnative*')];user_profile=snapshot(profile_paths);before=receipt.read_bytes()
  corrupt=work/'corrupt.zip';corrupt.write_bytes(b'not the pinned payload');refused=install(corrupt);assert refused.returncode!=0 and receipt.read_bytes()==before
  assert snapshot([artwork])==creations and snapshot(profile_paths)==user_profile
  # Exercise successful upgrade with exactly the same reviewed engine bytes under
  # a CI-only edition tag; this is not a separately published app version.
  manifest['version']=manifest['version']+'-ci-upgrade';(source/'release.json').write_text(json.dumps(manifest));upgraded=install(args.archive);(output/'upgrade.log').write_text(upgraded.stdout+upgraded.stderr);assert upgraded.returncode==0
  assert snapshot([artwork])==creations and snapshot(profile_paths)==user_profile and snapshot(ordinary)==ordinary_before
  assert final.exists() and json.loads(receipt.read_text())['release']!=record['release']
  result.update(installer_passed=True,native_runtime_tested=True,profile_isolation_verified=True,ordinary_krita_unchanged=True,native_canvas_png_kra_passed=True,studio_menu_reopens=True,failed_upgrade_preserved_receipt=True,successful_upgrade_preserved_artwork_and_settings=True,previous_runtime_retained=True,payload_sha256=manifest['sha256'])
  (output/'installer-e2e.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Native installed launcher, painting, exact KRA roundtrip, profile and upgrade preservation passed. No publication performed.')
if __name__=='__main__':main()
