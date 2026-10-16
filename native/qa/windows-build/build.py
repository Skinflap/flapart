#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a prepared Flapart source checkout with the exact official Windows ABI."""
import argparse,os,pathlib,platform,subprocess,json,re,sys
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--build',required=True,type=pathlib.Path);p.add_argument('--tools',required=True,type=pathlib.Path);p.add_argument('--python-root',type=pathlib.Path,default=pathlib.Path(sys.base_prefix));p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
if platform.system()!='Windows':raise SystemExit('Run this helper in Windows with Python3.13 including its development headers.')
source=a.source.resolve();prefix=a.prefix.resolve();build=a.build.resolve();tools=a.tools.resolve();python=a.python_root.resolve()
assert 'flapartnativerc' in (source/'krita/main.cc').read_text(),'Prepare the pinned source fork first.'
assert (python/'include/Python.h').is_file(),'Full Python development installation required; embedded-only Python lacks headers.'
llvm=tools/'llvm-mingw-20251118-ucrt-x86_64/bin';cmake=tools/'cmake-3.31.8-windows-x86_64/bin/cmake.exe';ninja=tools/'ninja.exe'
for path in (llvm/'x86_64-w64-mingw32-clang.exe',cmake,ninja,python/'python.exe'):assert path.is_file(),str(path)
# The SDK Python313 runtime and PyQt5 bind to Python3.13; use the same full SDK ABI.
env=dict(os.environ,PATH=os.pathsep.join(map(str,[prefix/'bin',llvm,tools,cmake.parent,python]))+os.pathsep+os.environ['PATH'],PYTHONPATH=str(prefix/'lib/site-packages'),PKG_CONFIG_PATH=str(prefix/'lib/pkgconfig'))
args=[str(cmake),'-S',str(source),'-B',str(build),'-G','Ninja','-DCMAKE_MAKE_PROGRAM='+ninja.as_posix(),'-DCMAKE_BUILD_TYPE=Release','-DBUILD_TESTING=OFF','-DBUILD_WITH_QT6=OFF','-DCMAKE_C_COMPILER='+(llvm/'x86_64-w64-mingw32-clang.exe').as_posix(),'-DCMAKE_CXX_COMPILER='+(llvm/'x86_64-w64-mingw32-clang++.exe').as_posix(),'-DCMAKE_RC_COMPILER='+(llvm/'x86_64-w64-mingw32-windres.exe').as_posix(),'-DCMAKE_PREFIX_PATH='+prefix.as_posix(),'-DCMAKE_INSTALL_PREFIX='+prefix.as_posix(),'-DPython_ROOT_DIR='+python.as_posix(),'-DPython_EXECUTABLE='+(python/'python.exe').as_posix(),'-DPYQT_SIP_DIR_OVERRIDE='+(prefix/'lib/site-packages/PyQt5/bindings').as_posix()]
for config in prefix.rglob('QtCore.toml'):
 match=re.search(r'sip-abi-version\s*=\s*"([^"]+)"',config.read_text())
 if match:args.append('-DFLAPART_SIP_ABI_VERSION='+match.group(1));break
for command in (args,[str(cmake),'--build',str(build),'-j',str(max(1,a.jobs))],[str(cmake),'--install',str(build)]):subprocess.run(command,env=env,check=True)
(build/'flapart-build-receipt.json').write_text(json.dumps({'platform':platform.platform(),'architecture':platform.machine(),'source_commit':'bd6e8d061d2f0388c5b10278786cf0fe62e3135f','compiler':'LLVM-MinGW20251118 Clang21.1.6','compiled':True,'runtime_qualified':False,'signed':False},indent=2))
print('Native Windows build installed. Run the native probe and sentinel checks before any release claim.')
