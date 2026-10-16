#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib,zipfile,json,hashlib
r=pathlib.Path(__file__).resolve().parents[1]; dest=r/'dist'; dest.mkdir(exist_ok=True)
p=dest/'flapart-studio-0.1.1-krita-plugin.zip'
if p.exists():raise SystemExit('Refusing to overwrite an existing release ZIP')
with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted((r/'plugin').rglob('*')):
  if f.is_file() and '__pycache__' not in f.parts:
   z.write(f,f.relative_to(r/'plugin'))
 z.write(r/'COPYING','flapart/COPYING')
 z.write(r/'README.md','flapart/README.md')
meta={'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'kind':'Krita Python plugin source','license':'GPL-3.0-or-later','native_application_installer':False}
(dest/'plugin-manifest.json').write_text(json.dumps(meta,indent=2)+'\n'); print(json.dumps(meta,indent=2))
