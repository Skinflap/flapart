#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a local Windows candidate with upstream runtime deployment rules."""
import argparse,pathlib,platform,os,subprocess,sys,json,hashlib,shutil
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--tools',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
if platform.system()!='Windows':raise SystemExit('Run on native Windows after the compiled fork probe passes.')
source=a.source.resolve();prefix=a.prefix.resolve();tools=a.tools.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Candidate output must be empty.')
assert 'flapartnativerc' in (source/'krita/main.cc').read_text()
llvm=tools/'llvm-mingw-20251118-ucrt-x86_64/bin'
env=dict(os.environ,MINGW_BIN_DIR=str(llvm),KRITACI_SKIP_SPLIT_DEBUG='1',KRITA_SKIP_DEBUG_PACKAGE='1')
# Upstream obtains D3D compiler redistribution files from the installed Windows SDK,
# never by copying arbitrary System32 DLLs. Fail if the redistributable SDK is absent.
sdk=pathlib.Path(os.environ.get('WindowsSdkDir',os.environ.get('ProgramFiles(x86)','')+'/Windows Kits/10'))
if not sdk.is_dir():raise SystemExit('Windows SDK redist directory required by windeployqt.')
env['WindowsSdkDir']=str(sdk)
subprocess.run([sys.executable,str(source/'packaging/windows/package-complete.py'),'--no-interactive','--package-name','Flapart-Studio','--src-dir',str(source),'--deps-install-dir',str(prefix),'--krita-install-dir',str(prefix)],cwd=out,env=env,check=True)
root=out/'Flapart-Studio';assert (root/'bin/krita.exe').is_file()
# Preserve upstream notices; remove an upstream desktop shortcut pointing to its old name.
(root/'krita.lnk').unlink(missing_ok=True)
(root/'Flapart.cmd').write_text('@echo off\r\nstart "Flapart Studio" "%~dp0bin\\krita.exe" %*\r\n')
files=[]
for f in sorted(root.rglob('*')):
 if f.is_file():files.append({'path':f.relative_to(root).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
# The upstream pre-customization ZIP is not a release artifact; retain the folder only.
(out/'Flapart-Studio.zip').unlink(missing_ok=True)
(out/'candidate-inventory.json').write_text(json.dumps({'product':'Flapart Studio','platform':'windows-x86_64','entrypoint':'Flapart-Studio/bin/krita.exe','runtime_collected':True,'relocation_test_passed':False,'source_closure_complete':False,'publishable':False,'files':files},indent=2)+'\n')
print('Local candidate folder assembled. Relocation, native probe and source/license closure still required; not publishable.')
