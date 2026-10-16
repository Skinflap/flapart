"""Separate complete-chain runner preparation/receive. No native application launch.
Caller supplies immutable candidate/chain pins and explicit authenticated client.
"""
import secrets,shutil,tempfile,time
from pathlib import Path
import protocol as p,github_read as g,full_chain as f,response_full as response
import runner_fixture as owned


def prepare(binding,chain_pin,state_path,public_root,now=None):
 now=int(time.time()) if now is None else now;b=p.binding(binding);p.require(p.hexstr(chain_pin,64),'independent chain pin')
 state_path=Path(state_path);public_root=Path(public_root);owned.private_parent(state_path);owned.private_parent(public_root)
 p.require(state_path!=public_root and not state_path.is_relative_to(public_root),'private state outside public root')
 home=Path(tempfile.mkdtemp(prefix='flprun-',dir=Path('/tmp').resolve()));home.chmod(0o700);marker=secrets.token_hex(32);(home/'.rendezvous-owner').write_text(marker)
 state_created=public_created=False
 try:
  owned.command(['gpg','--no-options','--homedir',home,'--batch','--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Flapart ephemeral complete-chain recipient','rsa3072','encr','1d'])
  listing=owned.command(['gpg','--no-options','--homedir',home,'--batch','--with-colons','--list-keys']).decode();keys=[row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:')];p.require(len(keys)==1,'one ephemeral key')
  key=owned.command(['gpg','--no-options','--homedir',home,'--batch','--armor','--export',keys[0]])
  request=p.request(b,key,keys[0],secrets.token_hex(32),now,now+2700);st=home.stat()
  owned.store(state_path,{'schema':1,'home':str(home),'device':st.st_dev,'inode':st.st_ino,'owner':marker,'request':request});state_created=True
  public_root.mkdir(mode=0o700);public_created=True;(public_root/'request.json').write_bytes(p.encode(request));(public_root/'recipient-public.asc').write_bytes(key)
  return {'request_sha256':p.digest(p.encode(request)),'chain_manifest_sha256':chain_pin,'artifact_name':g.request_artifact_name(b),'expires':request['expires'],'native_executed':False,'release_qualified':False}
 except BaseException:
  try:owned.command(['gpgconf','--homedir',home,'--kill','all'])
  finally:
   shutil.rmtree(home)
   if state_created:state_path.unlink()
   if public_created:shutil.rmtree(public_root)
  raise


def receive(state_path,chain_pin,artifact_id,output,client,clock=time.time,sleep=time.sleep):
 p.require(p.hexstr(chain_pin,64) and g.integer(artifact_id),'independent chain/artifact pins');state_path=Path(state_path);state,home=owned.check_state(state_path);request=state['request'];b=request['binding'];output=f.fresh(output);output.mkdir(mode=0o700)
 evidence={'schema':1,'kind':'complete-chain-receiver','passed':False,'chain_verified':False,'native_executed':False,'source_closure_complete':False,'release_qualified':False,'request_sha256':p.digest(p.encode(request)),'chain_manifest_sha256':chain_pin,'artifact_id':artifact_id,'stage':'waiting'}
 try:
  while True:
   p.check_request(request,int(clock()))
   rows=client.json('/repos/'+b['repository']+'/releases?per_page=100');p.require(isinstance(rows,list) and len(rows)<100,'bounded complete-chain drafts')
   matches=[row for row in rows if isinstance(row,dict) and row.get('tag_name')==response.tag(request)];p.require(len(matches)<=1,'ambiguous complete-chain draft')
   if matches:
    rid,_=response.release_checked(matches[0],request,chain_pin)
    assets=client.json('/repos/'+b['repository']+f'/releases/{rid}/assets?per_page=100')
    p.require(isinstance(assets,list) and len(assets)<=2 and all(isinstance(a,dict) and a.get('name') in ('candidate.gpg','response.json') and a.get('uploader',{}).get('id')==b['operator_id'] for a in assets),'partial full-chain asset identity')
    names=[a['name'] for a in assets];p.require(len(set(names))==len(names),'duplicate partial asset')
    p.require(all(a.get('state') in ('starter','uploaded') for a in assets),'unknown upload state')
    if set(names)=={'candidate.gpg','response.json'} and all(a['state']=='uploaded' for a in assets):break
   sleep(min(10,max(1,request['expires']-int(clock()))))
  evidence['stage']='authenticated-download';verified=response.fetch(client,request,chain_pin,artifact_id,rid,output/'candidate.gpg',int(clock()))
  evidence.update(release_id=rid,descriptor_sha256=verified['descriptor_sha256'],ciphertext_sha256=verified['descriptor']['ciphertext_sha256'],stage='decrypt-restore-admit')
  # Supplied client token stays in this process. Strip every unapproved environment
  # entry around retention subprocesses using a child process, never global mutation.
  import subprocess,sys,json
  args_path=output/'receive-arguments.json';owned.store(args_path,{'request':request,'chain_pin':chain_pin,'descriptor':verified['descriptor'],'descriptor_sha256':verified['descriptor_sha256'],'encrypted':str(output/'candidate.gpg'),'home':str(home),'output':str(output/'admitted'),'now':int(clock())})
  result_path=output/'admission-child.json'
  with result_path.open('xb') as stream:
   result_path.chmod(0o600);completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'_receive',str(args_path)],env=owned.child_environment(),stdout=stream,stderr=subprocess.DEVNULL,timeout=900)
  p.require(completed.returncode==0 and result_path.stat().st_size<=65536,'complete-chain child failure/output bound')
  admitted=p.read_metadata(result_path);p.require(admitted.get('chain_verified') is True and admitted.get('native_executed') is False and admitted.get('release_qualified') is False,'receiver evidence-only admission')
  p.check_request(request,int(clock()));evidence.update(passed=True,chain_verified=True,stage='complete-chain-admitted',admission_sha256=p.file_digest(output/'admitted/admission.json'))
 except Exception as error:evidence.update(stage='failed-'+evidence['stage'],error_type=type(error).__name__)
 finally:
  try:owned.cleanup(state_path);evidence['ephemeral_home_removed']=True
  except Exception:evidence.update(passed=False,cleanup_failed=True,ephemeral_home_removed=False)
  owned.store(output/'full-chain-receiver.json',evidence)
 return evidence


def _child(path):
 values=p.read_metadata(p.regular(Path(path)));p.require(set(values)=={'request','chain_pin','descriptor','descriptor_sha256','encrypted','home','output','now'},'receive child arguments')
 return f.decrypt_restore_admit(Path(values['encrypted']),Path(values['home']),values['request'],values['chain_pin'],values['descriptor'],values['descriptor_sha256'],Path(values['output']),values['now'])

if __name__=='__main__':
 import sys
 try:
  p.require(len(sys.argv)==3 and sys.argv[1]=='_receive','library entrypoint only');result=_child(sys.argv[2]);print(p.encode(result).decode(),end='')
 except Exception:
  print('Complete-chain child failed; diagnostics withheld.',file=sys.stderr);sys.exit(1)
