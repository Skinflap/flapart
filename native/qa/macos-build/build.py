#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a prepared namespaced Flapart source checkout on an actual Mac runner."""
import argparse,os,pathlib,platform,subprocess,json,re
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--prefix',required=True,type=pathlib.Path);p.add_argument('--build',required=True,type=pathlib.Path);p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
if platform.system()!='Darwin':raise SystemExit('Run on an actual macOS host.')
source=a.source.resolve();prefix=a.prefix.resolve();build=a.build.resolve()
assert (source/'krita/main.cc').is_file() and 'flapartnativerc' in (source/'krita/main.cc').read_text(),'Apply native/scripts/prepare-fork.py first.'
arch=platform.machine();target='11.0' if arch=='arm64' else '10.15'
pythonhome=prefix/'lib/Python.framework/Versions/Current'
site=next(pythonhome.glob('lib/python*/site-packages'))
bindings=site/'PyQt5/bindings'
assert (bindings/'QtCore/QtCoremod.sip').is_file(), 'Missing SDK PyQt bindings'
env=dict(os.environ,PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH'],CMAKE_PREFIX_PATH=str(prefix),MACOSX_DEPLOYMENT_TARGET=target,QMAKE_MACOSX_DEPLOYMENT_TARGET=target,PYTHONHOME=str(pythonhome),PYTHONPATH=str(site),DYLD_FRAMEWORK_PATH=str(prefix/'lib'))
args=['cmake','-S',str(source),'-B',str(build),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DBUILD_TESTING=OFF','-DBUILD_WITH_QT6=OFF','-DCMAKE_PREFIX_PATH='+str(prefix),'-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DKDE_INSTALL_BUNDLEDIR=bin','-DPYQT_SIP_DIR_OVERRIDE='+str(bindings),'-DPython_ROOT_DIR='+str(pythonhome),'-DPython_EXECUTABLE='+str(prefix/'bin/python3'),'-DPYTHON_INCLUDE_DIR='+str(prefix/'lib/Python.framework/Headers'),'-DCMAKE_OSX_ARCHITECTURES='+arch,'-DCMAKE_OSX_DEPLOYMENT_TARGET='+target]
for config in prefix.rglob('QtCore.toml'):
 match=re.search(r'sip-abi-version\s*=\s*"([^"]+)"',config.read_text())
 if match:args.append('-DFLAPART_SIP_ABI_VERSION='+match.group(1));break
for command in (args,['cmake','--build',str(build),'-j',str(max(1,a.jobs))],['cmake','--install',str(build)]):subprocess.run(command,env=env,check=True)
(build/'flapart-build-receipt.json').write_text(json.dumps({'platform':platform.platform(),'architecture':arch,'source_commit':'bd6e8d061d2f0388c5b10278786cf0fe62e3135f','compiled':True,'runtime_qualified':False,'signed':False,'notarized':False},indent=2))
print('Build installed. Native functional probe and bundle/signing qualification remain required.')
