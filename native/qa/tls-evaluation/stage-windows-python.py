#!/usr/bin/env python3
"""Stage complete official CPython3.13.16; retain custom path/site setup.
Never merges old DLLs into new runtime. Source archive is verified alongside it.
"""
import argparse,pathlib,zipfile,hashlib,json,shutil,platform,subprocess,os
p=argparse.ArgumentParser();p.add_argument('--downloads',type=pathlib.Path,required=True);p.add_argument('--old-python',type=pathlib.Path,required=True);p.add_argument('--destination',type=pathlib.Path,required=True);p.add_argument('--site-packages',required=True,help='Path inserted into _pth, relative to new Python root or absolute CI SDK path');a=p.parse_args()
lock=json.loads(pathlib.Path(__file__).with_name('python.lock.json').read_text());downloads=a.downloads.resolve();old=a.old_python.resolve();dest=a.destination.resolve();assert not dest.exists(),'Fresh destination required'
for item in lock['artifacts']:assert hashlib.sha256((downloads/item['name']).read_bytes()).hexdigest()==item['sha256'],item['name']
archive=downloads/'python-3.13.16-embed-amd64.zip';dest.mkdir(parents=True)
with zipfile.ZipFile(archive) as z:
 for n in z.namelist():assert not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts,n
 z.extractall(dest)
assert b'OpenSSL 3.5.9' in (dest/'libcrypto-3.dll').read_bytes(),'Official runtime TLS differs from required baseline'
preserved=[]
for rel in ['sitecustomize.py','usercustomize.py','Lib/sitecustomize.py','Lib/site-packages/sitecustomize.py','Lib/site-packages/usercustomize.py']:
 src=old/rel
 if src.is_file():
  target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target);preserved.append(rel)
paths=['python313.zip','.']
oldpth=old/'python313._pth'
if oldpth.exists():
 for line in oldpth.read_text().splitlines():
  line=line.strip()
  if line and not line.startswith('#') and line!='import site' and line not in paths:paths.append(line)
assert '\n' not in a.site_packages and '\r' not in a.site_packages
if a.site_packages not in paths:paths.append(a.site_packages)
paths.append('import site');(dest/'python313._pth').write_text('\n'.join(paths)+'\n')
receipt={'version':'3.13.16','source_sha256':next(x['sha256'] for x in lock['artifacts'] if x['name'].startswith('Python-')),'runtime_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'whole_official_runtime':True,'custom_site_files':preserved,'python_path_entries':paths,'runtime_executed':False}
if platform.system()=='Windows':
 code='import os,sys,ssl,hashlib,json;handles=[os.add_dll_directory(p) for p in os.environ.get("FLAPART_DLL_DIRS","").split(os.pathsep) if p];from PyQt5.QtCore import QT_VERSION_STR;print(json.dumps(dict(python=sys.version,ssl=ssl.OPENSSL_VERSION,qt=QT_VERSION_STR,sha256=hashlib.sha256(b"flapart").hexdigest())))'
 receipt['probe']=json.loads(subprocess.check_output([str(dest/'python.exe'),'-c',code],text=True));assert 'OpenSSL 3.5.9' in receipt['probe']['ssl'];receipt['runtime_executed']=True
(dest/'flapart-python-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
