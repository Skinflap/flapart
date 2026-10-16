#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render existing Flaptown vector branding and Syne Mono outlines deterministically."""
from pathlib import Path
import subprocess,json,gzip
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
r=Path(__file__).resolve().parent;native=r.parent;dest=r/'Flapart';dest.mkdir(exist_ok=True)
sigil=(native/'plugin/flapart/sigil.svg').read_text();group=sigil[sigil.index('<g '):sigil.rindex('</svg>')]
font=TTFont(native/'plugin/flapart/SyneMono-Regular.ttf');glyphs=font.getGlyphSet();cmap=font.getBestCmap();units=font['head'].unitsPerEm

def textpaths(text,x,y,size,color):
 scale=size/units;cursor=0;paths=[]
 for char in text:
  name=cmap.get(ord(char),'space');pen=SVGPathPen(glyphs);glyphs[name].draw(pen);paths.append(f'<path d="{pen.getCommands()}" transform="translate({cursor},0)"/>');cursor+=glyphs[name].width
 return f'<g fill="{color}" transform="translate({x},{y}) scale({scale},-{scale})">'+''.join(paths)+'</g>'
icon='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500"><rect width="500" height="500" rx="88" fill="#1f2128"/>'+group+'</svg>'
(dest/'flapart-icon.svg').write_text(icon)
for size in [16,22,24,32,48,64,128,256,512,1024]:subprocess.run(['rsvg-convert','-w',str(size),'-h',str(size),'-o',str(dest/f'{size}-apps-krita.png'),str(dest/'flapart-icon.svg')],check=True)
(dest/'sc-apps-krita.svgz').write_bytes(gzip.compress(sigil.encode(),mtime=0))
(dest/'CMakeLists.txt').write_text('ecm_install_icons(ICONS\n'+''.join(f'{n}-apps-krita.png\n' for n in [16,22,24,32,48,64,128,256,512,1024])+'sc-apps-krita.svgz\nDESTINATION ${KDE_INSTALL_ICONDIR})\n')
(dest/'branding.qrc').write_text('<RCC version="1.0"><qresource><file alias="krita-branding.svgz">sc-apps-krita.svgz</file></qresource></RCC>\n')
composer=dest/'krita.icon';(composer/'Assets').mkdir(parents=True,exist_ok=True);(composer/'Assets/flapart.svg').write_text(sigil)
(composer/'icon.json').write_text(json.dumps({'fill':{'solid':'srgb:0.12157,0.12941,0.15686,1.00000'},'groups':[{'name':'Flapart','layers':[{'image-name':'flapart.svg','name':'Flaptown sigil'}],'shadow':{'kind':'neutral','opacity':0.15},'specular':False}],'supported-platforms':{'squares':'shared'}},indent=2)+'\n')
# Vector outlines keep the banner's typography identical before application fonts load.
banner='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 130">'+textpaths('FLAPART',0,100,112,'#ede8e1')+'</svg>'
(r/'banner.svg').write_text(banner)
back='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#1f2128"/><rect x="1060" y="180" width="680" height="680" rx="64" fill="#292c35"/><g opacity=".35" transform="translate(1080,200) scale(1.3)">'+group+'</g><path d="M104 620 H880" stroke="#bf8b6f" stroke-width="3"/>'
back+=textpaths('Make something yours.',104,735,51,'#ede8e1')+textpaths('Draw. Paint. Keep every layer.',104,820,28,'#c2b4a5')+textpaths('Flaptown Advancements',104,930,25,'#bf8b6f')+textpaths('Powered by Krita. Free to create.',104,976,23,'#c2b4a5')+'</svg>'
(r/'splash.svg').write_text(back);subprocess.run(['rsvg-convert','-o',str(r/'flapart-splash.png'),str(r/'splash.svg')],check=True)
print('Rendered Flaptown sigil, exact Syne Mono outline banner, and native splash.')
