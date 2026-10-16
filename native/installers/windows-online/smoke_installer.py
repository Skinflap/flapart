"""Real Windows installer mechanics using tiny synthetic, never-executed payloads.
This does not qualify the painting engine or final runtime archive.
"""
import hashlib,json,os,platform,shutil,subprocess,tempfile,zipfile
from pathlib import Path
assert platform.system()=='Windows' and os.environ.get('GITHUB_ACTIONS')=='true','Disposable Windows CI only'
root=Path(__file__).parent
with tempfile.TemporaryDirectory(prefix='flapart-native-installer-smoke-',dir=os.environ['RUNNER_TEMP']) as tmp:
 tmp=Path(tmp);source=tmp/'source';source.mkdir();shutil.copy2(root/'Install Flapart.exe',source/'Install Flapart.exe');dest=tmp/'install'
 manifest={'status':'qualified','kind':'namespaced-compiled-fork','platform':'windows-x86_64','profileNamespace':'flapart-native','version':'0.0.0-ci','url':'https://accounts.flaptown.com/flapsoft/downloads/SYNTHETIC-NEVER-PUBLISHED.zip','executable':'Flapart-Studio/bin/krita.exe'}
 def archive(name,files):
  path=tmp/name
  with zipfile.ZipFile(path,'w') as z:
   for entry,body in files.items():z.writestr(entry,body)
  return path
 def invoke(path,target=dest,pin=True):
  if pin:manifest['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(source/'release.json').write_text(json.dumps(manifest))
  return subprocess.run([str(source/'Install Flapart.exe'),'--quiet','--archive',str(path),'--destination',str(target),'--no-shortcut'],capture_output=True,text=True,timeout=120)
 good=archive('good.zip',{'Flapart-Studio/bin/krita.exe':b'synthetic source bytes; DO NOT EXECUTE','Flapart-Studio/notices.txt':b'test'})
 first=invoke(good);assert first.returncode==0,first.stdout+first.stderr
 receipt=dest/'flapart-install.json';before=receipt.read_bytes();previous=json.loads(before)['release']
 engine=dest/'releases'/previous/manifest['executable']
 assert not os.path.exists(str(engine)+':Zone.Identifier'),'Local unmarked build must stay unmarked'
 art=tmp/'user-art.kra';art.write_bytes(b'USER ART SENTINEL');bad=archive('corrupt.zip',{'evil':'different bytes'})
 assert invoke(bad,pin=False).returncode!=0 and receipt.read_bytes()==before and art.read_bytes()==b'USER ART SENTINEL'
 traversal=archive('traversal.zip',{'../escaped.txt':b'escape','Flapart-Studio/bin/krita.exe':b'fake'})
 assert invoke(traversal).returncode!=0 and not (tmp/'escaped.txt').exists() and receipt.read_bytes()==before
 unknown=tmp/'other-app';unknown.mkdir();(unknown/'keep.txt').write_text('preserve')
 assert invoke(good,unknown).returncode!=0 and (unknown/'keep.txt').read_text()=='preserve'
 zone='[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://example.invalid/reviewed.zip\r\n'
 with open(str(good)+':Zone.Identifier','w',newline='') as stream:stream.write(zone)
 manifest['version']='0.0.0-ci-upgrade';assert invoke(good).returncode==0
 assert (dest/'releases'/previous).exists() and json.loads(receipt.read_text())['release']!=previous and art.read_bytes()==b'USER ART SENTINEL'
 installed=dest/'releases'/json.loads(receipt.read_text())['release']/manifest['executable']
 with open(str(installed)+':Zone.Identifier','r',newline='') as stream:assert stream.read()==zone,'Archive provenance must survive installation'
 result={'native_windows_installer_executed':True,'synthetic_payload_only':True,'painting_engine_tested':False,'checks':['initial per-user install','local unmarked archive stays unmarked','marked source archive provenance retained','wrong digest refuses without active change','pinned traversal archive refused','unrecognized destination preserved','successful upgrade retains previous version and outside artwork'],'passed':True}
 (root/'native-smoke-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
