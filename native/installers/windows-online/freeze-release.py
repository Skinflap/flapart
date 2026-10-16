#!/usr/bin/env python3
"""Freeze a locally shipped installer pin only after real package evidence exists.
Does not build, sign, upload, or claim tests were run. Run in release preparation.
"""
import argparse,hashlib,json,re,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
PLUGIN='7401d694e5a0b408663f87548cc856f7f39de2790bbdc9f19021e6610e5094c2'
def freeze(archive,evidence,platform,version,url,executable=None):
 if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',version):raise ValueError('Invalid version')
 parsed=urlsplit(url)
 if parsed.scheme!='https' or parsed.netloc!='accounts.flaptown.com' or not re.fullmatch(r'/flapsoft/downloads/[A-Za-z0-9][A-Za-z0-9._-]{0,150}',parsed.path) or parsed.query or parsed.fragment:raise ValueError('Use the reviewed Flapsoft HTTPS artifact location')
 with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 if evidence.get('payload_sha256')!=digest or evidence.get('platform')!=platform or evidence.get('profile_namespace')!='flapart-native':raise ValueError('Evidence must pin this exact platform and archive')
 for key in ('profile_isolation_verified','ordinary_krita_unchanged','native_canvas_png_kra_passed','runtime_dependencies_collected','source_closure_complete'):
  if evidence.get(key) is not True:raise ValueError('Missing native/package release gate: '+key)
 plugin=Path(__file__).with_name('studio-plugin.zip')
 if hashlib.sha256(plugin.read_bytes()).hexdigest()!=PLUGIN:raise ValueError('Frozen Studio plugin changed')
 with zipfile.ZipFile(archive) as z,zipfile.ZipFile(plugin) as expected:
  names=z.namelist()
  if len(names)>100000 or sum(i.file_size for i in z.infolist())>8*1024**3:raise ValueError('Oversized runtime')
  for name in names:
   path=PurePosixPath(name)
   if path.is_absolute() or '..' in path.parts or '\\' in name or any(ord(c)<32 for c in name):raise ValueError('Unsafe runtime path')
  for name in expected.namelist():
   suffix='/actions/flapart.action' if name=='flapart.action' else '/pykrita/'+name
   matches=[n for n in names if n.endswith(suffix)]
   if len(matches)!=1 or z.read(matches[0])!=expected.read(name):raise ValueError('Runtime does not contain exact frozen Studio file: '+name)
  if platform=='windows-x86_64':
   if not executable or executable not in names or not executable.endswith('/krita.exe'):raise ValueError('Pin the packaged native executable')
  elif platform in ('macos-x86_64','macos-arm64','macos-universal'):
   if 'Flapart Studio.app/Contents/MacOS/krita' not in names or any(not n.startswith('Flapart Studio.app/') for n in names):raise ValueError('Expected one deployable Flapart Studio app bundle')
   if evidence.get('signature') not in ('unsigned','adhoc','developer-id'):raise ValueError('Record real signature status without implying notarization')
  else:raise ValueError('Unknown platform')
 out={'status':'qualified','kind':'namespaced-compiled-fork','version':version,'platform':platform,'profileNamespace':'flapart-native','url':url,'sha256':digest,'studioPluginSha256':PLUGIN}
 if platform.startswith('macos'):out.update(app='Flapart Studio.app',signature=evidence['signature'])
 else:out['executable']=executable
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--platform',required=True);p.add_argument('--version',required=True);p.add_argument('--url',required=True);p.add_argument('--executable');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result=freeze(a.archive,json.loads(a.evidence.read_text()),a.platform,a.version,a.url,a.executable)
 if a.output.exists():raise SystemExit('Write a new frozen manifest; do not overwrite an existing released pin')
 a.output.write_text(json.dumps(result,indent=2)+'\n');print('Release pin written after exact-payload evidence checks. No upload performed.')
