#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a locally ad-hoc signed Mac bundle using upstream dependency collection."""
import argparse,pathlib,platform,os,subprocess,sys,json,hashlib,plistlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'portable'))
from binary_ids import macho_uuids
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
if platform.system()!='Darwin':raise SystemExit('Run on native macOS after the compiled fork probe passes.')
source=a.source.resolve();prefix=a.prefix.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Candidate output must be empty.')
assert 'flapartnativerc' in (source/'krita/main.cc').read_text()
env=dict(os.environ,PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH']);env.pop('BUILDROOT',None)
subprocess.run([sys.executable,str(source/'packaging/macos/macos-deploy.py'),'--install-dir',str(prefix),'--output-dir',str(out),'--krita-source',str(source)],env=env,check=True)
apps=list(out.glob('*.app'));assert len(apps)==1,'Expected exactly one application bundle'
root=out/'Flapart Studio.app';apps[0].rename(root)
plist=root/'Contents/Info.plist';info=plistlib.loads(plist.read_bytes());info.update(CFBundleIdentifier='com.flaptown.flapart-native',CFBundleName='Flapart Studio',CFBundleDisplayName='Flapart Studio');plist.write_bytes(plistlib.dumps(info))
assert (root/'Contents/MacOS/krita').is_file()
# Relocation changes Mach-O load commands; arm64 requires valid local code hashes.
# This is ad-hoc integrity signing, not Developer ID or notarization.
subprocess.run(['codesign','--force','--deep','--sign','-',str(root)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(root)],check=True)
files=[]
for f in sorted(root.rglob('*')):
 if f.is_symlink():files.append({'path':f.relative_to(out).as_posix(),'symlink':os.readlink(f)})
 elif f.is_file():files.append({'path':f.relative_to(out).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'macho_uuids':macho_uuids(f.read_bytes())})
(out/'candidate-inventory.json').write_text(json.dumps({'product':'Flapart Studio','platform':'macos-'+platform.machine(),'entrypoint':'Flapart Studio.app/Contents/MacOS/krita','runtime_collected':True,'relocation_test_passed':False,'source_closure_complete':False,'signed':False,'ad_hoc_signature':True,'developer_id_signed':False,'notarized':False,'publishable':False,'files':files},indent=2)+'\n')
print('Locally ad-hoc signed bundle assembled. Relocation, native probe and source/license closure still required; not publishable.')
