#!/usr/bin/env python3
"""Explicit complete-chain exchange command; importing never accesses GitHub."""
import argparse
import json
import sys
from pathlib import Path
import protocol as p
import coordinator_full as full
from coordinator_fixture import GhAdapter

class Parser(argparse.ArgumentParser):
 def error(self, message):
  raise ValueError('Invalid command arguments; use --help')

class CheckedAdapter:
 """Recheck the current authenticated identity before each mutation."""
 def __init__(self, delegate, operator):self.delegate=delegate;self.operator=operator
 @property
 def reader(self):return self.delegate.reader
 def operator_id(self):return self.delegate.operator_id()
 def check(self):p.require(self.operator_id()==self.operator,'authenticated operator changed')
 def create(self,*args):self.check();return self.delegate.create(*args)
 def upload(self,*args):self.check();return self.delegate.upload(*args)
 def delete(self,*args):self.check();return self.delegate.delete(*args)

def parser():
 root=Parser(description=__doc__);sub=root.add_subparsers(dest='command',required=True,parser_class=Parser)
 for name in ('coordinate','cleanup'):
  s=sub.add_parser(name)
  s.add_argument('--binding',type=Path,required=True,help='Independent exact run/job/operator/candidate binding JSON')
  s.add_argument('--artifact-id',type=int,required=True)
  s.add_argument('--chain-sha256',required=True)
  if name=='coordinate':
   s.add_argument('--recovered-root',type=Path,required=True)
   s.add_argument('--original-manifest',type=Path,required=True)
   s.add_argument('--output',type=Path,required=True,help='Fresh private output, separate from inputs')
  else:s.add_argument('--receipt',type=Path,required=True)
 return root

def canonical_directory(value):
 path=value.absolute()
 p.require(path.is_dir() and not any(x.is_symlink() for x in (path,*path.parents)),'canonical input directory')
 return path

def execute(args, adapter_factory=GhAdapter):
 b=p.binding(p.read_metadata(p.regular(args.binding.absolute())))
 p.require(type(args.artifact_id) is int and args.artifact_id>0 and p.hexstr(args.chain_sha256,64),'independent artifact/chain pins')
 if args.command=='coordinate':
  root=canonical_directory(args.recovered_root);manifest=p.regular(args.original_manifest.absolute());output=args.output.absolute()
  full.f.fresh(output)
  p.require(not output.is_relative_to(root) and not root.is_relative_to(output) and not manifest.is_relative_to(output) and not args.binding.absolute().is_relative_to(output),'output/input overlap')
  for name,pin in (('candidate.zip',b['candidate_sha256']),('candidate-inventory.json',b['inventory_sha256']),('chain-manifest.json',args.chain_sha256)):
   path=p.regular(root/name);p.require(p.file_digest(path)==pin,'local input pin mismatch')
  p.require((root/'candidate.zip').stat().st_size==b['candidate_bytes'] and p.file_digest(manifest)==b['manifest_sha256'],'local manifest/size pin mismatch')
 else:
  receipt=p.regular(args.receipt.absolute());r=p.read_metadata(receipt)
  p.require(r.get('schema')==1 and r.get('kind')=='full-chain-coordinator' and p.equal(r.get('binding'),b) and r.get('artifact_id')==args.artifact_id and r.get('chain_manifest_sha256')==args.chain_sha256 and r.get('cleanup_complete') is False,'cleanup receipt binding')
 adapter=CheckedAdapter(adapter_factory(),b['operator_id']);adapter.check()
 if args.command=='coordinate':r=full.coordinate(b,args.artifact_id,root,manifest,args.chain_sha256,output,adapter)
 else:r=full.cleanup(b,args.artifact_id,args.chain_sha256,receipt,adapter)
 return {'ready':r.get('ready') is True,'cleanup_complete':r.get('cleanup_complete') is True,'release_id':r.get('release_id'),'native_executed':False,'source_closure_complete':False,'release_qualified':False}

def main(argv=None,adapter_factory=GhAdapter):
 try:
  result=execute(parser().parse_args(argv),adapter_factory)
  print(json.dumps(result,sort_keys=True));return 0
 except Exception:
  print('Complete-chain coordinator failed; diagnostics withheld. Inspect the scoped receipt if created.',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
