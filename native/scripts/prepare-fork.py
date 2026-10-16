#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply only exact upstream-context changes in an explicitly selected clean checkout."""
import argparse, pathlib, subprocess, shutil
p=argparse.ArgumentParser(); p.add_argument('checkout',type=pathlib.Path); a=p.parse_args()
r=a.checkout.resolve(); own=pathlib.Path(__file__).resolve().parents[1]
expected='bd6e8d061d2f0388c5b10278786cf0fe62e3135f'
if subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip()!=expected:
    raise SystemExit('Refusing: checkout does not match the pinned upstream commit.')
if subprocess.check_output(['git','-C',str(r),'status','--porcelain'],text=True).strip():
    raise SystemExit('Refusing: checkout is not clean; preserve existing changes.')
f=r/'krita/main.cc'; text=f.read_text()
old='KAboutData aboutData("krita",\n                            "Krita",'
assert text.count(old)==1
text=text.replace(old,'KAboutData aboutData("krita",\n                            "Flapart Native",')
text=text.replace('aboutData.setHomepage(QStringLiteral("https://krita.org"));','aboutData.setHomepage(QStringLiteral("https://flaptown.com/flapsoft/"));')
# Retain internal application/resource identifiers for compatibility and upstream attribution.
f.write_text(text)
target=r/'plugins/python/flapart'; shutil.copytree(own/'plugin/flapart',target)
shutil.copy2(own/'plugin/flapart.desktop',target/'kritapykrita_flapart.desktop')
f=r/'plugins/python/CMakeLists.txt'; text=f.read_text(); text+='\n# Flaptown Advancements: GPLv3 native workspace overlay.\ninstall_pykrita_plugin(flapart PATTERNS "*.ttf" "*.txt" "*.svg")\n'; f.write_text(text)
print('Prepared Flapart Native source with full Krita core and Flapart Studio plugin.')

f=r/"plugins/extensions/pykrita/plugin/PythonPluginManager.cpp"
text=f.read_text(); old='pluginSettings.readEntry(QString("enable_") + plugin.moduleName(), false)'
assert text.count(old)==1
f.write_text(text.replace(old,'pluginSettings.readEntry(QString("enable_") + plugin.moduleName(), plugin.moduleName() == "flapart")'))

f=r/"plugins/python/CMakeLists.txt"
f.write_text(f.read_text()+'install(FILES flapart/Flaptown.colors DESTINATION ${KDE_INSTALL_DATADIR}/color-schemes)\n')
f=r/"libs/ui/KisMainWindow.cpp"
text=f.read_text(); assert text.count('readEntry("Theme", "Krita dark")')==2
f.write_text(text.replace('readEntry("Theme", "Krita dark")','readEntry("Theme", "Flaptown")'))

f=r/"krita/main.cc"
text=f.read_text()
old='                            KritaVersionWrapper::versionString(true),\n                            "", // TODO: "short description" needs new string exception'
new='                            QStringLiteral("0.1.0-preview (Krita ") + KritaVersionWrapper::versionString(true) + QStringLiteral(")"),\n                            "Flaptown Advancements native painting studio",'
assert old in text
f.write_text(text.replace(old,new))

# Newer PyQt releases can require a newer SIP ABI than upstream default.
f=r/"cmake/modules/SIPMacros.cmake"
text=f.read_text(); old="        set(module_tags)\n"; assert text.count(old)==1
f.write_text(text.replace(old,'        if (FLAPART_SIP_ABI_VERSION)\n            set(abi_version "${FLAPART_SIP_ABI_VERSION}")\n        endif()\n\n'+old))

# Fix a measured Qt6 startup/canvas crash at the zero-width HSV triangle apex.
f=r/"plugins/dockers/advancedcolorselector/kis_color_selector_triangle.cpp"
text=f.read_text()
old='    qreal value = (y)/qreal(triangleHeight);\n    qreal saturation = relativeX/qreal(horizontalLineLength);'
new='    // The triangle apex has a zero-length horizontal line. Avoid NaN HSV\n    // components: Qt6 rejects invalid colors and KoColor asserts on them.\n    qreal value = triangleHeight > 0 ? y / qreal(triangleHeight) : 0.0;\n    qreal saturation = horizontalLineLength > 0 ? relativeX / qreal(horizontalLineLength) : 0.0;'
assert old in text
f.write_text(text.replace(old,new))

# Independent platform settings, resources, logs and single-instance identity.
subprocess.run([__import__('sys').executable, str(own/'scripts/namespace-fork.py'), str(r)],check=True)

# Krita reapplies its UI font after Python setup; default to the bundled Flaptown
# font here while preserving explicitly selected user font preferences.
f=r/"libs/ui/KisUiFont.cpp"
text=f.read_text()
assert text.count('cfg.readEntry<bool>(useCustomSystemFontCfgName, false)') == 1
text=text.replace('cfg.readEntry<bool>(useCustomSystemFontCfgName, false)','cfg.readEntry<bool>(useCustomSystemFontCfgName, true)')
assert text.count('cfg.readEntry<QString>(customSystemFontCfgName, QString())') == 1
text=text.replace('cfg.readEntry<QString>(customSystemFontCfgName, QString())','cfg.readEntry<QString>(customSystemFontCfgName, QStringLiteral("Syne Mono"))')
assert text.count('cfg.readEntry<int>(customFontSizeCfgName, -1)') == 1
text=text.replace('cfg.readEntry<int>(customFontSizeCfgName, -1)','cfg.readEntry<int>(customFontSizeCfgName, 10)')
f.write_text(text)
