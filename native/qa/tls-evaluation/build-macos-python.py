#!/usr/bin/env python3
"""Build complete maintained CPython3.13 framework with OpenSSL3.5.9.
Chosen over a 3.13.5 _ssl-only rebuild because current CPython security fixes
also affect SSLContext, hostname validation and the standard library.
"""
import argparse,pathlib,platform,hashlib,json,tarfile,os,subprocess,shutil
def sdk_smoke_environment(base, new_prefix, site_packages, openssl_prefix):
 """Loader paths for the isolated SDK import smoke, never packaged-runtime QA."""
 site_packages=pathlib.Path(site_packages).resolve(strict=True)
 frameworks=[parent for parent in site_packages.parents if parent.name=='Python.framework']
 if len(frameworks)!=1:raise ValueError('Expected framework-contained KDE site-packages')
 sdk_lib=frameworks[0].parent
 if not (sdk_lib/'QtCore.framework/Versions/5/QtCore').is_file():raise ValueError('Candidate SDK QtCore framework missing')
 new_lib=pathlib.Path(new_prefix).resolve(strict=True)/'lib'
 if not (new_lib/'Python.framework/Versions/3.13/Python').is_file():raise ValueError('New Python framework missing')
 ssl_lib=pathlib.Path(openssl_prefix).resolve(strict=True)/'lib'
 if not (ssl_lib/'libssl.3.dylib').is_file():raise ValueError('Candidate OpenSSL missing')
 # Replace inherited loader overrides; old SDK Python must not outrank new Python.
 result={key:value for key,value in base.items() if not key.startswith('DYLD_') and key not in ('PYTHONHOME','PYTHONPATH')}
 result.update(PYTHONPATH=str(site_packages),PYTHONNOUSERSITE='1',
  OPENSSL_MODULES=str(ssl_lib/'ossl-modules'),
  DYLD_FRAMEWORK_PATH=os.pathsep.join(map(str,[new_lib,sdk_lib])),
  DYLD_LIBRARY_PATH=os.pathsep.join(map(str,[ssl_lib,new_lib,sdk_lib])))
 return result

