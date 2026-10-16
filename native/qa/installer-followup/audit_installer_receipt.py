#!/usr/bin/env python3
"""Audit captured installer receipts without inferring missing execution claims.
No launch, archive extraction, signing, transfer, or release qualification.
"""
import argparse,hashlib,json,re
from pathlib import Path

GATES=('installer_passed','native_runtime_tested','profile_isolation_verified',
 'ordinary_krita_unchanged','native_canvas_png_kra_passed','studio_menu_reopens',
 'failed_upgrade_preserved_receipt','failed_upgrade_preserved_artwork_and_settings',
 'successful_upgrade_preserved_artwork_and_settings','previous_runtime_retained')
TARGETS={'windows-x86_64':{'x86_64'},'macos-x86_64':{'x86_64'},'macos-arm64':{'arm64'},'macos-universal2':{'arm64','x86_64'}}

def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def regular(path):
 path=Path(path).absolute()
 if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
  raise ValueError('Use an existing regular input without symlink parents')
 return path

def document(path):
 path=regular(path)
 if path.stat().st_size>4*1024**2:raise ValueError('Oversized receipt')
 raw=path.read_bytes();data=json.loads(raw)
 if not isinstance(data,dict):raise ValueError('Receipt must be an object')
 return data,hashlib.sha256(raw).hexdigest()

def audit(archive,expected,receipt,child,target,architecture):
 if target not in TARGETS or architecture not in TARGETS[target]:raise ValueError('Unsupported target/architecture')
 if not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Expected SHA256 must be pinned explicitly')
 archive=regular(archive)
 if digest(archive)!=expected:raise ValueError('Candidate differs from pinned archive')
 data,receipt_sha=document(receipt);native,child_sha=document(child);gaps=[]
 def need(ok,label):
  if not ok:gaps.append(label)
 need(data.get('passed') is True,'installer.passed')
 need(data.get('native_child_exit_observed') is True,'installer.native_child_exit_observed')
 need(data.get('payload_sha256')==expected,'installer.payload_sha256')
 need(data.get('target_platform')==target,'installer.target_platform')
 need(data.get('runtime_scope')=='installed-runtime','installer.runtime_scope')
 need(data.get('native_execution') is True,'installer.native_execution')
 need(data.get('security_approval_automated') is False,'installer.security_approval_automated')
 need('error' not in data and not data.get('blocked'),'installer.failure_absent')
 for key in GATES:need(data.get(key) is True,'installer.'+key)
 for label,record in (('installer',data),('child',native)):
  arch=record.get('process_architecture');hardware=record.get('hardware_architecture');mode=record.get('execution_mode')
  need(arch==architecture,label+'.process_architecture')
  need(hardware in ('arm64','x86_64') and (mode=='native' and hardware==arch or mode=='translated' and target.startswith('macos') and hardware=='arm64' and arch=='x86_64'),label+'.execution_identity')
 need('error' not in native,'child.failure_absent')
 for key in ('process_architecture','hardware_architecture','execution_mode'):
  need(data.get(key) is not None and data.get(key)==native.get(key),'installer_child_agreement.'+key)
 # New producer must hash-bind its actual child output. A matching architecture
 # alone must not allow substitution of an unrelated successful probe receipt.
 need(data.get('native_probe_sha256')==child_sha,'installer.native_probe_sha256')
 need(digest(archive)==expected,'archive_unchanged_during_audit')
 return {'schema':1,'scope':'portable audit of captured installer claims, not native execution',
         'payload_sha256':expected,'target_platform':target,'requested_process_architecture':architecture,
         'receipt_sha256':receipt_sha,'child_receipt_sha256':child_sha,
         'installer_fields_complete':not gaps,'gaps':gaps,
         'native_test_performed_by_auditor':False,'source_closure_checked':False,
         'release_qualified':False,'binary_published':False}

def main():
 p=argparse.ArgumentParser()
 for name in ('archive','receipt','child','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--sha256',required=True);p.add_argument('--target',choices=TARGETS,required=True);p.add_argument('--architecture',choices=('arm64','x86_64'),required=True)
 a=p.parse_args()
 if a.output.exists() or a.output.is_symlink():raise ValueError('Use a fresh output')
 result=audit(a.archive,a.sha256,a.receipt,a.child,a.target,a.architecture)
 with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 return 0 if result['installer_fields_complete'] else 1
if __name__=='__main__':raise SystemExit(main())
