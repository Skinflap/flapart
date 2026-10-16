#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a locally ad-hoc signed Mac bundle using upstream dependency collection."""
import argparse,pathlib,platform,os,subprocess,sys,json,hashlib,plistlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'portable'))
from binary_ids import macho_uuids
from macho_format import is_macho
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--universal',action='store_true');p.add_argument('--maintained-work',type=pathlib.Path,required=True);p.add_argument('--promotion-receipt',type=pathlib.Path,required=True);a=p.parse_args()
if platform.system()!='Darwin':raise SystemExit('Run on native macOS after the compiled fork probe passes.')
source=a.source.resolve();prefix=a.prefix.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Candidate output must be empty.')
maintained=a.maintained_work.resolve();assert prefix==maintained/'sdk','Package the promoted maintained SDK only'
promotion=json.loads(a.promotion_receipt.read_text());assert promotion['promoted'] and pathlib.Path(promotion['sdk']).resolve()==prefix
for row in promotion['copied']:
 path=prefix/row['path'];assert path.resolve().is_relative_to(prefix) and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],('Promoted component changed',row['path'])
python_receipt=json.loads((maintained/'python-build/python-build-receipt.json').read_text());assert python_receipt['compiled']
assert 'flapartnativerc' in (source/'krita/main.cc').read_text()
env=dict(os.environ,PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH']);env.pop('BUILDROOT',None)
subprocess.run([sys.executable,str(source/'packaging/macos/macos-deploy.py'),'--install-dir',str(prefix),'--output-dir',str(out),'--krita-source',str(source)],env=env,check=True)
apps=list(out.glob('*.app'));assert len(apps)==1,'Expected exactly one application bundle'
root=out/'Flapart Studio.app';apps[0].rename(root)
plist=root/'Contents/Info.plist';info=plistlib.loads(plist.read_bytes());info.update(CFBundleIdentifier='com.flaptown.flapart-native',CFBundleName='Flapart Studio',CFBundleDisplayName='Flapart Studio');plist.write_bytes(plistlib.dumps(info))
assert (root/'Contents/MacOS/krita').is_file()
# Complete maintained Python, trust assets and native relocation before signing.
# This operates on a private staged copy and refuses unresolved imports.
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('complete-maintained-runtime.py')),
 '--bundle',str(root),'--sdk',str(prefix),'--private-prefix',str(maintained/'python-stage'),
 '--private-prefix',str(maintained/'openssl'),
 '--openssl-license',str(maintained/'openssl-build/arm64/openssl-3.5.9/LICENSE.txt'),
 '--python-license',str(maintained/'python-build/Python-3.13.16/LICENSE'),
 '--certificate-sha256',python_receipt['ca_snapshot_sha256'],
 '--output',str(out/'maintained-runtime.json'),'--apply'],check=True)
# Relocation changes Mach-O load commands; arm64 requires valid local code hashes.
# This is ad-hoc integrity signing, not Developer ID or notarization.
subprocess.run(['codesign','--force','--deep','--sign','-',str(root)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(root)],check=True)
files=[]
for f in sorted(root.rglob('*')):
 if f.is_symlink():files.append({'path':f.relative_to(out).as_posix(),'symlink':os.readlink(f)})
 elif f.is_file():
  data=f.read_bytes();uuids=macho_uuids(data);architectures=[]
  if is_macho(data):
   architectures=sorted(subprocess.check_output(['lipo','-archs',str(f)],text=True).strip().split())
   if a.universal and not {'arm64','x86_64'}.issubset(architectures):raise RuntimeError('Universal runtime contains a single-architecture binary: '+str(f.relative_to(root)))
  files.append({'path':f.relative_to(out).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'macho_uuids':uuids,'architectures':architectures})
if a.universal:
 main_arches=subprocess.check_output(['lipo','-archs',str(root/'Contents/MacOS/krita')],text=True).split()
 assert {'arm64','x86_64'}.issubset(main_arches),'Main application is not universal'
(out/'candidate-inventory.json').write_text(json.dumps({'product':'Flapart Studio','platform':'macos-universal2' if a.universal else 'macos-'+platform.machine(),'entrypoint':'Flapart Studio.app/Contents/MacOS/krita','runtime_collected':True,'relocation_test_passed':False,'source_closure_complete':False,'signed':False,'ad_hoc_signature':True,'developer_id_signed':False,'notarized':False,'publishable':False,'files':files},indent=2)+'\n')
print('Locally ad-hoc signed bundle assembled. Relocation, native probe and source/license closure still required; not publishable.')
