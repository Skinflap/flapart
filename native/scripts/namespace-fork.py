#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Give an already prepared fork independent native settings and resource identity."""
import pathlib,sys
r=pathlib.Path(sys.argv[1]).resolve()
names={'kritarc':'flapartnativerc','kritadisplayrc':'flapartnativedisplayrc','kritashortcutsrc':'flapartnativeshortcutsrc','kritacrash.log':'flapart-native-crash.log','krita.log':'flapart-native.log','krita-sysinfo.log':'flapart-native-sysinfo.log','kritacrashlog.txt':'flapart-native-crashlog.txt'}
changed=[]
for base in ('krita','libs','plugins'):
 for f in (r/base).rglob('*'):
  if f.suffix not in ('.cc','.cpp','.h'):continue
  text=f.read_text();new=text
  for old,target in names.items():
   new=new.replace('"'+old+'"','"'+target+'"').replace('"/'+old+'"','"/'+target+'"')
  if new!=text:f.write_text(new);changed.append(str(f.relative_to(r)))
f=r/'krita/main.cc';text=f.read_text()
text=text.replace('#include <kaboutdata.h>','#include <kaboutdata.h>\n#include <KConfig>')
old='extern "C" MAIN_EXPORT int MAIN_FN(int argc, char **argv)\n{'
assert text.count(old)==1
text=text.replace(old,old+'\n    qputenv("FLAPART_NATIVE", "1");\n    // Set identity before QApplication/OpenGL probes and KConfig initialization.\n    QCoreApplication::setApplicationName(QStringLiteral("flapart-native"));\n    KConfig::setMainConfigName(QStringLiteral("flapartnativerc"));')
text=text.replace('QString key = "Krita5"','QString key = "FlapartNative0"')
assert 'KAboutData aboutData("krita",' in text
text=text.replace('KAboutData aboutData("krita",','KAboutData aboutData("flapart-native",')
text=text.replace('aboutData.setOrganizationDomain("krita.org");','aboutData.setOrganizationDomain("flaptown.com");')
old = 'app.setDesktopFileName(QStringLiteral("org.kde.krita"));'
assert text.count(old) == 1
text = text.replace(old, 'app.setDesktopFileName(QStringLiteral("com.flaptown.FlapartNative"));')
old = 'KAboutData::setApplicationData(aboutData);'
assert text.count(old) == 1
text = text.replace(old, 'aboutData.setDesktopFileName(QStringLiteral("com.flaptown.FlapartNative"));\n    ' + old)
f.write_text(text)
print('Independent Flapart native identity; explicit file namespaces:',len(changed))
