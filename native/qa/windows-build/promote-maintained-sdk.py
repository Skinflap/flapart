#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Promote a TLS-qualified private Windows experiment into a fresh build SDK.
Does not modify its inputs, compile Krita, or qualify a distributed package.
"""
import argparse,pathlib,platform,json,hashlib,shutil,importlib.util
from python_runtime_paths import relocated_lines
p=argparse.ArgumentParser();p.add_argument('--tls-work',type=pathlib.Path,required=True);p.add_argument('--tls-evidence',type=pathlib.Path,required=True);p.add_argument('--destination',type=pathlib.Path,required=True);a=p.parse_args()
assert platform.system()=='Windows','Run on the same native Windows environment as the TLS experiment'
work=a.tls_work.resolve();evidence=a.tls_evidence.resolve();dest=a.destination.resolve();original=work/'sdk';openssl=work/'openssl'
assert not dest.exists() and not dest.is_relative_to(work),'Fresh SDK destination outside TLS inputs required'
ci=json.loads((evidence/'native-ci-receipt.json').read_text());tls=json.loads((evidence/'tls-validation.json').read_text())
assert ci['passed'] is True and tls['passed'] is True and ci['qtbase']=='d96d05760ac47f39c26b0f4292feb38cb0641725'
ssl_receipt=json.loads((work/'openssl-build/openssl-build-receipt.json').read_text());assert ssl_receipt['compiled'] and 'OpenSSL 3.5.9' in ssl_receipt['version']
py_receipt=json.loads((original/'python/flapart-python-receipt.json').read_text());assert py_receipt['version']=='3.13.16' and py_receipt['runtime_executed']
metadata_file=pathlib.Path(__file__).resolve().parents[2]/'distribution/source-qualification/native_metadata.py'
spec=importlib.util.spec_from_file_location('flapart_native_metadata',metadata_file);metadata=importlib.util.module_from_spec(spec);spec.loader.exec_module(metadata)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
shutil.copytree(original,dest);changes=[]
def replace(source,target):
    before=sha(target) if target.is_file() else None;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    changes.append({'path':target.relative_to(dest).as_posix(),'old_sha256':before,'source_sha256':sha(source),'sha256':sha(target)})
# Replace complete headers, not just the DLLs, so the final source build sees
# the maintained API and matching import archives/pkg-config metadata.
old_headers=dest/'include/openssl'
if old_headers.exists():shutil.rmtree(old_headers)
for section in ('include','lib','bin'):
    for source in sorted((openssl/section).rglob('*')):
        assert not source.is_symlink(),'Unexpected Windows OpenSSL link'
        if source.is_file():replace(source,dest/section/source.relative_to(openssl/section))
for path in list((dest/'lib/pkgconfig').glob('*.pc'))+list((dest/'lib/cmake').rglob('*.cmake')):
    text=path.read_text(encoding='utf-8');updated=text.replace(openssl.as_posix(),dest.as_posix()).replace(str(openssl),str(dest))
    if updated!=text:path.write_text(updated,encoding='utf-8')
# The experiment copied the rebuilt DLL; retain its matching linker archive.
archives=[f for base in (work/'network-build',work/'qtbase') for f in base.rglob('libQt5Network.a') if f.is_file()]
assert archives and len({sha(f) for f in archives})==1,('Different rebuilt QtNetwork import archives',archives)
replace(archives[0],dest/'lib/libQt5Network.a')
pth=dest/'python/python313._pth';paths=relocated_lines(pth.read_text(encoding='utf-8'),original)
for line in paths:
    if line!='import site':assert (dest/'python'/line).resolve().is_relative_to(dest) and (dest/'python'/line).exists(),line
pth.write_text('\n'.join(paths)+'\n',encoding='utf-8')
old_names={'libssl-1_1-x64.dll','libcrypto-1_1-x64.dll','libssl-1_1.dll','libcrypto-1_1.dll','ssleay32.dll','libeay32.dll'}
retired=[];checked=0
for path in sorted(dest.rglob('*')):
    if not path.is_file() or path.suffix.lower() not in ('.dll','.pyd'):continue
    relative=path.relative_to(dest).as_posix()
    if relative.startswith('lib/site-packages/pyqtbuild/'):
        continue # Build-only bundler remains needed by SIP; final package omits it.
    if path.name.casefold() in old_names:retired.append(path);continue
    info=metadata.parse(path.read_bytes());assert info and info['architectures']==['x86_64'],relative
    assert not any(x.casefold() in old_names for x in info['native_dependencies']),('Old TLS consumer remains',relative)
    checked+=1
retired_rows=[{'path':f.relative_to(dest).as_posix(),'sha256':sha(f)} for f in retired]
for path in retired:path.unlink()
network=metadata.parse((dest/'bin/Qt5Network.dll').read_bytes())
assert {'libssl-3-x64.dll','libcrypto-3-x64.dll'}.issubset({x.casefold() for x in network['native_dependencies']})
for row in changes:row['sha256']=sha(dest/row['path'])
maintained_outputs=[]
for path in [dest/'bin/Qt5Network.dll',*list((dest/'bin').glob('lib*-3-x64.dll')),*list((dest/'python').glob('*'))]:
    if path.is_file() and path.suffix.lower() in ('.dll','.pyd','.exe','.zip'):
        maintained_outputs.append({'path':path.relative_to(dest).as_posix(),'sha256':sha(path),'component':'cpython-official-runtime' if path.parent==dest/'python' else ('qt-network' if path.name=='Qt5Network.dll' else 'openssl-native-build')})
receipt={'schema_version':1,'platform':platform.platform(),'source_tls_receipt_sha256':sha(evidence/'tls-validation.json'),'source_ci_receipt_sha256':sha(evidence/'native-ci-receipt.json'),'openssl':'3.5.9','python':'3.13.16','replaced_files':changes,'maintained_outputs':maintained_outputs,'python_source_sha256':py_receipt['source_sha256'],'python_runtime_archive_sha256':py_receipt['runtime_sha256'],'retired_old_ssl':retired_rows,'native_imports_checked':checked,'python_path_entries':paths,'inputs_unchanged':True,'fresh_krita_source_build_required':True,'packaged_runtime_qualified':False,'publishable':False}
(dest/'flapart-maintained-sdk.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
