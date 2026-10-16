#!/usr/bin/env python3
"""Experimental native-platform Qt5Network-only rebuild in a fresh directory.
Never installs or changes the input SDK. Requires exact patched Qt source and
matching native SDK/compiler environment. A successful compile is not TLS QA.
"""
import argparse,pathlib,subprocess,json,os,platform,shutil,hashlib
p=argparse.ArgumentParser();p.add_argument('--qmake',type=pathlib.Path,required=True);p.add_argument('--qtbase',type=pathlib.Path,required=True);p.add_argument('--openssl-prefix',type=pathlib.Path,required=True);p.add_argument('--ssl-library',type=pathlib.Path,required=True);p.add_argument('--crypto-library',type=pathlib.Path,required=True);p.add_argument('--build',type=pathlib.Path,required=True);p.add_argument('--make',required=True);p.add_argument('--jobs',type=int,default=3);p.add_argument('--execute',action='store_true');a=p.parse_args()
for n in ('qmake','qtbase','openssl_prefix','ssl_library','crypto_library','build'):setattr(a,n,getattr(a,n).resolve())
assert a.jobs in range(1,17)
for p in (a.qmake,a.qtbase/'src/network/network.pro',a.openssl_prefix/'include/openssl/opensslv.h',a.ssl_library,a.crypto_library):assert p.exists(),p
v=subprocess.check_output([str(a.qmake),'-query','QT_VERSION'],text=True).strip();assert v=='5.15.7',('SDK ABI mismatch',v)
assert '5.15.7' in (a.qtbase/'.qmake.conf').read_text()
assert not a.build.exists(), 'Use a fresh shadow build directory'
a.build.mkdir(parents=True)
module_build=a.build/'src/network';module_build.mkdir(parents=True)
# A standalone source module lacks configure-generated feature metadata. Preserve
# the SDK's exact public/private feature choices; only replace its SSL link input.
sdk=a.qmake.parent.parent
metadata=[];config_sources={}
for name in ['qt_lib_network.pri','qt_lib_network_private.pri']:
 source=sdk/'mkspecs/modules'/name
 assert source.is_file(),source
 config_sources[name]=hashlib.sha256(source.read_bytes()).hexdigest()
 for line in source.read_text().splitlines():
  if '.enabled_features =' in line or '.disabled_features =' in line or (line.startswith('QMAKE_LIBS_') and not line.startswith('QMAKE_LIBS_OPENSSL')):metadata.append(line)
metadata.extend(['QMAKE_INCDIR_OPENSSL = '+(a.openssl_prefix/'include').as_posix(),'QMAKE_LIBS_OPENSSL = '+a.ssl_library.as_posix()+' '+a.crypto_library.as_posix()])
(module_build/'qtnetwork-config.pri').write_text('\n'.join(metadata)+'\n')
if platform.system()=='Darwin':headers=sdk/'lib/QtNetwork.framework/Versions/5/Headers'
else:headers=sdk/'include/QtNetwork'
for name,source in [('qtnetwork-config.h',headers/'qtnetwork-config.h'),('qtnetwork-config_p.h',headers/'5.15.7/QtNetwork/private/qtnetwork-config_p.h')]:
 assert source.is_file(),source
 shutil.copy2(source,module_build/name);config_sources[name]=hashlib.sha256(source.read_bytes()).hexdigest()

# Absolute libraries prevent old SDK -L search order from choosing OpenSSL1.1.
command=[str(a.qmake),(a.qtbase/'src/network/network.pro').as_posix(),'-o','Makefile','-after','QMAKE_INCDIR_OPENSSL='+(a.openssl_prefix/'include').as_posix(),'QMAKE_LIBS_OPENSSL='+a.ssl_library.as_posix()+' '+a.crypto_library.as_posix()]
if platform.system()=='Windows':command.append('QMAKE_LIBDIR+='+ (sdk/'lib').as_posix())
if platform.system()=='Darwin':command.extend(['QMAKE_APPLE_DEVICE_ARCHS=x86_64 arm64','QMAKE_MACOSX_DEPLOYMENT_TARGET=11.0'])
receipt={'status':'planned','sdk_feature_configuration_sha256':config_sources,'qt_version':v,'qmake':command,'make':[a.make,'-j'+str(a.jobs)],'input_sdk_unmodified':True,'installation_performed':False,'native_runtime_validation_required':True}
try:
 if a.execute:
  with (a.build/'build.log').open('w') as log:
   subprocess.run(command,cwd=module_build,stdout=log,stderr=log,check=True)
   subprocess.run(receipt['make'],cwd=module_build,stdout=log,stderr=log,check=True)
  receipt['status']='compiled-unqualified'
finally:(a.build/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
