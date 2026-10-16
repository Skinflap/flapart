#!/usr/bin/env python3
"""Native Windows/macOS TLS build experiment. Evidence only in --output.
Original SDK is read-only; all candidate binaries remain in fresh --work.
"""
import argparse,hashlib,json,os,pathlib,platform,shutil,subprocess,sys,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--sdk',type=pathlib.Path,required=True);p.add_argument('--tools',type=pathlib.Path);p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
ROOT=pathlib.Path(__file__).resolve().parent;original=a.sdk.resolve();work=a.work.resolve();output=a.output.resolve();system=platform.system()
assert system in ('Windows','Darwin'),'Run on native Windows or Apple macOS'
assert 1<=a.jobs<=16 and original.is_dir() and not work.exists()
assert not output.is_relative_to(work),'Evidence directory must be outside binary workspace'
work.mkdir(parents=True);output.mkdir(parents=True,exist_ok=True)
receipt={'platform':platform.platform(),'architecture':platform.machine(),'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'passed':False,'stage':'initializing','commands':[],'qt_superproject':'2d0ea49d3428d639d45e7b1a32bbe0d096ed8b8e','qtbase':'d96d05760ac47f39c26b0f4292feb38cb0641725','original_sdk_unchanged':True,'runtime_artifact_upload':False}
env=os.environ.copy();candidate=work/'sdk';downloads=work/'downloads';downloads.mkdir();log_index=0

def run(stage,command,cwd=None,custom_env=None):
 global log_index
 receipt['stage']=stage;log_index+=1;command=[x.as_posix() if isinstance(x,pathlib.Path) else str(x) for x in command];receipt['commands'].append({'stage':stage,'command':command});print(stage,flush=True)
 with (output/(f'{log_index:02d}-'+stage+'.log')).open('w',encoding='utf-8') as log:subprocess.run(command,cwd=cwd,env=custom_env or env,stdout=log,stderr=subprocess.STDOUT,check=True)

def fetch(name,url,digest):
 receipt['stage']='fetch-'+name;path=downloads/name
 with urllib.request.urlopen(url,timeout=90) as response,path.open('wb') as target:shutil.copyfileobj(response,target)
 assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,('Hash mismatch',name)
 return path

def choose(candidates):
 for value in candidates:
  if not value:continue
  path=pathlib.Path(value) if pathlib.Path(value).is_file() else pathlib.Path(shutil.which(str(value)) or '')
  if path.is_file():return path.resolve()
 raise RuntimeError('Required native tool missing: '+', '.join(map(str,candidates)))

try:
 receipt['stage']='copy-sdk';shutil.copytree(original,candidate,symlinks=True)
 if system=='Windows':
  assert a.tools,'Windows requires --tools with pinned LLVM-MinGW20251118'
  llvm=a.tools.resolve()/'llvm-mingw-20251118-ucrt-x86_64/bin';assert (llvm/'x86_64-w64-mingw32-clang.exe').is_file()
  msys=work/'msys'
  run('prepare-msys',[sys.executable,ROOT/'prepare-msys.py','--destination',msys,'--cache',downloads/'msys'])
  perl=choose([msys/'usr/bin/perl.exe'])
  ssl_make=choose([msys/'usr/bin/make.exe'])
  receipt['perl_os']=subprocess.check_output([str(perl),'-e','print $^O'],text=True).strip()
  perl_paths=subprocess.check_output([str(perl),'-MFile::Spec','-e','print File::Spec->catfile("a","b")'],text=True).strip()
  assert perl_paths=='a/b',('OpenSSL MinGW requires Unix-path Perl',receipt['perl_os'],perl_paths)
  make=choose([llvm/'mingw32-make.exe','C:/Strawberry/c/bin/gmake.exe','C:/Strawberry/c/bin/mingw32-make.exe','mingw32-make.exe','gmake.exe'])
  env['PATH']=os.pathsep.join(map(str,[candidate/'bin',llvm,perl.parent,make.parent]))+os.pathsep+env.get('PATH','')
 else:
  perl=choose(['/usr/bin/perl','perl']);make=choose(['/usr/bin/make','make']);env['PATH']=str(candidate/'bin')+os.pathsep+env.get('PATH','')
 receipt['tools']={'perl':str(perl),'make':str(make)}
 if system=='Windows':receipt['tools']['openssl_make']=str(ssl_make)
 run('perl-version',[perl,'-v']);run('make-version',[make,'--version'])
 ssl=fetch('openssl-3.5.9.tar.gz','https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz','603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a')
 lock=json.loads((ROOT/'python.lock.json').read_text())
 for row in lock['artifacts']:fetch(row['name'],row['url'],row['sha256'])
 # Pin the exact gitlink, not a moving branch or guessed Qt release tag.
 qtbase=work/'qtbase';run('qtbase-init',['git','init',qtbase]);run('qtbase-remote',['git','remote','add','origin','https://invent.kde.org/szaman/qtbase.git'],qtbase);run('qtbase-fetch',['git','fetch','--depth','1','origin',receipt['qtbase']],qtbase);run('qtbase-checkout',['git','checkout','--detach','FETCH_HEAD'],qtbase)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=qtbase,text=True).strip()==receipt['qtbase']
 prefix=work/'openssl';command=[sys.executable,ROOT/'build-openssl.py','--archive',ssl,'--work',work/'openssl-build','--prefix',prefix,'--perl',perl,'--make',ssl_make if system=='Windows' else make,'--jobs',a.jobs]
 if system=='Windows':command+=['--toolchain',llvm]
 run('build-openssl',command)
 # syncqt prepares forwarding headers in our private source copy only.
 run('syncqt',[perl,candidate/'bin/syncqt.pl','-version','5.15.7','-outdir',qtbase,qtbase])
 if system=='Windows':libs=[prefix/'lib/libssl.dll.a',prefix/'lib/libcrypto.dll.a']
 else:libs=[prefix/'lib/libssl.3.dylib',prefix/'lib/libcrypto.3.dylib']
 qmake=candidate/'bin'/('qmake.exe' if system=='Windows' else 'qmake')
 run('build-qtnetwork',[sys.executable,ROOT/'build-network-module.py','--qmake',qmake,'--qtbase',qtbase,'--openssl-prefix',prefix,'--ssl-library',libs[0],'--crypto-library',libs[1],'--build',work/'network-build','--make',make,'--jobs',a.jobs,'--execute'])
 # Select only newly built module output, never the preexisting SDK module.
 search_roots=[work/'network-build',qtbase]
 if system=='Windows':
  found=[f for base in search_roots for f in base.rglob('Qt5Network.dll') if f.is_file()];assert len(found)==1,found
  shutil.copy2(found[0],candidate/'bin/Qt5Network.dll')
  for f in (prefix/'bin').glob('*.dll'):shutil.copy2(f,candidate/'bin'/f.name)
  env['FLAPART_DLL_DIRS']=os.pathsep.join(map(str,[candidate/'bin',prefix/'bin']))
  run('stage-python',[sys.executable,ROOT/'stage-windows-python.py','--downloads',downloads,'--old-python',original/'python','--destination',work/'python-new','--site-packages',candidate/'lib/site-packages'])
  old=candidate/'python';old.rename(work/'python-sdk-original');shutil.move(work/'python-new',old)
  # App DLL lookup must not pick an older duplicate Python runtime in bin.
  for name in ['python313.dll','python3.dll']:
   if (candidate/'bin'/name).exists():shutil.copy2(old/name,candidate/'bin'/name)
  python=old/'python.exe';openssl=prefix/'bin/openssl.exe';env['PATH']=str(old)+os.pathsep+env['PATH']
 else:
  found=[f for base in search_roots for f in base.rglob('QtNetwork') if f.is_file() and not f.is_symlink() and f.parent.name=='5' and f.parent.parent.name=='Versions' and f.parent.parent.parent.name=='QtNetwork.framework'];assert len(found)==1,found
  destination=(candidate/'lib/QtNetwork.framework/Versions/5/QtNetwork');assert destination.is_file();shutil.copy2(found[0],destination)
  for name in ['libssl.3.dylib','libcrypto.3.dylib']:shutil.copy2(prefix/'lib'/name,candidate/'lib'/name)
  run('build-bearer',[sys.executable,ROOT/'build-macos-bearer.py','--sdk',candidate,'--qtbase',qtbase,'--openssl-prefix',prefix,'--build',work/'bearer-build','--make',make,'--jobs',a.jobs])
  run('build-python',[sys.executable,ROOT/'build-macos-python.py','--archive',downloads/'Python-3.13.16.tar.xz','--openssl-prefix',prefix,'--old-framework',original/'lib/Python.framework','--site-packages',candidate/'lib/python3.13/site-packages','--work',work/'python-build','--prefix',work/'python-stage','--jobs',a.jobs])
  old=candidate/'lib/Python.framework';old.rename(work/'python-sdk-original');shutil.copytree(work/'python-stage/lib/Python.framework',old,symlinks=True)
  # KDE macOS PyQt lives inside the framework, reached by lib/python3.13 alias.
  oldsite=work/'python-sdk-original/Versions/3.13/lib/python3.13/site-packages'
  newsite=old/'Versions/3.13/lib/python3.13/site-packages'
  shutil.copytree(oldsite,newsite,symlinks=True,dirs_exist_ok=True)
  python=old/'Versions/3.13/bin/python3.13';openssl=prefix/'bin/openssl'
  env['DYLD_FRAMEWORK_PATH']=str(candidate/'lib');env['DYLD_LIBRARY_PATH']=os.pathsep.join(map(str,[candidate/'lib',prefix/'lib']));env['PYTHONPATH']=str(candidate/'lib/python3.13/site-packages')
 env['OPENSSL_MODULES']=str(prefix/'lib/ossl-modules');env['QT_QPA_PLATFORM']='offscreen'
 probe_args=[str(ROOT/'https-validation-probe.py'),'--openssl',str(openssl),'--output',str(output/'tls-validation.json')]
 if system=='Windows':
  # Python3.8+ DLL loading requires explicit search directories, not just PATH.
  bootstrap='import os,sys,runpy;handles=[os.add_dll_directory(p) for p in os.environ["FLAPART_DLL_DIRS"].split(os.pathsep)];sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name="__main__")'
  run('tls-validation',[python,'-c',bootstrap,*probe_args],custom_env=env)
 else:run('tls-validation',[python,*probe_args],custom_env=env)
 tls=json.loads((output/'tls-validation.json').read_text());assert tls['passed'];receipt['passed']=True;receipt['stage']='native-tls-probe-passed';receipt['relocated_distribution_qualified']=False
except Exception as error:
 receipt['error']=repr(error);raise
finally:
 for module in ('network','bearer'):
  inner=work/(module+'-build')/'build.log'
  if inner.is_file():shutil.copy2(inner,output/(module+'-build-inner.log'))
 if (work/'bearer-build/receipt.json').is_file():shutil.copy2(work/'bearer-build/receipt.json',output/'bearer-build.json')
 for name,source in [('openssl-build.json',work/'openssl-build/openssl-build-receipt.json'),('network-build.json',work/'network-build/receipt.json'),('python-build.json',work/'python-build/python-build-receipt.json'),('python-stage.json',candidate/'python/flapart-python-receipt.json')]:
  if source.is_file():shutil.copy2(source,output/name)
 (output/'native-ci-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
