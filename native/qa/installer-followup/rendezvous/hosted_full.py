#!/usr/bin/env python3
"""Manual hosted complete-chain CLI. No dispatch, upload, release or secret enrollment.
Only run invokes native installer after actual admission and host gates.
"""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path
import protocol as p,github_read as g,runner_full,candidate_runner as candidate
import runner_fixture as owned

WORKFLOW='.github/workflows/native-installer-full-chain.yml'
INPUTS={'candidate_sha256':'FLAPART_CANDIDATE_SHA256','candidate_bytes':'FLAPART_CANDIDATE_BYTES','inventory_sha256':'FLAPART_INVENTORY_SHA256','manifest_sha256':'FLAPART_MANIFEST_SHA256','chain_manifest_sha256':'FLAPART_CHAIN_SHA256'}
SELECTED={
 'hosted-result.json':'hosted-result.json',
 'receiver.json':'receiver/full-chain-receiver.json',
 'admission.json':'receiver/admitted/admission.json',
 'installer-adapter.json':'installer/candidate-installer-evidence.json',
 'installer-e2e.json':'installer/installer/installer-e2e.json',
 'native-first.json':'installer/installer/native-first/result.json',
 'native-upgrade.json':'installer/installer/native-upgrade/result.json',
}
MAX_RECEIPT=1024**2


def number(value):
 p.require(isinstance(value,str) and re.fullmatch('[1-9][0-9]{0,19}',value),'positive bounded decimal required');return int(value)

def context(env):
 p.require(env.get('GITHUB_ACTIONS')=='true' and env.get('CI')=='true' and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch','actual manual Actions context required')
 repo=env.get('GITHUB_REPOSITORY','');p.require(re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo),'repository')
 commit=env.get('GITHUB_SHA','');p.require(p.hexstr(commit,40),'checkout SHA')
 arch=env.get('FLAPART_ARCHITECTURE');p.require(arch in ('arm64','x86_64'),'bounded architecture')
 ref=env.get('GITHUB_WORKFLOW_REF','');p.require(ref.startswith(repo+'/'+WORKFLOW+'@refs/heads/'),'exact manual workflow ref')
 values={}
 for key,name in INPUTS.items():
  value=env.get(name,'')
  if key=='candidate_bytes':values[key]=number(value);p.require(values[key]<=p.LIMIT,'candidate size bound')
  else:p.require(p.hexstr(value,64),'immutable SHA input');values[key]=value
 return {'repository':repo,'workflow':WORKFLOW,'run_id':number(env.get('GITHUB_RUN_ID','')),'attempt':number(env.get('GITHUB_RUN_ATTEMPT','')),'commit':commit,'architecture':arch,'operator_id':number(env.get('GITHUB_ACTOR_ID','')),**values}


def authenticate_binding(ctx,client):
 base='/repos/'+ctx['repository'];run=client.json(base+f"/actions/runs/{ctx['run_id']}")
 expected={'id':ctx['run_id'],'run_attempt':ctx['attempt'],'head_sha':ctx['commit'],'path':WORKFLOW,'event':'workflow_dispatch','status':'in_progress'}
 p.require(all(p.equal(run.get(k),v) for k,v in expected.items()) and run.get('repository',{}).get('full_name')==ctx['repository'] and run.get('actor',{}).get('id')==ctx['operator_id'] and run.get('triggering_actor',{}).get('id')==ctx['operator_id'],'authenticated run/operator mismatch')
 jobs=client.json(base+f"/actions/runs/{ctx['run_id']}/attempts/{ctx['attempt']}/jobs?per_page=100")
 p.require(isinstance(jobs,dict) and type(jobs.get('total_count')) is int and 0<jobs['total_count']<=100 and isinstance(jobs.get('jobs'),list) and len(jobs['jobs'])==jobs['total_count'],'complete job list')
 matches=[j for j in jobs['jobs'] if isinstance(j,dict) and j.get('name')=='installer-'+ctx['architecture'] and j.get('status')=='in_progress']
 p.require(len(matches)==1,'unique active matrix job');job=matches[0]
 label={'arm64':'macos-15','x86_64':'macos-15-intel'}[ctx['architecture']]
 p.require(job.get('run_id')==ctx['run_id'] and isinstance(job.get('labels'),list) and label in job['labels'] and g.integer(job.get('id')),'job identity/runner label')
 return p.binding({k:v for k,v in ctx.items() if k!='chain_manifest_sha256'}|{'job_id':job['id']})


