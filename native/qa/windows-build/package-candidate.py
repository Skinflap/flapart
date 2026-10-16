#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a local Windows candidate with upstream runtime deployment rules."""
import argparse,pathlib,platform,os,subprocess,sys,json,hashlib,shutil,importlib.util
from python_runtime_paths import relocated_lines
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--tools',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
if platform.system()!='Windows':raise SystemExit('Run on native Windows after the compiled fork probe passes.')
source=a.source.resolve();prefix=a.prefix.resolve();tools=a.tools.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Candidate output must be empty.')
assert 'flapartnativerc' in (source/'krita/main.cc').read_text()
llvm=tools/'llvm-mingw-20251118-ucrt-x86_64/bin'
env=dict(os.environ,MINGW_BIN_DIR=str(llvm),KRITACI_SKIP_SPLIT_DEBUG='1',KRITA_SKIP_DEBUG_PACKAGE='1')
# Windows10/11 supply D3DCompiler_47.dll. Keep it as an explicit OS
# dependency rather than copying System32 or requiring SDK redistribution.
assert sys.getwindowsversion().major>=10, 'This candidate requires Windows10 or later'
system_d3d=pathlib.Path(os.environ['SystemRoot'])/'System32/d3dcompiler_47.dll'
assert system_d3d.is_file(), 'Required OS D3D compiler is unavailable'
help_env=dict(env,PATH=str(llvm.parent/'x86_64-w64-mingw32/bin')+os.pathsep+str(prefix/'bin')+os.pathsep+env['PATH'])
help_result=subprocess.run([str(prefix/'bin/windeployqt.exe'),'--help'],env=help_env,capture_output=True,text=True,check=True)
assert '--no-system-d3d-compiler' in help_result.stdout
# Adapt a private copy of the pinned upstream packager; preserve source checkout.
upstream=source/'packaging/windows/package-complete.py';original=upstream.read_text()
needle='["windeployqt.exe", *QMLDIR_ARGS,'
assert original.count(needle)==2, 'Upstream deployment call sites changed'
adapted=original.replace(needle,'["windeployqt.exe", "--no-system-d3d-compiler", *QMLDIR_ARGS,')
path_needle="{os.environ['MINGW_BIN_DIR']};{DEPS_INSTALL_DIR}"
assert adapted.count(path_needle)==1, 'Upstream build-tool PATH changed'
adapted=adapted.replace(path_needle,"{os.environ['MINGW_BIN_DIR']};{os.environ['MINGW_BIN_DIR']}\\..\\x86_64-w64-mingw32\\bin;{DEPS_INSTALL_DIR}")
driver_dir=out/'packaging-driver';driver_dir.mkdir();driver=driver_dir/'package-complete.py';driver.write_text(adapted)
shutil.copytree(source/'packaging/windows/components',driver_dir/'components',ignore=shutil.ignore_patterns('__pycache__'))
subprocess.run([sys.executable,str(driver),'--no-interactive','--package-name','Flapart-Studio','--src-dir',str(source),'--deps-install-dir',str(prefix),'--krita-install-dir',str(prefix)],cwd=out,env=env,check=True)
root=out/'Flapart-Studio';assert (root/'bin/krita.exe').is_file()
assert not any(root.rglob('d3dcompiler_*.dll')), 'D3D compiler must remain an OS dependency'
# Keep the maintained embedded interpreter available for scripts and actual
# runtime qualification. Upstream removes these entry points after copying.
for name in ('python.exe','pythonw.exe'):
 source_python=prefix/'python'/name
 assert source_python.is_file(), ('Maintained interpreter missing',name)
 shutil.copy2(source_python,root/'python'/name)
pth=root/'python/python313._pth';assert pth.is_file()
python_paths=relocated_lines(pth.read_text(encoding='utf-8'),prefix)
for line in python_paths:
 if line=='import site':continue
 target=(root/'python'/line).resolve()
 assert target.is_relative_to(root.resolve()) and target.exists(),('Missing packaged Python path',line)
pth.write_text('\n'.join(python_paths)+'\n',encoding='utf-8')
# pyqtbuild is a build-only bundler, not PyQt5 or its runtime SIP module.
# Its optional DLL collection includes obsolete OpenSSL and unrelated MSVC
# runtimes; upstream removes its metadata but leaves this lowercase package.
build_only_package=root/'lib/site-packages/pyqtbuild'
if build_only_package.exists():shutil.rmtree(build_only_package)
assert not build_only_package.exists()
metadata_path=pathlib.Path(__file__).resolve().parents[2]/'distribution/source-qualification/native_metadata.py'
assert metadata_path.is_file(), 'Reviewed PE import parser is required'
spec=importlib.util.spec_from_file_location('flapart_native_metadata',metadata_path)
metadata=importlib.util.module_from_spec(spec);spec.loader.exec_module(metadata)
old_ssl={'libssl-1_1-x64.dll','libcrypto-1_1-x64.dll','libssl-1_1.dll','libcrypto-1_1.dll','ssleay32.dll','libeay32.dll'}
retired=[];native_count=0
for native_file in sorted(root.rglob('*')):
 if not native_file.is_file() or native_file.suffix.lower() not in ('.dll','.pyd','.exe'):continue
 if native_file.name.casefold() in old_ssl:
  retired.append(native_file);continue
 info=metadata.parse(native_file.read_bytes())
 assert info and info['format']=='pe' and info['architectures']==['x86_64'],('Unexpected runtime architecture',native_file)
 native_count+=1
 assert not any(name.casefold() in old_ssl for name in info['native_dependencies']),('Unrebuilt OpenSSL1.1 consumer',native_file)
retired_files=[{'path':f.relative_to(out).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in retired]
for f in retired:f.unlink()
# Preserve upstream notices; remove an upstream desktop shortcut pointing to its old name.
(root/'krita.lnk').unlink(missing_ok=True)
(root/'Flapart.cmd').write_text('@echo off\r\nstart "Flapart Studio" "%~dp0bin\\krita.exe" %*\r\n')
files=[]
for f in sorted(root.rglob('*')):
 if f.is_file():files.append({'path':f.relative_to(out).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
# The upstream pre-customization ZIP is not a release artifact; retain the folder only.
(out/'Flapart-Studio.zip').unlink(missing_ok=True)
(out/'candidate-inventory.json').write_text(json.dumps({'product':'Flapart Studio','platform':'windows-x86_64','entrypoint':'Flapart-Studio/bin/krita.exe','minimum_windows':'10','required_system_dlls':['d3dcompiler_47.dll'],'system_d3d_loading_and_angle_render_qualified':False,'packager_source_sha256':hashlib.sha256(original.encode()).hexdigest(),'packager_adapter_sha256':hashlib.sha256(adapted.encode()).hexdigest(),'python_path_entries':python_paths,'native_imports_checked':native_count,'retired_old_ssl':retired_files,'build_only_pyqtbuild_omitted':True,'runtime_collected':True,'relocation_test_passed':False,'source_closure_complete':False,'publishable':False,'files':files},indent=2)+'\n')
print('Local candidate folder assembled. Relocation, native probe and source/license closure still required; not publishable.')
