#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Windows CI test; settings paths come from Windows Known Folders."""
import argparse,ctypes,uuid,pathlib,platform,os,subprocess,json,shutil,hashlib
p=argparse.ArgumentParser();p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--probe',required=True,type=pathlib.Path);p.add_argument('--output',required=True,type=pathlib.Path);p.add_argument('--timeout',type=int,default=180);a=p.parse_args()
if platform.system()!='Windows' or os.environ.get('CI')!='true':raise SystemExit('Requires a disposable native Windows CI profile (CI=true).')
def knownfolder(identifier):
 raw=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identifier).bytes_le);result=ctypes.c_wchar_p()
 shell=ctypes.windll.shell32;hr=shell.SHGetKnownFolderPath(ctypes.byref(raw),0,None,ctypes.byref(result))
 if hr:raise OSError(hr,'SHGetKnownFolderPath failed')
 try:return pathlib.Path(result.value)
 finally:ctypes.windll.ole32.CoTaskMemFree(result)
local=knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');roaming=knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D')
prefix=a.prefix.resolve();probe=a.probe.resolve();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
executable=prefix/'bin/krita.exe';assert executable.is_file(),str(executable)
settings=local/'flapartnativerc';plugins=roaming/'flapart-native/pykrita'
if settings.exists() or plugins.exists():raise SystemExit('Refusing existing Flapart profile; use a fresh disposable runner.')
plugins.mkdir(parents=True);settings.write_text('[python]\nenable_flapart=true\nenable_flapart_probe=true\n')
shutil.copy2(probe/'flapart_probe.desktop',plugins/'flapart_probe.desktop');shutil.copytree(probe/'flapart_probe',plugins/'flapart_probe',ignore=shutil.ignore_patterns('__pycache__'))
sentinels={}
for path in (local/'kritarc',local/'kritadisplayrc',local/'kritashortcutsrc',roaming/'krita/FLAPART_QA_KEEP.txt',local/'krita.log',local/'krita-sysinfo.log'):
 path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():path.write_bytes(b'ORIGINAL-KRITA-SENTINEL\n')
 sentinels[path]=hashlib.sha256(path.read_bytes()).hexdigest()
env=dict(os.environ,FLAPART_NATIVE='1',FLAPART_QA_EXPECT_COMPILED='1',FLAPART_QA_OUTPUT=str(output),PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH'],PYTHONHOME=str(prefix/'python'),PYTHONPATH=str(prefix/'lib/site-packages'),QT_PLUGIN_PATH=str(prefix/'plugins'))
receipt=output/'result.json'
if receipt.exists():raise SystemExit('Output already contains a receipt; use a fresh output directory.')
with (output/'runtime.log').open('w') as log:
 process=subprocess.Popen([str(executable),'--nosplash'],env=env,stdout=log,stderr=log)
 try:process.wait(timeout=a.timeout)
 except subprocess.TimeoutExpired:
  process.terminate()
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:process.kill();process.wait()
if not receipt.exists():raise SystemExit('No native result.json; inspect runtime.log and Flapart native logs.')
result=json.loads(receipt.read_text());print(json.dumps(result,indent=2));assert process.returncode==0 and 'error' not in result
for key in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action'):assert result.get(key) is True,key
assert result['canvas']==[64,64] and result['round_trip']==[64,64,'Draw here'] and result['round_trip_pixel']==[70,110,191,255]
assert result['browser_handoff']==['https://flaptown.com/flapart/?from=native&destination=profile']
assert all(path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in sentinels.items()),'Original Krita sentinel changed'
(output/'qualification.json').write_text(json.dumps({'platform':platform.platform(),'architecture':platform.machine(),'native_runtime_test':True,'original_krita_sentinels_preserved':True,'compiled_fork':True,'signed':False,'physical_tablet_tested':False},indent=2)+'\n')
print('Native Windows source application probe and Krita namespace preservation passed.')
