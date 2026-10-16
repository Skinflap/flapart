#!/usr/bin/env python3
"""Prepare exact maintained image-library source without modifying existing trees."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(component, archive, work):
    pins = json.loads((ROOT/'pins.json').read_text())[component]
    archive, work = archive.absolute(), work.absolute()
    if work.exists() or work.is_symlink():
        raise ValueError('Use a fresh private destination')
    if any(p.is_symlink() for p in (archive, *archive.parents, *work.parents)):
        raise ValueError('Symlink input or destination parent refused')
    if sha(archive) != pins['archive_sha256']:
        raise ValueError('Source archive hash mismatch')
    for patch in pins['patches']:
        if sha(ROOT/patch['path']) != patch['sha256']:
            raise ValueError('Patch hash mismatch')
    work.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(work, filter='data')
    source = work/pins['source_root']
    for patch in pins['patches']:
        for args in (['--check'], []):
            subprocess.run(['git','apply',*args,str(ROOT/patch['path'])],cwd=source,check=True)
    rows = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            rows.append({'path':path.relative_to(source).as_posix(),'link':str(path.readlink())})
        elif path.is_file():
            rows.append({'path':path.relative_to(source).as_posix(),'sha256':sha(path)})
    manifest=work/'source-manifest.json'
    manifest.write_text(json.dumps(rows,indent=2)+'\n')
    if sha(manifest)!=pins['manifest_sha256'] or len(rows)!=pins['entries']:
        raise ValueError('Prepared source differs from exact native-build inputs')
    result={'component':component,'version':pins['version'],'source':str(source),
            'source_manifest_sha256':sha(manifest),'entries':len(rows),
            'prepared':True,'native_compiled':False,'security_qualified':False}
    (work/'preparation.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component',choices=['libraw','libheif','libde265'])
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.component,args.archive,args.work),indent=2))
