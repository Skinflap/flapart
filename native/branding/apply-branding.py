#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply Flapart branding v1 after prepare-fork.py; exact-context, preflighted."""
import argparse, pathlib, shutil, hashlib, json
p=argparse.ArgumentParser();p.add_argument('source',type=pathlib.Path);a=p.parse_args()
r=a.source.resolve();assets=pathlib.Path(__file__).resolve().parent
assert 'flapartnativerc' in (r/'krita/main.cc').read_text(),'Prepare the namespaced fork first'
assert not (r/'krita/pics/branding/Flapart').exists(),'Branding already installed'
changes={}
def replace(path,old,new):
 text=changes.get(path,(r/path).read_text())
 assert text.count(old)==1,(path,old,text.count(old))
 changes[path]=text.replace(old,new)
replace('CMakeLists.txt','if ("${BRANDING}" STREQUAL "")\n    if (DEFINED KRITA_STABLE)','if ("${BRANDING}" STREQUAL "")\n    set(BRANDING "Flapart")\nendif()\nif ("${BRANDING}" STREQUAL "")\n    if (DEFINED KRITA_STABLE)')
replace('krita/CMakeLists.txt','MACOSX_BUNDLE_GUI_IDENTIFIER "org.krita"','MACOSX_BUNDLE_GUI_IDENTIFIER "com.flaptown.flapart-native"')
replace('krita/CMakeLists.txt','MACOSX_BUNDLE_BUNDLE_NAME "Krita"','MACOSX_BUNDLE_BUNDLE_NAME "Flapart Studio"')
replace('krita/versioninfo.rc.in','VALUE "CompanyName", KRITA_FOUNDATION_STR','VALUE "CompanyName", "Flaptown Advancements"')
replace('krita/versioninfo.rc.in','VALUE "FileDescription", KRITA_DESCRIPTION_STR','VALUE "FileDescription", "Flapart Studio, powered by Krita"')
replace('krita/versioninfo.rc.in','VALUE "ProductName", "Krita"','VALUE "ProductName", "Flapart Studio"')
replace('krita/data/splash/splash.qrc','<file alias="0.png">electrichearts_20250824A_kiki_4K.png</file>','<file alias="0.png">flapart-splash.png</file>')
replace('libs/ui/kis_splash_screen.cpp','i18nc("Normal splash artist name", "Tyson Tan")','i18nc("Normal splash artist name", "Flaptown Advancements")')
replace('libs/ui/KisWelcomePageWidget.cpp','https://invent.kde.org/graphics/krita','https://flaptown.com/flapsoft')
replace('libs/ui/KisWelcomePageWidget.cpp','i18n("Source Code")','i18n("Flapsoft · Source Code")')
replace('libs/ui/KisWelcomePageWidget.cpp','https://www.krita.org?" + analyticsString + "marketing-site" + "','https://flaptown.com')
replace('libs/ui/KisWelcomePageWidget.cpp','i18n("Krita Website")','i18n("Flaptown Website")')
for path,text in changes.items():(r/path).write_text(text)
shutil.copytree(assets/'Flapart',r/'krita/pics/branding/Flapart')
for name in ('banner.svg','flapart-splash.png'):shutil.copy2(assets/name,r/'krita/data/splash'/name)
print(json.dumps({'branding_version':1,'modified_files':sorted(changes),'upstream_authors_and_engine_help_retained':True},indent=2))
