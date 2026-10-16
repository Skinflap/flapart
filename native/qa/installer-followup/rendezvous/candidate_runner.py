"""Exact recovered-candidate admission and hosted installer adapter.
No transfer/key generation/workflow mutation. Never accepts fixture assertions as
packaging proof: verify_chain reads all actual stage blobs and exact ZIP members.
"""
import importlib.util,json,os,platform,shutil,subprocess,sys,time,zipfile
from pathlib import Path
import protocol as p

NATIVE=Path(__file__).resolve().parents[3]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
chain=load('candidate_actual_chain',NATIVE/'distribution/provenance/verify_chain.py')
transport=load('candidate_transport',NATIVE/'distribution/private-retention/transport_v2.py')


def tree_inventory(root):
 root=Path(root);p.require(root.is_absolute() and root.is_dir() and not any(x.is_symlink() for x in (root,*root.parents)),'canonical recovered root')
 invpath=p.regular(root/'inventory.json');p.require(invpath.stat().st_size<=transport.MANIFEST_LIMIT,'retention inventory bound')
 inv=transport.read(invpath,transport.MANIFEST_LIMIT);rows=transport.validate_original(inv)
 p.require(inv['candidate']=='candidate.zip','fixed candidate path')
 actual=set();physical={};logical=0
 for path in root.rglob('*'):
  p.require(not path.is_symlink(),'recovered evidence symlink')
  if path.is_dir():continue
  p.regular(path);actual.add(path.relative_to(root).as_posix());st=path.stat();physical[(st.st_dev,st.st_ino)]=st.st_size
 p.require(actual=={'inventory.json',*(row['path'] for row in rows)},'unlisted/missing recovered evidence')
 for row in rows:
  path=p.regular(root/row['path']);p.require(path.stat().st_size==row['bytes'] and p.file_digest(path)==row['sha256'],'recovered evidence bytes changed');logical+=row['bytes']
 return {'logical_bytes':logical,'physical_bytes':sum(physical.values()),'files':len(actual),'inventory_sha256':p.file_digest(invpath)}


def admit(root,request,installer_manifest,chain_manifest_sha256,ciphertext,ciphertext_sha256,now):
 """All pins MUST come from authenticated independent dispatch/operator inputs.
 root is the existing decrypted/restored retention tree; never extracts it here.
 Ciphertext hash verifies bytes only; caller still proves GPG/API authentication.
 """
 started=time.monotonic();p.check_request(request,now);b=request['binding'];root=Path(root)
 cipher=p.regular(ciphertext);p.require(0<cipher.stat().st_size<=p.LIMIT and p.file_digest(cipher)==ciphertext_sha256,'ciphertext pin/size')
 retention=tree_inventory(root)
 archive=p.regular(root/'candidate.zip');inventory=p.regular(root/'candidate-inventory.json');manifest=p.regular(installer_manifest);cm=p.regular(root/'chain-manifest.json')
 p.require(p.hexstr(chain_manifest_sha256,64) and p.file_digest(cm)==chain_manifest_sha256,'independent packaging chain pin')
 p.require(archive.stat().st_size==b['candidate_bytes'] and p.file_digest(archive)==b['candidate_sha256'],'candidate ZIP pin')
 p.require(p.file_digest(inventory)==b['inventory_sha256'] and p.file_digest(manifest)==b['manifest_sha256'],'original manifest/inventory pin')
 original=p.read_metadata(manifest)
 p.require(original.get('sha256')==b['candidate_sha256'] and original.get('platform') in ('macos-universal','macos-universal2') and original.get('kind')=='namespaced-compiled-fork' and original.get('profileNamespace')=='flapart-native' and original.get('status')=='ci-candidate','unqualified original Mac candidate manifest')
 cmobj=chain.read_json(cm)
 p.require(cmobj.get('archive')=={'path':'candidate.zip','sha256':b['candidate_sha256']} and cmobj.get('inventory')=={'path':'candidate-inventory.json','sha256':b['inventory_sha256']} and cmobj.get('tree')=='package' and cmobj.get('archive_prefix')=='Flapart Studio.app','chain exact path mapping')
 verified=chain.verify(cmobj,root)
 p.require(verified.get('chain_verified') is True and verified.get('source_closure_complete') is False and verified.get('release_qualified') is False,'chain evidence-only outcome')
 with zipfile.ZipFile(archive) as z:expanded=sum(info.file_size for info in z.infolist())
 # Installer retains old/new editions and uses a transient extraction directory.
 # Conservatively reserve three expanded copies + two ZIP copies +1GiB evidence.
 required=3*expanded+2*archive.stat().st_size+1024**3
 p.check_request(request,now+int(time.monotonic()-started))
 p.require(p.file_digest(cm)==chain_manifest_sha256 and p.file_digest(archive)==b['candidate_sha256'] and p.file_digest(inventory)==b['inventory_sha256'] and p.file_digest(manifest)==b['manifest_sha256'],'admission inputs changed')
 return {'schema':1,'admitted':True,'chain_verified':True,'native_executed':False,'source_closure_complete':False,'release_qualified':False,'request_sha256':p.digest(p.encode(request)),'chain_manifest_sha256':chain_manifest_sha256,'ciphertext_sha256':ciphertext_sha256,'candidate_sha256':b['candidate_sha256'],'retention':retention,'expanded_archive_bytes':expanded,'required_free_bytes_before_installer':required,'chain':verified}


