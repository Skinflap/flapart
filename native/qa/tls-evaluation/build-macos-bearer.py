#!/usr/bin/env python3
"""Rebuild the Qt generic bearer plugin against the refreshed private SDK.
Native experiment only: no original SDK mutation or distribution qualification.
"""
import argparse, json, pathlib, platform, shutil, subprocess
p=argparse.ArgumentParser()
for name in ('sdk','qtbase','openssl-prefix','build'):
 p.add_argument('--'+name,type=pathlib.Path,required=True)
p.add_argument('--make',required=True);p.add_argument('--jobs',type=int,default=3)
a=p.parse_args()
assert platform.system()=='Darwin' and 1<=a.jobs<=16
sdk=a.sdk.resolve();qtbase=a.qtbase.resolve();ssl=a.openssl_prefix.resolve();build=a.build.resolve()
assert not build.exists();build.mkdir(parents=True)
# qmake shadowed() discovers the module root only with the source-relative layout.
module_build=build/'src/plugins/bearer/generic';module_build.mkdir(parents=True)
source=qtbase/'src/plugins/bearer/generic/generic.pro';assert source.is_file()
qmake=sdk/'bin/qmake';assert subprocess.check_output([str(qmake),'-query','QT_VERSION'],text=True).strip()=='5.15.7'
command=[str(qmake),str(source),'-o','Makefile','-after','QMAKE_APPLE_DEVICE_ARCHS=x86_64 arm64','QMAKE_MACOSX_DEPLOYMENT_TARGET=11.0','QMAKE_INCDIR_OPENSSL='+str(ssl/'include'),'QMAKE_LIBS_OPENSSL='+str(ssl/'lib/libssl.3.dylib')+' '+str(ssl/'lib/libcrypto.3.dylib')]
receipt={'passed':False,'command':command,'source':str(source),'outputs':[]}
try:
 with (build/'build.log').open('w') as log:
  subprocess.run(command,cwd=module_build,stdout=log,stderr=log,check=True)
  subprocess.run([a.make,'-j'+str(a.jobs)],cwd=module_build,stdout=log,stderr=log,check=True)
 for name in ('libqgenericbearer.dylib','libqgenericbearer_debug.dylib'):
  found=[f for root in (build,qtbase) for f in root.rglob(name) if f.is_file() and not f.is_symlink()]
  assert len(found)==1,(name,found)
  binary=found[0];deps=subprocess.check_output(['otool','-L',str(binary)],text=True)
  assert 'libssl.1.1' not in deps and 'libcrypto.1.1' not in deps,deps
  arch=subprocess.check_output(['lipo','-archs',str(binary)],text=True).strip()
  assert {'arm64','x86_64'}<=set(arch.split()),arch
  target=sdk/'plugins/bearer'/name;assert target.is_file(),target
  shutil.copy2(binary,target)
  receipt['outputs'].append({'name':name,'architectures':arch,'dependencies':deps})
 receipt['passed']=True
finally:(build/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
