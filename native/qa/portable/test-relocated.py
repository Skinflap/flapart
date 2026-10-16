#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-test a packaged runtime with fresh Flapart-only settings in disposable CI."""
import argparse,pathlib,platform,os,json,shutil,subprocess,sys,ctypes,uuid,tempfile
p=argparse.ArgumentParser();p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--probe',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--previous-qualification',type=pathlib.Path,required=True);a=p.parse_args()
if os.environ.get('CI')!='true' or platform.system() not in ('Darwin','Windows'):raise SystemExit('Disposable native Mac/Windows CI required.')
previous=json.loads(a.previous_qualification.read_text());assert previous.get('compiled_fork') and previous.get('original_krita_sentinels_preserved'),'Require prior successful prefix qualification in this runner'
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Relocation output must be empty.')
if platform.system()=='Darwin':
 config=pathlib.Path.home()/'Library/Preferences';data=pathlib.Path.home()/'Library/Application Support/flapart-native';target='macos'
else:
 def knownfolder(identifier):
  raw=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identifier).bytes_le);value=ctypes.c_wchar_p();hr=ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw),0,None,ctypes.byref(value))
  if hr:raise OSError(hr,'Known Folder lookup failed')
  try:return pathlib.Path(value.value)
  finally:ctypes.windll.ole32.CoTaskMemFree(value)
 config=knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');data=knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D')/'flapart-native';target='windows'
# The preceding CI probe refused preexisting Flapart settings. Preserve its files
# outside the new test profile, leaving every ordinary Krita path untouched.
with tempfile.TemporaryDirectory(prefix='flapart-relocated-',dir=os.environ.get('RUNNER_TEMP')) as temporary:
 temporary=pathlib.Path(temporary)
 backup=temporary/'prior-flapart-profile';backup.mkdir()
 for path in [config/'flapartnativerc',config/'flapartnativedisplayrc',config/'flapartnativeshortcutsrc',data]:
  if path.exists():shutil.move(str(path),str(backup/path.name))
 # Keep runtime binaries OUTSIDE evidence; workflow artifacts must contain receipts only.
 relocated=temporary/'runtime';relocated.mkdir();candidate=a.candidate.resolve();copy=relocated/candidate.name
 shutil.copytree(candidate,copy,symlinks=True)
 helper=pathlib.Path(__file__).resolve().parents[1]/(target+'-build')/'test-compiled.py'
 subprocess.run([sys.executable,str(helper),'--packaged','--prefix',str(copy),'--probe',str(a.probe.resolve()),'--output',str(out/'runtime')],check=True)
result=json.loads((out/'runtime/qualification.json').read_text());assert result['relocated_package_test'];print('Relocated package native probe passed without SDK/Python/compiler environment.')
