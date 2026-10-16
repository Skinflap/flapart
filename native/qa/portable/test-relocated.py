#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-test a packaged runtime with temporary Flapart-only settings in disposable CI."""
import argparse,pathlib,platform,os,json,shutil,subprocess,sys,ctypes,uuid,tempfile,contextlib

def present(path):return path.exists() or path.is_symlink()
def remove_test_path(path):
 if path.is_symlink() or path.is_file():path.unlink()
 elif path.exists():shutil.rmtree(path)

@contextlib.contextmanager
def preserved_profile(paths,temporary_parent=None):
 """Restore original profiles even on failure; retain backups if restoration fails."""
 paths=[pathlib.Path(p) for p in paths]
 assert len(set(paths))==len(paths) and len({p.name for p in paths})==len(paths)
 backup=pathlib.Path(tempfile.mkdtemp(prefix='flapart-prior-profile-',dir=temporary_parent))
 prepared=[];errors=[]
 try:
  for path in paths:
   saved=backup/path.name;existed=present(path)
   if existed:shutil.move(str(path),str(saved))
   prepared.append((path,saved,existed))
  yield
 finally:
  # Only prepared paths belong to the temporary profile. A setup failure must
  # not delete untouched originals. Continue restoring other paths after errors.
  for path,saved,existed in reversed(prepared):
   try:
    remove_test_path(path)
    if existed:
     if not present(saved):raise OSError('Original profile backup missing: '+str(saved))
     path.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(saved),str(path))
   except OSError as error:errors.append(str(error))
  if errors or any(backup.iterdir()):
   raise RuntimeError('Flapart profile restoration incomplete; retained backup at '+str(backup)+'; '+'; '.join(errors))
  backup.rmdir()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--probe',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--previous-qualification',type=pathlib.Path,required=True);p.add_argument('--process-architecture',choices=('arm64','x86_64'),help='Mac-only: execute and verify this application process architecture');a=p.parse_args()
 system=platform.system()
 if os.environ.get('CI')!='true' or system not in ('Darwin','Windows'):raise SystemExit('Disposable native Mac/Windows CI required.')
 if a.process_architecture and system!='Darwin':raise SystemExit('--process-architecture is supported only by the Mac application harness.')
 previous=json.loads(a.previous_qualification.read_text());assert previous.get('compiled_fork') and previous.get('original_krita_sentinels_preserved'),'Require prior successful prefix qualification in this runner'
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 if any(out.iterdir()):raise SystemExit('Relocation output must be empty.')
 if system=='Darwin':
  config=pathlib.Path.home()/'Library/Preferences';data=pathlib.Path.home()/'Library/Application Support/flapart-native';target='macos'
 else:
  def knownfolder(identifier):
   raw=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identifier).bytes_le);value=ctypes.c_wchar_p();hr=ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw),0,None,ctypes.byref(value))
   if hr:raise OSError(hr,'Known Folder lookup failed')
   try:return pathlib.Path(value.value)
   finally:ctypes.windll.ole32.CoTaskMemFree(value)
  config=knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');data=knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D')/'flapart-native';target='windows'
 paths=[config/'flapartnativerc',config/'flapartnativedisplayrc',config/'flapartnativeshortcutsrc',data]
 # Ordinary Krita paths remain untouched. Preserve the preceding probe's profile
 # through sequential ARM/Intel runs, including helper failures and timeouts.
 with preserved_profile(paths,os.environ.get('RUNNER_TEMP')):
  with tempfile.TemporaryDirectory(prefix='flapart-relocated-',dir=os.environ.get('RUNNER_TEMP')) as temporary:
   relocated=pathlib.Path(temporary)/'runtime';relocated.mkdir();candidate=a.candidate.resolve();copy=relocated/candidate.name
   shutil.copytree(candidate,copy,symlinks=True)
   helper=pathlib.Path(__file__).resolve().parents[1]/(target+'-build')/'test-compiled.py'
   command=[sys.executable,str(helper),'--packaged','--prefix',str(copy),'--probe',str(a.probe.resolve()),'--output',str(out/'runtime')]
   if a.process_architecture:command+=['--process-architecture',a.process_architecture]
   subprocess.run(command,check=True)
 result=json.loads((out/'runtime/qualification.json').read_text());assert result['relocated_package_test']
 if a.process_architecture:assert result['process_architecture']==a.process_architecture,'Relocated application did not use requested process architecture'
 print('Relocated package native probe passed without SDK/Python/compiler environment; prior Flapart profile restored.')

if __name__=='__main__':main()
