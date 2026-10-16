#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a locally ad-hoc signed Mac bundle using upstream dependency collection."""
import argparse,pathlib,platform,os,subprocess,sys,json,hashlib,plistlib,shutil
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'portable'))
from binary_ids import macho_uuids
from macho_format import is_macho
from package_stage import run_stage, validate_evidence
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--prefix',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--universal',action='store_true');p.add_argument('--maintained-work',type=pathlib.Path,required=True);p.add_argument('--promotion-receipt',type=pathlib.Path,required=True);p.add_argument('--stage-evidence',type=pathlib.Path);p.add_argument('--retain-native-bytes',action='store_true');a=p.parse_args()
if platform.system()!='Darwin':raise SystemExit('Run on native macOS after the compiled fork probe passes.')
source=a.source.resolve();prefix=a.prefix.resolve();out=a.output.resolve();validate_evidence(out,a.stage_evidence,a.retain_native_bytes);out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()):raise SystemExit('Candidate output must be empty.')
maintained=a.maintained_work.resolve();assert prefix==maintained/'sdk','Package the promoted maintained SDK only'
promotion=json.loads(a.promotion_receipt.read_text());assert promotion['promoted'] and pathlib.Path(promotion['sdk']).resolve()==prefix
for row in promotion['copied']:
 path=prefix/row['path'];assert path.resolve().is_relative_to(prefix) and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],('Promoted component changed',row['path'])
python_receipt=json.loads((maintained/'python-build/python-build-receipt.json').read_text());assert python_receipt['compiled']
assert 'flapartnativerc' in (source/'krita/main.cc').read_text()
env=dict(os.environ,PATH=str(prefix/'bin')+os.pathsep+os.environ['PATH']);env.pop('BUILDROOT',None);env['PYTHONDONTWRITEBYTECODE']='1'
assert (prefix/'bin/python').is_file() and (prefix/'bin/python').resolve().is_relative_to(prefix),'Required SDK python command missing or escaping'
root=out/'Flapart Studio.app'
helper=pathlib.Path(__file__).with_name('package_stage.py')
collector=source/'packaging/macos/macos-deploy.py'
recorder_helpers=[pathlib.Path(__file__)]
def stage(name,command,helpers=(),tools=(),sdk=None):
 run_stage(name,command,root,a.stage_evidence,[*recorder_helpers,*helpers],tools,a.retain_native_bytes,env,sdk)
stage('collector',[sys.executable,str(helper),'--source',str(source),'--prefix',str(prefix),'--output',str(out)],
 helpers=[collector],tools=['install_name_tool','lipo','otool','codesign','rsync','file','/usr/libexec/PlistBuddy','krita_version','python','macdeployqt']+(['qtpaths'] if shutil.which('qtpaths',path=env['PATH']) else []),sdk=prefix)
# Complete maintained Python, trust assets and native relocation before signing.
# This operates on a private staged copy and refuses unresolved imports.
stage('completion',[sys.executable,str(pathlib.Path(__file__).with_name('complete-maintained-runtime.py')),
 '--bundle',str(root),'--sdk',str(prefix),'--private-prefix',str(maintained/'python-stage'),
 '--private-prefix',str(maintained/'openssl'),
 '--openssl-license',str(maintained/'openssl-build/arm64/openssl-3.5.9/LICENSE.txt'),
 '--python-license',str(maintained/'python-build/Python-3.13.16/LICENSE'),
 '--certificate-sha256',python_receipt['ca_snapshot_sha256'],
 '--output',str(out/'maintained-runtime.json'),'--apply'],helpers=[pathlib.Path(__file__).with_name('complete-maintained-runtime.py'),pathlib.Path(__file__).resolve().parents[2]/'distribution/source-qualification/native_metadata.py'],tools=['install_name_tool'])
# Relocation changes Mach-O load commands; arm64 requires valid local code hashes.
# This is ad-hoc integrity signing, not Developer ID or notarization.
stage('codesign',['codesign','--force','--deep','--sign','-',str(root)],tools=['codesign'])
stage('verify',['codesign','--verify','--deep','--strict',str(root)],tools=['codesign'])
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
