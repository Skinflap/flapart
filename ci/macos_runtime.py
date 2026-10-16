"""Run the real official Mac painting engine plus Flapart Studio on disposable CI."""
import hashlib,json,os,pathlib,platform,shutil,subprocess,time,urllib.request

assert os.environ.get('GITHUB_ACTIONS')=='true' and platform.system()=='Darwin', 'Disposable macOS CI only'
root=pathlib.Path(__file__).resolve().parents[1]
scratch=pathlib.Path(os.environ['RUNNER_TEMP'])/'flapart-native-qa';scratch.mkdir(exist_ok=False)
output=root/'qa-result';output.mkdir(exist_ok=True)
url='https://download.kde.org/stable/krita/5.3.4.1/krita-5.3.4.1-signed.dmg'
expected='531e261da1fd8d5c468cfcd4eebd16e9edf6ab320e89406d2875f2e43c1148de'
dmg=scratch/'krita.dmg'
with urllib.request.urlopen(url,timeout=120) as source,dmg.open('wb') as dest:shutil.copyfileobj(source,dest)
assert hashlib.sha256(dmg.read_bytes()).hexdigest()==expected, 'Upstream runtime checksum mismatch'
mount=scratch/'mount';mount.mkdir()
subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(dmg)],check=True)
try:
 apps=list(mount.glob('*.app'));assert len(apps)==1
 app=scratch/'Krita.app';subprocess.run(['ditto',str(apps[0]),str(app)],check=True)
finally:subprocess.run(['hdiutil','detach',str(mount)],check=True)
data=pathlib.Path.home()/'Library/Application Support/krita'
config=pathlib.Path.home()/'Library/Preferences/kritarc'
assert not data.exists() and not config.exists(), 'Refuse to replace an existing Krita profile'
pykrita=data/'pykrita';pykrita.mkdir(parents=True)
for src in (root/'native/plugin').iterdir():
 if src.is_dir():shutil.copytree(src,pykrita/src.name,ignore=shutil.ignore_patterns('__pycache__'))
 elif src.suffix=='.desktop':shutil.copy2(src,pykrita/src.name)
 elif src.suffix=='.action':
  (data/'actions').mkdir(exist_ok=True)
  shutil.copy2(src,data/'actions'/src.name)
for src in (root/'native/qa/portable').iterdir():
 if src.is_dir():shutil.copytree(src,pykrita/src.name,ignore=shutil.ignore_patterns('__pycache__'))
 elif src.suffix=='.desktop':shutil.copy2(src,pykrita/src.name)
config.parent.mkdir(parents=True,exist_ok=True)
config.write_text('[python]\nenable_flapart=true\nenable_flapart_probe=true\n[General]\nOpenGLRenderer=none\n')
env=os.environ.copy();env.update(FLAPART_NATIVE='1',FLAPART_QA_OUTPUT=str(output))
with (output/'native.log').open('w') as log:
 process=subprocess.Popen([str(app/'Contents/MacOS/krita'),'--nosplash'],env=env,stdout=log,stderr=subprocess.STDOUT)
 try:process.wait(timeout=180)
 except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15);raise
result=json.loads((output/'result.json').read_text())
assert 'error' not in result, result.get('error')
assert result['canvas']==[64,64] and result['round_trip']==[64,64,'Draw here']
assert result['round_trip_pixel']==[70,110,191,255]
assert process.returncode==0
assert all(result.get(key) is True for key in ('png','kra','batchmode_restored','focus_hides_panels','focus_restores_panels','action','action_reopens'))
assert result['shortcut']=='Ctrl+Alt+F'
assert result['browser_handoff']==['https://flaptown.com/flapart/?from=native&destination=profile']
assert (output/'helper-export.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
(output/'provenance.json').write_text(json.dumps({'kind':'official Mac engine plus Studio plugin; not namespaced fork','upstream_url':url,'sha256':expected,'platform':platform.platform(),'passed':True},indent=2)+'\n')
print('Native macOS canvas, PNG, KRA, pixel roundtrip and Studio controls passed.')
