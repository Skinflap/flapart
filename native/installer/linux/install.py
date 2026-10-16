#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install an isolated Flapart Studio using a verified official Krita download."""
import sys, os, platform

def check_runtime():
 if sys.version_info < (3, 9):
  raise SystemExit('Flapart Studio setup needs Python 3.9 or later. Update Python before installing; nothing was downloaded or installed.')
 try: libc = os.confstr('CS_GNU_LIBC_VERSION')
 except (AttributeError, OSError, ValueError): libc = None
 if libc:
  parts = libc.split()
  family, version = (parts[0], parts[1]) if len(parts) == 2 else ('', '')
 else:
  family, version = platform.libc_ver()
 try: number = tuple(int(part) for part in version.split('.'))
 except ValueError: number = ()
 if family.lower() != 'glibc' or number < (2, 35):
  raise SystemExit('Flapart Studio needs GNU glibc 2.35 or later (for example Ubuntu 22.04 or newer). This Linux system is not supported; nothing was downloaded or installed. The browser workshop remains available at https://flaptown.com/flapart/.')

check_runtime()
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile, time, urllib.request
from tls_refresh import refresh as refresh_tls
from python_refresh import refresh as refresh_python
URL='https://download.kde.org/stable/krita/5.3.4.1/krita-5.3.4.1-x86_64.AppImage'
DIGEST='e315dfb3da81cdb8bddc4bb3fcd4d9bacd0630fc7065d8ed07de758b267573f0'
p=argparse.ArgumentParser(description='Install Flapart Studio. Internet required unless an official AppImage is supplied.')
p.add_argument('--appimage-file',type=pathlib.Path,help='Use a previously downloaded official Krita 5.3.4.1 AppImage; the same checksum is required.')
p.add_argument('--tls-package-file',type=pathlib.Path,help='Use the pinned Ubuntu libssl3 security package from a previous download.')
p.add_argument('--python-package-file',type=pathlib.Path,help='Use the pinned CPython 3.13.16 refresh from a previous download.')
p.add_argument('--destination',type=pathlib.Path,default=pathlib.Path.home()/'.local/opt/flapart-studio')
p.add_argument('--no-shortcut',action='store_true',help='Skip the application-menu shortcut.')
a=p.parse_args()
if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'): p.error('This installer supports Linux x86_64 only.')
source=pathlib.Path(__file__).resolve().parent; dest=a.destination.expanduser().absolute()
if any(c in str(dest) for c in '\n\r'): p.error('Destination cannot contain line breaks.')
if dest.is_symlink(): p.error('Refusing to replace a symbolic-link destination.')
if dest.exists() and not (dest/'flapart-install.json').is_file(): p.error('Destination already exists and is not a Flapart installation; choose another folder.')
dest.parent.mkdir(parents=True,exist_ok=True)
print('Flapart Studio • full native painting, powered by Krita 5.3.4.1',flush=True)
print('This installer downloads about 399 MiB from KDE, Ubuntu and Flaptown and needs about 2 GiB free. No administrator access is used.',flush=True)
with tempfile.TemporaryDirectory(prefix='.flapart-install-',dir=dest.parent) as temp:
 temp=pathlib.Path(temp); image=temp/'krita.AppImage'; digest=hashlib.sha256(); total=0
 print('Checking the supplied AppImage…' if a.appimage_file else 'Downloading the official Krita runtime…',flush=True)
 incoming=a.appimage_file.open('rb') if a.appimage_file else urllib.request.urlopen(URL,timeout=60)
 with incoming as stream,image.open('wb') as out:
  while True:
   block=stream.read(1024*1024)
   if not block: break
   out.write(block);digest.update(block);total+=len(block)
   if total%(32*1024*1024)==0: print(f'  {total//(1024*1024)} MiB',flush=True)
 if digest.hexdigest()!=DIGEST: raise SystemExit('Download verification failed. Nothing was installed; retry from the official source.')
 image.chmod(0o700);print('Verified. Preparing your studio…',flush=True)
 with (temp/'extract.log').open('w') as log:
  subprocess.run([str(image),'--appimage-extract'],cwd=temp,stdout=log,stderr=log,check=True)
 bundle=temp/'Flapart-Studio';bundle.mkdir();shutil.move(str(temp/'squashfs-root'),bundle/'krita-runtime')
 print('Verifying the Ubuntu security-library refresh…',flush=True)
 tls_receipt=refresh_tls(bundle/'krita-runtime',a.tls_package_file)
 print('Verifying the Python security refresh…',flush=True)
 python_receipt=refresh_python(bundle/'krita-runtime',a.python_package_file)
 for filename in ('Flapart','fonts.conf','flapart.svg','COPYING'): shutil.copy2(source/filename,bundle/filename)
 plugins=bundle/'krita-runtime/usr/share/krita/pykrita';plugins.mkdir(parents=True,exist_ok=True)
 shutil.copytree(source/'plugin/flapart',plugins/'flapart',ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copy2(source/'plugin/flapart.desktop',plugins/'flapart.desktop')
 actions=bundle/'krita-runtime/usr/share/krita/actions';actions.mkdir(parents=True,exist_ok=True)
 shutil.copy2(source/'plugin/flapart.action',actions/'flapart.action')
 schemes=bundle/'krita-runtime/usr/share/color-schemes';schemes.mkdir(parents=True,exist_ok=True)
 shutil.copy2(source/'plugin/flapart/Flaptown.colors',schemes/'Flaptown.colors')
 (bundle/'Flapart').chmod(0o755)
 receipt={'product':'Flapart Studio','version':'0.1.3','engine':'Official Krita 5.3.4.1 with Ubuntu TLS and CPython security refreshes','upstream_url':URL,'upstream_sha256':DIGEST,'tls_refresh':tls_receipt,'python_refresh':python_receipt,'installed_at':int(time.time()),'distribution':'upstream runtime and Ubuntu security package downloaded directly; verified Flaptown-built CPython refresh; Flapart GPLv3 plugin and launcher'}
 (bundle/'flapart-install.json').write_text(json.dumps(receipt,indent=2)+'\n')
 backup=dest.with_name(dest.name+'.previous-'+str(time.time_ns()))
 if dest.exists(): dest.rename(backup)
 try: bundle.rename(dest)
 except BaseException:
  if backup.exists(): backup.rename(dest)
  raise
 if backup.exists(): print('Previous application retained at '+str(backup),flush=True)
if not a.no_shortcut:
 applications=pathlib.Path(os.environ.get('XDG_DATA_HOME',str(pathlib.Path.home()/'.local/share')))/'applications';applications.mkdir(parents=True,exist_ok=True)
 # Desktop Exec is not a shell. Quote all reserved characters and double percent field markers.
 escaped=str(dest/'Flapart').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
 desktop='[Desktop Entry]\nType=Application\nName=Flapart Studio\nComment=Draw and paint with the full Krita engine\nExec="'+escaped+'" %F\nIcon='+str(dest/'flapart.svg')+'\nTerminal=false\nCategories=Graphics;2DGraphics;RasterGraphics;\nStartupNotify=true\n'
 (applications/'com.flaptown.FlapartStudio.desktop').write_text(desktop)
print('\nInstalled. Open “Flapart Studio” from your applications menu, or run '+str(dest/'Flapart'),flush=True)
print('Your pictures and existing Krita settings are preserved. Account sharing opens Flaptown in your browser.',flush=True)
