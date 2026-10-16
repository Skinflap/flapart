"""Disposable hosted Mac CI: installer transaction, no automated security approval."""
import argparse,json,os,platform,shutil,subprocess,tempfile,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--archive',type=Path);p.add_argument('--manifest',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert os.environ.get('GITHUB_ACTIONS')=='true' and platform.system()=='Darwin','Disposable hosted Mac only'
root=Path(__file__).parent
for name in ('Install Flapart.command','Flapart Studio.command'):subprocess.run(['/bin/bash','-n',str(root/name)],check=True)
if not a.archive or not a.manifest:
 result=subprocess.run(['/bin/bash',str(root/'Install Flapart.command')],capture_output=True,text=True)
 assert result.returncode and 'no qualified' in result.stderr
 print('Mac shell syntax and blocked-payload refusal passed; no native package tested.');raise SystemExit
with tempfile.TemporaryDirectory(prefix='flapart-installer-',dir=os.environ['RUNNER_TEMP']) as temp:
 temp=Path(temp);source=temp/'source';source.mkdir();dest=temp/'installed'
 for f in root.glob('*.command'):shutil.copy2(f,source/f.name)
 shutil.copy2(a.manifest,source/'release.json')
 subprocess.run(['/bin/bash',str(source/'Install Flapart.command'),str(a.archive.resolve()),str(dest)],check=True)
 receipt=dest/'flapart-install.json';before=receipt.read_bytes();record=json.loads(before)
 app=dest/'releases'/record['release']/'Flapart Studio.app';assert app.is_dir()
 archive_quarantine=subprocess.run(['/usr/bin/xattr','-p','com.apple.quarantine',str(a.archive)],capture_output=True)
 app_quarantine=subprocess.run(['/usr/bin/xattr','-p','com.apple.quarantine',str(app)],capture_output=True)
 if archive_quarantine.returncode==0:assert app_quarantine.returncode==0

 corrupt=temp/'corrupt.zip';corrupt.write_bytes(b'deliberately invalid candidate')
 bad=subprocess.run(['/bin/bash',str(source/'Install Flapart.command'),str(corrupt),str(dest)],capture_output=True,text=True)
 assert bad.returncode and 'checksum' in bad.stderr and receipt.read_bytes()==before
 a.output.mkdir(parents=True,exist_ok=True)
 (a.output/'installer-result.json').write_text(json.dumps({'installer_passed':True,'corrupted_upgrade_refused':True,'active_receipt_preserved':True,'existing_quarantine_preserved':True,'downloaded_user_gatekeeper_flow_tested':False,'security_approval_automated':False,'native_runtime_tested':False,'platform':platform.platform(),'sha256':record['sha256']},indent=2)+'\n')
print('Mac installer transaction and corrupt-upgrade refusal passed; native runtime probe remains separate.')
