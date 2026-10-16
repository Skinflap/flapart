#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Mac CI qualification for a locally built namespaced Flapart application."""
import argparse,pathlib,platform,os,subprocess,json,shutil,hashlib,time,signal
p=argparse.ArgumentParser();p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--probe',required=True,type=pathlib.Path);p.add_argument('--output',required=True,type=pathlib.Path);p.add_argument('--timeout',type=int,default=150);a=p.parse_args()
if platform.system()!='Darwin':raise SystemExit('Native macOS runner required.')
if os.environ.get('CI')!='true':raise SystemExit('Use only a disposable CI profile (CI=true); this harness writes test settings.')
prefix=a.prefix.resolve();probe=a.probe.resolve();output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
candidates=[prefix/'bin/krita.app/Contents/MacOS/krita',prefix/'bin/Flapart Native.app/Contents/MacOS/krita',prefix/'bin/krita']
candidates += sorted(prefix.glob('**/*.app/Contents/MacOS/krita'))
executable=next((x for x in candidates if x.is_file()),None)
if executable is None:raise SystemExit('No installed Krita/Flapart executable under prefix.')
home=pathlib.Path.home();config=home/'Library/Preferences';support=home/'Library/Application Support';data=support/'flapart-native';plugins=data/'pykrita';plugins.mkdir(parents=True,exist_ok=True);config.mkdir(parents=True,exist_ok=True)
settings=config/'flapartnativerc'
if settings.exists():raise SystemExit('Refusing to overwrite existing Flapart settings; use a fresh CI runner.')
settings.write_text('[python]\nenable_flapart=true\nenable_flapart_probe=true\n')
shutil.copy2(probe/'flapart_probe.desktop',plugins/'flapart_probe.desktop');shutil.copytree(probe/'flapart_probe',plugins/'flapart_probe',ignore=shutil.ignore_patterns('__pycache__'))
sentinels={}
for path in (config/'kritarc',config/'kritadisplayrc',config/'kritashortcutsrc',support/'krita/FLAPART_QA_KEEP.txt',support/'krita.log',support/'krita-sysinfo.log'):
 path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():path.write_bytes(b'ORIGINAL-KRITA-SENTINEL\n')
 sentinels[path]=hashlib.sha256(path.read_bytes()).hexdigest()
framework=prefix/'lib/Python.framework';versions=framework/'Versions';pythonhome=versions/'Current'
if not pythonhome.exists():
 found=sorted(p for p in versions.glob('3.*') if p.is_dir());pythonhome=found[-1] if found else None
site=[]
if pythonhome:site += list(pythonhome.glob('lib/python*/site-packages'))
site += list(prefix.glob('lib/python*/site-packages'))
# Keep the embedded SDK Python and Qt separate from Homebrew/runtime-host packages.
env=dict(os.environ,FLAPART_NATIVE='1',FLAPART_QA_EXPECT_COMPILED='1',FLAPART_QA_OUTPUT=str(output),PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH'],DYLD_FRAMEWORK_PATH=str(prefix/'lib'),DYLD_FALLBACK_LIBRARY_PATH=str(prefix/'lib'),PYTHONPATH=os.pathsep.join(map(str,site)),QT_PLUGIN_PATH=str(prefix/'plugins'))
if pythonhome:env['PYTHONHOME']=str(pythonhome)
receipt=output/'result.json'
if receipt.exists():raise SystemExit('Output already contains a receipt; use a fresh output directory.')
with (output/'runtime.log').open('w') as log:
 process=subprocess.Popen([str(executable),'--nosplash'],env=env,stdout=log,stderr=log,start_new_session=True)
 try:process.wait(timeout=a.timeout)
 except subprocess.TimeoutExpired:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
if not receipt.exists():raise SystemExit('No native result.json; inspect runtime.log and Flapart native logs.')
result=json.loads(receipt.read_text());print(json.dumps(result,indent=2))
assert process.returncode==0 and 'error' not in result
for key in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action'):assert result.get(key) is True,key
assert result['canvas']==[64,64] and result['round_trip']==[64,64,'Draw here'] and result['round_trip_pixel']==[70,110,191,255]
assert result['browser_handoff']==['https://flaptown.com/flapart/?from=native&destination=profile']
assert all(path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest for path,digest in sentinels.items()),'Original Krita sentinel changed'
qualification={'platform':platform.platform(),'architecture':platform.machine(),'native_runtime_test':True,'original_krita_sentinels_preserved':True,'compiled_fork':True,'signed':False,'notarized':False,'physical_tablet_tested':False}
(output/'qualification.json').write_text(json.dumps(qualification,indent=2)+'\n');print('Native source application probe and Krita namespace preservation passed.')