def git(repo,args):
 result=subprocess.run(['git','-C',str(repo),*args],env=owned.child_environment(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
 p.require(result.returncode==0,'checked-out source verification failed');return result.stdout

def verify_committed(repo,commit,paths):
 repo=Path(repo);p.require(repo.is_absolute() and repo.is_dir() and repo.resolve()==repo,'canonical checkout')
 p.require(git(repo,['rev-parse','HEAD']).decode().strip()==commit,'checkout differs from authenticated commit')
 hashes={}
 for path in sorted(set(Path(x) for x in paths)):
  p.regular(path);p.require(path.is_relative_to(repo),'helper outside checkout')
  name=path.relative_to(repo).as_posix();original=git(repo,['show',commit+':'+name])
  p.require(p.digest(original)==p.file_digest(path),'helper differs from exact checked-out commit');hashes[name]=p.file_digest(path)
 return hashes


def checkout_inputs(repo,commit):
 repo=Path(repo);installer=repo/'native/installers/macos-online';probe=repo/'native/qa/portable'
 pins=candidate.helper_inputs(installer,probe);paths=[]
 for name in pins:
  prefix,relative=name.split('/',1);paths.append((installer if prefix=='installer' else probe)/relative)
 for directory in ('native/qa/installer-followup/rendezvous','native/distribution/private-retention','native/distribution/provenance'):
  paths.extend((repo/directory).glob('*.py'))
 paths.append(repo/'native/distribution/source-qualification/native_metadata.py')
 return pins,verify_committed(repo,commit,paths)


def save(root,name,value):
 path=root/name;temporary=root/(name+'.pending')
 with temporary.open('xb') as stream:temporary.chmod(0o600);stream.write(p.encode(value))
 temporary.replace(path)


def prepare(root,repo,env,client):
 ctx=context(env);binding=authenticate_binding(ctx,client);pins,committed=checkout_inputs(repo,ctx['commit']);root=Path(root)
 owned.private_parent(root);root.mkdir(mode=0o700)
 session={'schema':1,'context':ctx,'binding':binding,'helper_pins':pins,'committed_helpers':committed}
 save(root,'session.json',session)
 try:
  result=runner_full.prepare(binding,ctx['chain_manifest_sha256'],root/'private-state.json',root/'public')
  return {**result,'candidate_sha256':binding['candidate_sha256']}
 except Exception:
  save(root,'hosted-result.json',{'schema':1,'passed':False,'stage':'prepare-failed','native_executed':False,'source_closure_complete':False,'release_qualified':False});raise


def run(root,repo,env,client):
 root=Path(root);ctx=context(env);session=p.read_metadata(p.regular(root/'session.json'))
 p.require(session.get('schema')==1 and p.equal(session.get('context'),ctx),'immutable session/context changed')
 binding=authenticate_binding(ctx,client);p.require(p.equal(session['binding'],binding),'authenticated binding changed')
 pins,committed=checkout_inputs(repo,ctx['commit']);p.require(p.equal(pins,session['helper_pins']) and p.equal(committed,session['committed_helpers']),'checked-out helpers changed')
 artifact=number(env.get('FLAPART_REQUEST_ARTIFACT_ID',''))
 result={'schema':1,'passed':False,'stage':'receive','native_executed':False,'source_closure_complete':False,'release_qualified':False,'commit':ctx['commit'],'binding':binding,'chain_manifest_sha256':ctx['chain_manifest_sha256'],'artifact_id':artifact}
 save(root,'hosted-result.json',result)
 try:
  received=runner_full.receive(root/'private-state.json',ctx['chain_manifest_sha256'],artifact,root/'receiver',client)
  p.require(received.get('passed') is True and received.get('chain_verified') is True,'full-chain receiver did not admit candidate')
  # The authenticated descriptor pins the actual received ciphertext; admission
  # rechecks its hash and all original bytes before the real installer runs.
  request=p.read_metadata(root/'public/request.json');p.require(p.equal(request['binding'],binding),'public request changed')
  child=p.read_metadata(root/'receiver/receive-arguments.json');p.require(p.equal(child['request'],request) and child['chain_pin']==ctx['chain_manifest_sha256'],'receiver arguments changed')
  admitted=root/'receiver/admitted';result['stage']='actual-installer';save(root,'hosted-result.json',result)
  actual=candidate.run_installer(admitted/'recovered',request,admitted/'envelope/installer-original.json',ctx['chain_manifest_sha256'],root/'receiver/candidate.gpg',child['descriptor']['ciphertext_sha256'],Path(repo)/'native/installers/macos-online',Path(repo)/'native/qa/portable',root/'installer',pins)
  p.require(actual.get('passed') is True and actual.get('native_executed') is True,'actual installed-runtime test failed')
  result.update(passed=True,native_executed=True,stage='actual-installed-runtime-verified')
 except Exception as error:result.update(stage='failed-'+result['stage'],error_type=type(error).__name__)
 finally:save(root,'hosted-result.json',result)
 return result


def cleanup(root):
 root=Path(root);state=root/'private-state.json'
 if state.exists():owned.cleanup(state)
 return {'ephemeral_state_present':state.exists(),'native_executed':False}


def collect(root):
 root=Path(root);p.require(root.is_absolute() and root.is_dir() and not any(x.is_symlink() for x in (root,*root.parents)),'canonical evidence root')
 destination=root/'selected-json';owned.private_parent(destination);destination.mkdir(mode=0o700);rows=[]
 try:
  for name,relative in SELECTED.items():
   source=root/relative
   if not source.exists():continue
   p.regular(source);p.require(source.stat().st_size<=MAX_RECEIPT,'selected receipt exceeds bound')
   # Strict duplicate-aware parse, no truncation or conversion to passing results.
   candidate.chain.read_json(source);data=source.read_bytes();target=destination/name
   with target.open('xb') as stream:target.chmod(0o600);stream.write(data)
   rows.append({'path':name,'bytes':len(data),'sha256':p.digest(data)})
  p.require(len(rows)<=len(SELECTED) and sum(r['bytes'] for r in rows)<=len(SELECTED)*MAX_RECEIPT,'selected evidence bounds')
  save(destination,'selection.json',{'schema':1,'files':rows,'selection_only':True,'source_closure_complete':False,'release_qualified':False})
  return {'selected_files':len(rows),'selected_bytes':sum(r['bytes'] for r in rows),'release_qualified':False}
 except Exception:
  import shutil;shutil.rmtree(destination);raise


def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','run','cleanup','collect'));parser.add_argument('--root',type=Path,required=True);parser.add_argument('--workspace',type=Path);parser.add_argument('--token-env');args=parser.parse_args()
 # These are workflow-owned paths, canonicalized once for macOS /var aliases.
 root=args.root.absolute().parent.resolve()/args.root.name;repo=args.workspace.resolve() if args.workspace else None
 try:
  if args.command in ('prepare','run'):
   p.require(repo is not None and args.token_env is not None,'workspace and explicit token env required');token=owned.consume_token(args.token_env);client=g.Client(token);del token
   result=prepare(root,repo,os.environ,client) if args.command=='prepare' else run(root,repo,os.environ,client)
  else:result=cleanup(root) if args.command=='cleanup' else collect(root)
  print(json.dumps(result,sort_keys=True));return 0 if result.get('passed',True) else 1
 except Exception:
  print('Hosted complete-chain step failed; raw diagnostics withheld.',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