p=argparse.ArgumentParser();p.add_argument('--archive',type=pathlib.Path,required=True);p.add_argument('--openssl-prefix',type=pathlib.Path,required=True);p.add_argument('--old-framework',type=pathlib.Path,required=True);p.add_argument('--site-packages',type=pathlib.Path,required=True);p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--jobs',type=int,default=3);p.add_argument('--deployment-target',default='11.0');a=p.parse_args()
assert platform.system()=='Darwin','Native Apple runner required'
assert 1<=a.jobs<=16
for n in ['archive','openssl_prefix','old_framework','site_packages','work','prefix']:setattr(a,n,getattr(a,n).resolve())
assert hashlib.sha256(a.archive.read_bytes()).hexdigest()=='f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d'
assert not a.work.exists() and not a.prefix.exists(),'Fresh isolated paths required'
assert (a.openssl_prefix/'lib/libssl.3.dylib').exists()
a.work.mkdir(parents=True);a.prefix.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(a.archive) as t:t.extractall(a.work,filter='data')
source=a.work/'Python-3.13.16';build=a.work/'build';build.mkdir();sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()
env=dict(os.environ,SDKROOT=sdk,MACOSX_DEPLOYMENT_TARGET=a.deployment_target,LDFLAGS='-Wl,-headerpad_max_install_names',PKG_CONFIG_PATH=str(a.openssl_prefix/'lib/pkgconfig'),PKG_CONFIG_LIBDIR=os.pathsep.join([str(a.openssl_prefix/'lib/pkgconfig'),str(pathlib.Path(sdk)/'usr/lib/pkgconfig')]),CC=subprocess.check_output(['xcrun','--find','clang'],text=True).strip())
receipt={'compiled':False,'version':'3.13.16','ssl_target':'3.5.9','sdk':sdk,'commands':[],'full_framework_reason':'Includes maintained CPython SSLContext/hostname/stdlib security fixes; retains cp313 ABI','runtime_qualified':False}
def run(cmd):receipt['commands'].append(list(map(str,cmd)));subprocess.run(list(map(str,cmd)),cwd=build,env=env,check=True)
try:
 # Match the pinned KDE recipe's relocatable links and script shebangs.
 patches=[('Mac/Makefile.in','BINDIR=\t\t@bindir@',"BINDIR=$(shell perl -le 'use File::Spec; print File::Spec->abs2rel(@ARGV)' @bindir@ $(FRAMEWORKUNIXTOOLSPREFIX)/bin)"),('Misc/python-config.in','#!@EXENAME@','#!/usr/bin/env python3')]
 receipt['source_patches']=[]
 for rel,before,after in patches:
  path=source/rel;original=path.read_bytes();text=original.decode();assert text.count(before)==1,(rel,'source context changed')
  path.write_text(text.replace(before,after));receipt['source_patches'].append({'path':rel,'before_sha256':hashlib.sha256(original).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'recipe_commit':'0fd95c4efca2e5b5024121bb0ccae5b353956cd9'})
 run([source/'configure','--prefix='+str(a.prefix),'--enable-framework='+str(a.prefix/'lib'),'--enable-universalsdk='+sdk,'--with-universal-archs=universal2','--with-openssl='+str(a.openssl_prefix),'--with-openssl-rpath='+str(a.openssl_prefix/'lib'),'--without-ensurepip','--without-static-libpython','--with-readline=editline'])
 run(['make','-j'+str(a.jobs)])
 # CPython substitutes FRAMEWORKINSTALLLAST at configure time; overriding it
 # on the make command line does not suppress /Applications tools. Stage ALL
 # install targets, then promote only the configured private prefix.
 destdir=a.work/'install-root';destdir.mkdir()
 run(['make','install','DESTDIR='+str(destdir)])
 staged_prefix=destdir/a.prefix.relative_to(a.prefix.anchor)
 assert staged_prefix.is_dir() and staged_prefix.resolve().is_relative_to(destdir.resolve()) and not a.prefix.exists()
 receipt['install_staging']={'destdir':str(destdir),'promoted_prefix':str(staged_prefix),'optional_applications_promoted':False}
 # No staged symlink may point outside the configured candidate prefix.
 links=[]
 for path in staged_prefix.rglob('*'):
  if path.is_symlink():
   target=os.readlink(path);assert not os.path.isabs(target),(path,target)
   resolved=(path.parent/target).resolve();assert resolved.is_relative_to(staged_prefix.resolve()),(path,target)
   links.append({'path':str(path.relative_to(staged_prefix)),'target':target})
 receipt['install_staging']['relative_symlinks']=links
 shutil.copytree(staged_prefix,a.prefix,symlinks=True)
 framework=a.prefix/'lib/Python.framework';version=framework/'Versions/3.13';site=version/'lib/python3.13/site-packages';site.mkdir(exist_ok=True)
 preserved=[]
 for rel in ['Versions/3.13/lib/python3.13/sitecustomize.py','Versions/3.13/lib/python3.13/site-packages/sitecustomize.py','Versions/3.13/lib/python3.13/site-packages/usercustomize.py']:
  src=a.old_framework/rel
  if src.is_file():dest=framework/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);preserved.append(rel)
 receipt['preserved_custom_site_files']=preserved
 # Snapshot the runner's OS root certificates into the isolated OpenSSL CA path.
 # This does not alter any system trust store or relax peer/hostname validation.
 roots=subprocess.check_output(['security','find-certificate','-a','-p','/System/Library/Keychains/SystemRootCertificates.keychain']);assert b'BEGIN CERTIFICATE' in roots
 capath=a.openssl_prefix/'ssl';capath.mkdir(exist_ok=True);(capath/'cert.pem').write_bytes(roots);receipt['ca_snapshot_sha256']=hashlib.sha256(roots).hexdigest()
 # The full replacement must retain the original interpreter's extension breadth.
 def extension_names(folder):
  return {f.name.split('.')[0] for f in folder.glob('*.so') if f.is_file()}
 baseline=extension_names(a.old_framework/'Versions/3.13/lib/python3.13/lib-dynload')
 actual=extension_names(version/'lib/python3.13/lib-dynload')
 receipt['extension_modules']={'baseline':sorted(baseline),'candidate':sorted(actual),'missing':sorted(baseline-actual)}
 assert baseline and not baseline-actual,('CPython extension regression',sorted(baseline-actual))
 sslmods=list((version/'lib/python3.13/lib-dynload').glob('_ssl*.so'))+list((version/'lib/python3.13/lib-dynload').glob('_hashlib*.so'));assert len(sslmods)==2
 for f in sslmods+[version/'Python']:
  arches=subprocess.check_output(['lipo','-archs',str(f)],text=True);assert 'arm64' in arches and 'x86_64' in arches,(f,arches)
 for f in sslmods:
  loads=subprocess.check_output(['otool','-L',str(f)],text=True);assert '1.1.dylib' not in loads and '.3.dylib' in loads,loads
 runtime_env=sdk_smoke_environment(env,a.prefix,a.site_packages,a.openssl_prefix)
 receipt['smoke_loader']={'scope':'SDK build-time import smoke only; not relocated runtime qualification','framework_paths':runtime_env['DYLD_FRAMEWORK_PATH'].split(os.pathsep),'library_paths':runtime_env['DYLD_LIBRARY_PATH'].split(os.pathsep),'site_packages':str(a.site_packages)}
 code="""import ssl,hashlib,sys,json,ctypes,os
import PyQt5.QtCore as QtCore
lib=ctypes.CDLL(None)
lib._dyld_image_count.restype=ctypes.c_uint32
lib._dyld_get_image_name.argtypes=[ctypes.c_uint32]
lib._dyld_get_image_name.restype=ctypes.c_char_p
images=[os.path.realpath(os.fsdecode(lib._dyld_get_image_name(i))) for i in range(lib._dyld_image_count())]
python_frameworks=sorted(set(p for p in images if p.endswith('/Python.framework/Versions/3.13/Python')))
print(json.dumps(dict(python=sys.version,python_version=list(sys.version_info[:3]),prefix=sys.prefix,python_frameworks=python_frameworks,pyqt_qtcore=os.path.realpath(QtCore.__file__),ssl=ssl.OPENSSL_VERSION,qt=QtCore.QT_VERSION_STR,paths=ssl.get_default_verify_paths()._asdict())))
"""
 receipt['probe']=json.loads(subprocess.check_output([str(version/'bin/python3.13'),'-c',code],env=runtime_env,text=True));assert 'OpenSSL 3.5.9' in receipt['probe']['ssl'];assert receipt['probe']['python_version']==[3,13,16];assert pathlib.Path(receipt['probe']['prefix']).resolve()==version.resolve();assert receipt['probe']['python_frameworks']==[str((version/'Python').resolve())];assert pathlib.Path(receipt['probe']['pyqt_qtcore']).is_relative_to(a.site_packages);receipt['compiled']=True
finally:(a.work/'python-build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
