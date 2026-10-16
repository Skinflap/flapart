#!/usr/bin/env python3
"""Build pinned OpenSSL in fresh native CI directories; never install to host/SDK."""
import argparse,hashlib,json,os,pathlib,platform,shutil,subprocess,tarfile
p=argparse.ArgumentParser();p.add_argument('--archive',type=pathlib.Path,required=True);p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--toolchain',type=pathlib.Path);p.add_argument('--perl',default='perl');p.add_argument('--make',default='make');p.add_argument('--jobs',type=int,default=3);p.add_argument('--deployment-target',default='11.0');a=p.parse_args()
assert platform.system() in ('Windows','Darwin'),'Native Windows/macOS runner required'
assert 1<=a.jobs<=16
archive=a.archive.resolve();work=a.work.resolve();prefix=a.prefix.resolve()
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a'
assert not work.exists() and not prefix.exists(),'Fresh output paths required'
work.mkdir(parents=True);prefix.parent.mkdir(parents=True,exist_ok=True)
receipt={'openssl':'3.5.9','compiled':False,'qualified':False,'commands':[],'host':platform.platform()}
def run(cmd,cwd,env=None):
 receipt['commands'].append([str(x) for x in cmd]);subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,check=True)
def build(arch,target,dest,env):
 source=work/arch;source.mkdir()
 with tarfile.open(archive) as tar:tar.extractall(source,filter='data')
 source=source/'openssl-3.5.9'
 run([a.perl,'Configure',target,'shared','--prefix='+dest.as_posix(),'--openssldir='+prefix.as_posix()+'/ssl','--libdir=lib'],source,env)
 run([a.make,'-j'+str(a.jobs)],source,env);run([a.make,'install_sw'],source,env)
try:
 if platform.system()=='Windows':
  assert a.toolchain,'--toolchain must point to LLVM-MinGW20251118 bin'
  toolchain=a.toolchain.resolve();assert (toolchain/'x86_64-w64-mingw32-clang.exe').exists()
  env=dict(os.environ,PATH=str(toolchain)+os.pathsep+str(pathlib.Path(a.perl).parent)+os.pathsep+os.environ['PATH'],SHELL=str(pathlib.Path(a.perl).parent/'sh.exe'),CC='x86_64-w64-mingw32-clang',AR='llvm-ar',RANLIB='llvm-ranlib',RC='x86_64-w64-mingw32-windres')
  version=subprocess.check_output([str(toolchain/'x86_64-w64-mingw32-clang.exe'),'--version'],text=True);assert '21.1.6' in version,version
  receipt['compiler']=version;build('windows','mingw64',prefix,env)
 else:
  sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip();receipt['macos_sdk']=sdk
  for arch,target in [('arm64','darwin64-arm64-cc'),('x86_64','darwin64-x86_64-cc')]:
   env=dict(os.environ,CC='clang',MACOSX_DEPLOYMENT_TARGET=a.deployment_target,CFLAGS=f'-arch {arch} -isysroot {sdk} -mmacosx-version-min={a.deployment_target}',LDFLAGS=f'-arch {arch} -isysroot {sdk} -mmacosx-version-min={a.deployment_target} -Wl,-headerpad_max_install_names')
   build(arch,target,work/(arch+'-prefix'),env)
  left=work/'arm64-prefix';right=work/'x86_64-prefix';shutil.copytree(left,prefix,symlinks=True)
  for f in left.rglob('*'):
   if not f.is_file() or f.is_symlink():continue
   rel=f.relative_to(left);other=right/rel;assert other.is_file(),rel
   kind=subprocess.check_output(['file','-b',str(f)],text=True)
   if 'Mach-O' in kind or 'current ar archive' in kind:
    run(['lipo','-create',f,other,'-output',prefix/rel],work)
    info=subprocess.check_output(['lipo','-archs',str(prefix/rel)],text=True);assert 'arm64' in info and 'x86_64' in info
   elif f.read_bytes()!=other.read_bytes() and rel.parts[0]=='include':
    # OpenSSL generated configuration headers can differ by architecture.
    target=prefix/rel;arm=target.with_name(target.stem+'.arm64'+target.suffix);x86=target.with_name(target.stem+'.x86_64'+target.suffix);shutil.copy2(f,arm);shutil.copy2(other,x86)
    target.write_text('#if defined(__arm64__) || defined(__aarch64__)\n#include "'+arm.name+'"\n#elif defined(__x86_64__)\n#include "'+x86.name+'"\n#else\n#error Unsupported architecture\n#endif\n')
  for metadata in list((prefix/'lib/pkgconfig').glob('*.pc')) + list((prefix/'lib/cmake').rglob('*.cmake')):
   text=metadata.read_text();metadata.write_text(text.replace(str(left),str(prefix)).replace(str(right),str(prefix)))
  for f in prefix.rglob('*'):
   if not f.is_file() or f.is_symlink():continue
   kind=subprocess.check_output(['file','-b',str(f)],text=True)
   if 'Mach-O' not in kind:continue
   loads=subprocess.check_output(['otool','-L',str(f)],text=True)
   for line in loads.splitlines():
    old=line.strip().split(' (')[0]
    if str(left) in old or str(right) in old:run(['install_name_tool','-change',old,'@rpath/'+pathlib.Path(old).name,f],work)
   if f.suffix=='.dylib':run(['install_name_tool','-id','@rpath/'+f.name,f],work)
   if f==prefix/'bin/openssl':run(['install_name_tool','-add_rpath','@executable_path/../lib',f],work)
   run(['codesign','--force','--sign','-',f],work)
 cli=prefix/'bin'/('openssl.exe' if platform.system()=='Windows' else 'openssl')
 env=dict(os.environ,OPENSSL_MODULES=str(prefix/'lib/ossl-modules'),PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH'])
 receipt['version']=subprocess.check_output([str(cli),'version','-a'],env=env,text=True);assert 'OpenSSL 3.5.9' in receipt['version']
 receipt['compiled']=True
finally:(work/'openssl-build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
