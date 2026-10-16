#!/usr/bin/env python3
"""Build and assemble both Qt5 architectures privately, without SDK adoption.

Requires source prepared by prepare-macos.py and a maintained dependency SDK.
Strict universal assembly follows compilation; application/runtime qualification is separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SKIP = ('qt3d qtactiveqt qtcanvas3d qtconnectivity qtdoc qtlocation qtsensors '
        'qtserialport qtwayland qtwebchannel qtwebsockets qtwebview qtwebengine '
        'qtxmlpatterns qtcharts qtdatavis3d qtgamepad qtnetworkauth qtpurchasing '
        'qtremoteobjects qtscxml qtserialbus qtspeech qtvirtualkeyboard').split()
MODULES = ['core', 'gui', 'network', 'xml', 'quick', 'svg', 'qml', 'widgets', 'quickwidgets']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def configure_args(source, sdk, arch):
    if arch not in ('arm64', 'x86_64'):
        raise ValueError('Unsupported architecture')
    return ['arch', '-' + arch, str(source / 'configure'),
            *[flag for module in SKIP for flag in ('-skip', module)],
            '-nomake', 'examples', '-nomake', 'tools', '-no-compile-examples',
            '-no-dbus', '-no-iconv', '-no-qml-debug', '-no-libproxy', '-no-system-proxies',
            '-icu', '-no-mtdev', '-system-zlib', '-qt-pcre', '-qt-sqlite',
            '-system-libpng', '-system-libjpeg', '-system-freetype', '-system-harfbuzz',
            '-webp', 'system', '-opensource', '-confirm-license', '-openssl-linked',
            '-prefix', str(sdk), 'OPENSSL_PREFIX=' + str(sdk),
            '-I', str(sdk / 'include'), '-L', str(sdk / 'lib'),
            '-device-option', 'QMAKE_APPLE_DEVICE_ARCHS=' + arch]


def build(prepared, original_sdk, work, jobs, reviewed_text=None):
    if platform.system() != 'Darwin':
        raise RuntimeError('Native macOS required; no synthetic build success')
    prepared, original_sdk, work = (p.absolute() for p in (prepared, original_sdk, work))
    if work.exists() or work.is_symlink() or not 1 <= jobs <= 8:
        raise ValueError('Use a fresh build directory and 1-8 jobs')
    source = prepared / 'source'
    receipt = json.loads((prepared / 'preparation.json').read_text())
    if not receipt['prepared'] or receipt['security_receipt_sha256'] != '1ae18120e4d0455624167153ec7eec3040f593a9a464920337ebeb1df0f14914':
        raise ValueError('Incorrect security source preparation')
    manifest = prepared / 'prepared-source-manifest.json'
    if sha(manifest) != receipt['prepared_source_manifest_sha256']:
        raise ValueError('Prepared source manifest changed')
    expected = json.loads(manifest.read_text())
    actual = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            actual.append({'path': str(path.relative_to(source)), 'link': str(path.readlink())})
        elif path.is_file():
            actual.append({'path': str(path.relative_to(source)), 'sha256': sha(path),
                           'executable': bool(path.stat().st_mode & 0o111)})
    if actual != expected:
        raise ValueError('Prepared source files changed')
    if work.resolve().is_relative_to(original_sdk.resolve()) or work.resolve().is_relative_to(prepared.resolve()):
        raise ValueError('Build must be separate from retained inputs')
    if '3.5.9' not in (original_sdk / 'include/openssl/opensslv.h').read_text():
        raise ValueError('Maintained OpenSSL 3.5.9 SDK required')
    pc = (original_sdk / 'lib/pkgconfig/libwebp.pc').read_text().splitlines()
    if 'Version: 1.6.0' not in [line.strip() for line in pc]:
        raise ValueError('System WebP 1.6.0 SDK required')
    work.mkdir(parents=True)
    # Git exports intentionally contain no .git marker. Qt's configure otherwise
    # assumes release-tarball forwarding headers already exist. Generate those
    # with upstream syncqt in a new build-owned source copy, preserving the
    # hash-bound prepared export and avoiding synthetic Git provenance.
    copied_source = work / 'source'
    shutil.copytree(source, copied_source, symlinks=True)
    source = copied_source
    sdk = work / 'sdk'
    shutil.copytree(original_sdk, sdk, symlinks=True)
    evidence = work / 'evidence'
    evidence.mkdir()
    env = os.environ.copy()
    for key in ('QMAKEFEATURES', 'QTDIR', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH'):
        env.pop(key, None)
    env['OPENSSL_LIBS'] = '-L' + str(sdk / 'lib') + ' -lssl -lcrypto'
    env['PKG_CONFIG_LIBDIR'] = str(sdk / 'lib/pkgconfig')
    env['PKG_CONFIG_PATH'] = str(sdk / 'lib/pkgconfig')
    result = {'compiled': False, 'universal_assembled': False, 'runtime_qualified': False,
              'baseline_sdk': str(original_sdk),
              'release_qualified': False, 'stages': [], 'source_receipt_sha256': sha(prepared / 'preparation.json')}

    def run(name, argv, cwd):
        row = {'name': name, 'argv': [str(x) for x in argv], 'cwd': str(cwd)}
        result['stages'].append(row)
        (evidence / (name + '-argv.json')).write_text(json.dumps(row, indent=2) + '\n')
        with (evidence / (name + '.log')).open('x') as log:
            proc = subprocess.run(argv, cwd=cwd, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=14400)
        row['returncode'] = proc.returncode
        if proc.returncode:
            raise RuntimeError('Stage failed: ' + name + '; inspect its retained log')

    try:
        header_inputs = []
        for module_source in sorted(source.iterdir()):
            if not module_source.is_dir() or not (module_source / 'sync.profile').is_file():
                continue
            run('headers-' + module_source.name,
                ['perl', str(source / 'qtbase/bin/syncqt.pl'), '-version', '5.15.7',
                 '-outdir', str(module_source), str(module_source)], work)
            header_inputs.append({'module': module_source.name,
                                  'profile_sha256': sha(module_source / 'sync.profile')})
        if not (source / 'qtbase/include/QtCore/qglobal.h').is_file():
            raise ValueError('Qt bootstrap forwarding header generation failed')
        (evidence / 'generated-header-inputs.json').write_text(json.dumps(header_inputs, indent=2) + '\n')
        for arch in ('arm64', 'x86_64'):
            directory = work / ('build-' + arch)
            directory.mkdir()
            run(arch + '-configure', configure_args(source, sdk, arch), directory)
            # Preserve normal tool/module ordering. Early whole-tree qmake_all
            # runs before qmltyperegistrar installs qmltypes.prf and can omit
            # the generated QtQuick/QML registration translation units.
            run(arch + '-build', ['arch', '-' + arch, 'make', '-j' + str(jobs)], directory)
            registrations = []
            for component in ('qml', 'quick'):
                folder = directory / 'qtdeclarative/src' / component
                matches = list(folder.glob('*_qmltyperegistrations.cpp'))
                if len(matches) != 1 or not matches[0].stat().st_size:
                    raise ValueError('Missing generated QML registration source: ' + component)
                registrations.append({'path': str(matches[0]), 'sha256': sha(matches[0])})
            (evidence / (arch + '-qml-registration-inputs.json')).write_text(json.dumps(registrations, indent=2) + '\n')
            run(arch + '-features', [sys.executable, str(ROOT.parent / 'qt-xml-security/compare-features.py'),
                '--before', str(original_sdk / 'mkspecs'), '--after', str(directory / 'qtbase/mkspecs'),
                '--allow-host-build-mode-change',
                *[flag for module in MODULES for flag in ('--module', module)],
                '--output', str(evidence / (arch + '-features.json'))], directory)
            summary = (directory / 'qtbase/config.summary').read_text()
            if not any('Using system libwebp' in line and line.rstrip().endswith('yes') for line in summary.splitlines()):
                raise ValueError('Configuration did not select system WebP')
            stage = work / ('stage-' + arch)
            stage.mkdir()
            run(arch + '-install', ['arch', '-' + arch, 'make', '-j' + str(jobs), 'install',
                                   'INSTALL_ROOT=' + str(stage), 'DESTDIR=' + str(stage)], directory)
        result['compiled'] = True
        # INSTALL_ROOT and DESTDIR stage the absolute -prefix beneath each root.
        relative_prefix = sdk.relative_to(sdk.anchor)
        installed = {arch: work / ('stage-' + arch) / relative_prefix for arch in ('arm64', 'x86_64')}
        for arch, prefix in installed.items():
            for module in ('Core', 'Gui', 'Network', 'Xml', 'Quick', 'Svg', 'Qml', 'Widgets', 'QuickWidgets'):
                for suffix in ('', '_debug'):
                    required = prefix / ('lib/Qt' + module + '.framework/Versions/5/Qt' + module + suffix)
                    if not required.is_file():
                        raise ValueError('Missing installed framework variant: ' + str(required))
                    if module in ('Qml', 'Quick'):
                        name = arch + '-' + module.lower() + (suffix or '-release') + '-exports'
                        run(name, ['xcrun', 'nm', '-arch', arch, '-gU', str(required)], work)
                        symbols = (evidence / (name + '.log')).read_text()
                        pattern = r'\bT\s+_+Z[0-9]+qml_register_types_Qt' + module + r'v$'
                        if not re.search(pattern, symbols, re.MULTILINE):
                            raise ValueError('Required QML registration function is not exported: ' + str(required))
            for suffix in ('', '_debug'):
                if not (prefix / ('plugins/imageformats/libqwebp' + suffix + '.dylib')).is_file():
                    raise ValueError('Missing installed WebP plugin variant: ' + arch)
        command = [sys.executable, str(ROOT / 'merge-macos.py'),
                   '--arm64', str(installed['arm64']), '--x86-64', str(installed['x86_64']),
                   '--output', str(work / 'qt-universal'), '--evidence', str(evidence / 'assembly.json')]
        if reviewed_text:
            command += ['--reviewed-text', str(reviewed_text.absolute())]
        run('universal-assembly', command, work)
        result['universal_assembled'] = True
    finally:
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--maintained-sdk', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--reviewed-text', type=Path,
                        help='Exact-hash reviewed architecture metadata differences; omitted means refuse all differences')
    args = parser.parse_args()
    print(json.dumps(build(args.prepared, args.maintained_sdk, args.work, args.jobs, args.reviewed_text), indent=2))
