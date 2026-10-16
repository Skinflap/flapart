#!/usr/bin/env python3
"""Apply exact reviewed Qt fixes only to an explicitly supplied private source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
RECEIPT_SHA='1ae18120e4d0455624167153ec7eec3040f593a9a464920337ebeb1df0f14914'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def apply(source,output):
    source=Path(source).absolute();output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Use a fresh evidence destination')
    if not output.parent.is_dir():raise ValueError('Evidence parent must exist')
    receipt=ROOT/'receipt.json'
    if digest(receipt)!=RECEIPT_SHA:raise ValueError('Review receipt changed')
    review=json.loads(receipt.read_text())
    patches=[]
    for row in review['patches']:
        patch=ROOT/row['path']
        if digest(patch)!=row['sha256']:raise ValueError('Patch hash mismatch')
        module=patch.stem
        if module not in review['source_revisions']:raise ValueError('Unknown module')
        patches.append((module,patch))
    for row in review['changes']:
        path=source/row['module']/row['path']
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink source path')
        if digest(path)!=row['before_sha256']:raise ValueError('Unexpected original source: '+row['module']+'/'+row['path'])
    # Validate all modules before writing any. The caller owns a disposable source copy.
    for module,patch in patches:subprocess.run(['git','apply','--check',str(patch)],cwd=source/module,check=True)
    for module,patch in patches:subprocess.run(['git','apply',str(patch)],cwd=source/module,check=True)
    for row in review['changes']:
        if digest(source/row['module']/row['path'])!=row['after_sha256']:raise RuntimeError('Patched source mismatch')
    result={'review_sha256':RECEIPT_SHA,'source_revision_expectations':review['source_revisions'],'scope':'22 changed source file hashes only; full source tree identity must be checked separately','applied':True,'native_compiled':False,'runtime_qualified':False,'changes':review['changes'],'patches':review['patches']}
    with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();apply(args.private_source,args.output)
    print('Reviewed source applied; native build and runtime qualification still required')