def helper_inputs(installer,probe):
 installer=Path(installer);probe=Path(probe);result={}
 p.regular(installer/'ci_e2e.py');p.regular(probe/'flapart_probe.desktop');p.regular(probe/'flapart_probe/__init__.py')
 for path in [installer/'ci_e2e.py',*[x for pattern in ('*.command','*.ttf','*.exe') for x in installer.glob(pattern)],*[x for x in probe.rglob('*') if x.is_file() and '__pycache__' not in x.parts]]:
  p.regular(path);label=('installer/' if path.is_relative_to(installer) else 'probe/')+path.relative_to(installer if path.is_relative_to(installer) else probe).as_posix();result[label]=p.file_digest(path)
 return result


def installer_plan(root,request,manifest,installer,probe,output,helper_pins):
 p.binding(request['binding']);output=Path(output)
 p.require(output.is_absolute() and output.parent.is_dir() and not output.exists() and not any(x.is_symlink() for x in (output,*output.parents)),'fresh canonical installer evidence')
 p.require(not output.is_relative_to(Path(root)) and not Path(root).is_relative_to(output),'output must not overlap recovered chain')
 actual=helper_inputs(installer,probe);p.require(p.equal(actual,helper_pins),'independent helper pins mismatch')
 return {'argv':[sys.executable,str(Path(installer)/'ci_e2e.py'),'--archive',str(Path(root)/'candidate.zip'),'--archive-sha256',request['binding']['candidate_sha256'],'--manifest',str(manifest),'--probe',str(probe),'--architecture',request['binding']['architecture'],'--output',str(output/'installer')],'helper_hashes':actual,'native_executed':False,'release_qualified':False}


def run_installer(root,request,manifest,chain_sha,ciphertext,cipher_sha,installer,probe,output,helper_pins):
 """Explicit actual hosted-Mac entry point; not called by portable tests.
 Do not pass GitHub tokens in child environment. No re-sign/quarantine bypass.
 """
 p.require(platform.system()=='Darwin' and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('CI')=='true','actual hosted macOS required')
 p.require(os.stat('/dev/console').st_uid==os.getuid(),'active GUI console session required')
 subprocess.run(['/bin/launchctl','print','gui/'+str(os.getuid())],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
 home=Path.home();p.require(not (home/'Library/Preferences/flapartnativerc').exists() and not (home/'Library/Application Support/flapart-native').exists(),'fresh Flapart profile required')
 admission=admit(root,request,manifest,chain_sha,ciphertext,cipher_sha,int(time.time()))
 plan=installer_plan(root,request,manifest,installer,probe,output,helper_pins);output=Path(output)
 p.require(shutil.disk_usage(output.parent).free>=admission['required_free_bytes_before_installer'],'insufficient measured installer disk space')
 runner_tmp=Path(os.environ.get('RUNNER_TEMP',''));p.require(runner_tmp.is_absolute() and runner_tmp.is_dir() and runner_tmp.stat().st_dev==output.parent.stat().st_dev,'explicit runner temporary space on measured volume required')
 output.mkdir(mode=0o700);result={'schema':1,'passed':False,'native_executed':False,'source_closure_complete':False,'release_qualified':False,'admission':admission,'plan':plan}
 env={k:v for k,v in os.environ.items() if k in ('HOME','USER','LOGNAME','TMPDIR','LANG','LC_ALL','RUNNER_TEMP','__CF_USER_TEXT_ENCODING')};env.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin',GITHUB_ACTIONS='true',CI='true',PYTHONDONTWRITEBYTECODE='1')
 try:
  with (output/'driver.stdout').open('xb') as stdout,(output/'driver.stderr').open('xb') as stderr:
   completed=subprocess.run(plan['argv'],env=env,stdout=stdout,stderr=stderr,timeout=900)
  result['returncode']=completed.returncode;p.require(completed.returncode==0,'actual installer driver failed')
  receipt=chain.read_json(output/'installer/installer-e2e.json')
  required=('passed','native_execution','native_runtime_tested','native_canvas_png_kra_passed','profile_isolation_verified','ordinary_krita_unchanged','native_child_exit_observed','failed_upgrade_preserved_artwork_and_settings','successful_upgrade_preserved_artwork_and_settings','upgraded_runtime_tested','upgraded_native_child_exit_observed')
  p.require(all(receipt.get(k) is True for k in required),'missing measured installed-runtime outcomes')
  p.require(receipt.get('payload_sha256')==request['binding']['candidate_sha256'] and receipt.get('process_architecture')==request['binding']['architecture'] and receipt.get('runtime_scope')=='installed-runtime' and receipt.get('release_qualified') is False,'installer receipt binding')
  p.require(p.file_digest(Path(root)/'candidate.zip')==request['binding']['candidate_sha256'] and p.equal(helper_inputs(installer,probe),helper_pins),'candidate/helpers changed during test')
  result.update(passed=True,native_executed=True,installer_receipt_sha256=p.file_digest(output/'installer/installer-e2e.json'))
 except Exception as error:result['error_type']=type(error).__name__
 finally:(output/'candidate-installer-evidence.json').write_bytes(p.encode(result))
 return result
