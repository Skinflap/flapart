#!/usr/bin/env python3
"""Harmless runner exchange only: prepare, receive, cleanup. Never native launch."""
import argparse,importlib.util,json,os,re,secrets,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
import fixture,protocol as p,github_read as g

RETENTION=Path(__file__).resolve().parents[3]/'distribution/private-retention/retain.py'
STATE_KEYS={'schema','home','device','inode','owner','request'}
FIXTURE_LIMIT=128*1024

def child_environment():
 # No GitHub token, inherited search/injection variables or user GPG home.
 return {k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','TMP','TEMP','LANG','LC_ALL','SystemRoot','WINDIR')}

def consume_token(name):
 p.require(isinstance(name,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,63}',name),'explicit token environment name')
 token=os.environ.pop(name,None);p.require(isinstance(token,str) and bool(token),'missing explicitly named token')
 return token

def command(argv):
 result=subprocess.run([str(x) for x in argv],env=child_environment(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=90)
 p.require(result.returncode==0,'fixture child command failed')
 p.require(len(result.stdout)<=65536,'fixture child output limit')
 return result.stdout

def private_parent(path):
 p.require(path.is_absolute() and path.parent.is_dir() and not any(x.is_symlink() for x in (path,*path.parents)),'canonical path required')
 p.require(not path.exists(),'fresh path required')

def store(path,value):
 with path.open('xb') as stream:path.chmod(0o600);stream.write(p.encode(value))

def check_state(path):
 p.regular(path);p.require(path.stat().st_mode&0o077==0 and path.stat().st_uid==os.getuid(),'private state permissions')
 obj=p.read_metadata(path);p.require(set(obj)==STATE_KEYS and type(obj['schema']) is int and obj['schema']==1,'state fields')
 home=Path(obj['home']);p.require(home.is_absolute() and home.parent==Path('/tmp').resolve() and re.fullmatch('flprun-[A-Za-z0-9_-]+',home.name),'owned short home path')
 p.require(home.is_dir() and not any(x.is_symlink() for x in (home,*home.parents)),'owned home type')
 st=home.stat();p.require(st.st_uid==os.getuid() and st.st_mode&0o077==0 and (st.st_dev,st.st_ino)==(obj['device'],obj['inode']),'owned home identity')
 marker=home/'.rendezvous-owner';p.regular(marker);p.require(p.hexstr(obj['owner'],64) and marker.read_text()==obj['owner'],'owned home marker')
 return obj,home

def cleanup(state_path):
 state_path=Path(state_path);obj,home=check_state(state_path)
 try:command(['gpgconf','--homedir',home,'--kill','all'])
 finally:shutil.rmtree(home);state_path.unlink()

def prepare(binding,state_path,public_root,now=None):
 now=int(time.time()) if now is None else now
 state_path=Path(state_path);public_root=Path(public_root);private_parent(state_path);private_parent(public_root)
 p.require(state_path!=public_root and not state_path.is_relative_to(public_root),'state must be outside public artifact root')
 p.require(set(binding)==p.BINDING-set(fixture.pins()),'fixture identity fields only')
 b=p.binding(dict(binding,**fixture.pins()));home=Path(tempfile.mkdtemp(prefix='flprun-',dir=Path('/tmp').resolve()));home.chmod(0o700)
 owner=secrets.token_hex(32);(home/'.rendezvous-owner').write_text(owner)
 state_created=public_created=False
 try:
  command(['gpg','--no-options','--homedir',home,'--batch','--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Flapart disposable harmless fixture','rsa2048','encr','1d'])
  listing=command(['gpg','--no-options','--homedir',home,'--batch','--with-colons','--list-keys']).decode()
  keys=[line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:')];p.require(len(keys)==1,'single ephemeral primary key')
  key=command(['gpg','--no-options','--homedir',home,'--batch','--armor','--export',keys[0]])
  request=p.request(b,key,keys[0],secrets.token_hex(32),now,now+2700)
  st=home.stat();state={'schema':1,'home':str(home),'device':st.st_dev,'inode':st.st_ino,'owner':owner,'request':request};store(state_path,state);state_created=True
  public_root.mkdir(mode=0o700);public_created=True
  (public_root/'request.json').write_bytes(p.encode(request));(public_root/'recipient-public.asc').write_bytes(key)
  return {'request_sha256':p.digest(p.encode(request)),'artifact_name':g.request_artifact_name(b),'expires':request['expires'],'native_executed':False}
 except BaseException:
  try:command(['gpgconf','--homedir',home,'--kill','all'])
  finally:
   shutil.rmtree(home)
   if state_created:state_path.unlink()
   if public_created:shutil.rmtree(public_root)
  raise

def find_release(client,obj):
 releases=client.json('/repos/'+obj['binding']['repository']+'/releases?per_page=100')
 p.require(isinstance(releases,list) and len(releases)<100,'bounded draft listing')
 matches=[r for r in releases if isinstance(r,dict) and r.get('tag_name')==g.draft_tag(obj)]
 p.require(len(matches)<=1,'ambiguous draft exchange')
 if not matches:return None
 p.require(g.integer(matches[0].get('id')),'draft ID')
 return matches[0]['id']

def receive(state_path,output,client,clock=time.time,sleep=time.sleep):
 state_path=Path(state_path);output=Path(output);private_parent(output)
 obj,home=check_state(state_path);request=obj['request']
 # Never accept caller-selected runtime pins: this harness is fixture-only.
 p.require(all(request['binding'][k]==v for k,v in fixture.pins().items()),'non-fixture candidate refused')
 output.mkdir(mode=0o700);evidence={'schema':1,'passed':False,'native_executed':False,'release_qualified':False,'request_sha256':p.digest(p.encode(request)),'stage':'waiting'}
 try:
  while True:
   p.check_request(request,int(clock()));release=find_release(client,request)
   if release is not None:
    assets=client.json('/repos/'+request['binding']['repository']+f'/releases/{release}/assets?per_page=100')
    p.require(isinstance(assets,list) and len(assets)<=2 and all(isinstance(a,dict) and a.get('name') in ('candidate.gpg','response.json') and a.get('uploader',{}).get('id')==request['binding']['operator_id'] for a in assets),'unexpected exchange assets')
    names=[a['name'] for a in assets];p.require(len(set(names))==len(names),'duplicate exchange assets')
    p.require(all(a.get('state') in ('starter','uploaded') for a in assets),'unknown upload state')
    if set(names)=={'candidate.gpg','response.json'} and all(a['state']=='uploaded' for a in assets):
     p.require(all(type(a.get('size')) is int and 0<a['size']<=FIXTURE_LIMIT for a in assets),'fixture asset bound');break
   sleep(min(10,max(1,request['expires']-int(clock()))))
  evidence['stage']='download';result=g.fetch_response(client,request,release,output/'candidate.gpg',int(clock()))
  evidence['ciphertext_sha256']=result['response']['sha256'];evidence['release_id']=release
  evidence['stage']='decrypt'
  command([sys.executable,Path(__file__).resolve(),'_decrypt','--state',state_path,'--encrypted',output/'candidate.gpg','--sha256',result['response']['sha256'],'--output',output/'recovered'])
  p.validate_pack(output/'recovered',request,int(clock()))
  for name,data in fixture.payloads().items():p.require((output/'recovered'/name).read_bytes()==data,'harmless fixture bytes mismatch')
  evidence.update(passed=True,stage='exact-harmless-fixture-verified',payload_sha256=fixture.pins()['candidate_sha256'])
 except Exception as error:
  # Do not retain arbitrary exceptions containing URLs, credentials or user paths.
  evidence.update(stage='failed-'+evidence['stage'],error_type=type(error).__name__)
 finally:
  try:cleanup(state_path);evidence['ephemeral_home_removed']=True
  except Exception:evidence.update(passed=False,ephemeral_home_removed=False,cleanup_failed=True)
  store(output/'fixture-evidence.json',evidence)
 return evidence

def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
 prepare_p=sub.add_parser('prepare');prepare_p.add_argument('--binding',type=Path,required=True);prepare_p.add_argument('--public-root',type=Path,required=True)
 receive_p=sub.add_parser('receive');receive_p.add_argument('--output',type=Path,required=True);receive_p.add_argument('--token-env',required=True)
 sub.add_parser('cleanup')
 decrypt_p=sub.add_parser('_decrypt',help=argparse.SUPPRESS);decrypt_p.add_argument('--encrypted',type=Path,required=True);decrypt_p.add_argument('--sha256',required=True);decrypt_p.add_argument('--output',type=Path,required=True)
 for child in sub.choices.values():child.add_argument('--state',type=Path,required=True)
 args=parser.parse_args()
 try:
  if args.action=='prepare':result=prepare(p.read_metadata(p.regular(args.binding)),args.state,args.public_root)
  elif args.action=='cleanup':cleanup(args.state);result={'ephemeral_home_removed':True,'native_executed':False}
  elif args.action=='_decrypt':
   state,home=check_state(args.state);p.require(all(state['request']['binding'][k]==v for k,v in fixture.pins().items()),'fixture pins')
   p.require(p.regular(args.encrypted).stat().st_size<=FIXTURE_LIMIT,'fixture ciphertext bound')
   spec=importlib.util.spec_from_file_location('fixture_retention',RETENTION);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   module.LIMIT=FIXTURE_LIMIT;module.MAX_FILES=4
   result=module.decrypt(args.encrypted,args.sha256,home,state['request']['fingerprint'],args.output)
  else:
   token=consume_token(args.token_env);client=g.Client(token);del token
   result=receive(args.state,args.output,client)
  print(json.dumps(result,sort_keys=True));return 0 if result.get('passed',True) else 1
 except Exception:
  print('Harmless fixture harness failed; no credentials or raw error emitted.',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
