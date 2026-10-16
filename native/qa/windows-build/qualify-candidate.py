#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the proven Windows package gates against one explicitly pinned archive.

Diagnostic only: no publication, source-closure inference or workflow dispatch.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_layout(candidate, archive, output, temporary, installer_output):
    require(candidate.name == 'Flapart-Studio' and candidate.is_dir(), 'Expected collected Flapart-Studio directory')
    require(archive.is_file() and temporary.is_dir(), 'Missing archive or temporary root')
    require(not output.exists() and not installer_output.exists(), 'Output paths must be fresh')
    require(not candidate.is_relative_to(output) and not output.is_relative_to(candidate), 'Evidence and runtime must be separate')
    require(not archive.is_relative_to(output) and not temporary.is_relative_to(output) and not installer_output.is_relative_to(output), 'Binary payload or temporary runtime cannot enter evidence')
    require(not archive.is_relative_to(candidate) and not installer_output.is_relative_to(candidate), 'Artifact outputs cannot enter runtime')
    require(not output.is_relative_to(temporary) and not installer_output.is_relative_to(temporary), 'Durable outputs cannot enter disposable temporary root')


def check_pin(path, pin, label):
    require(isinstance(pin, str) and len(pin) == 64 and all(c in '0123456789abcdef' for c in pin) and digest(path) == pin, label + ' hash mismatch')


def stage_probe(source, target):
    require(not target.exists(), 'Probe staging must be fresh')
    files = [source / 'flapart_probe.desktop', *sorted((source / 'flapart_probe').rglob('*'))]
    require(files[0].is_file() and (source / 'flapart_probe/__init__.py').is_file(), 'Missing application probe')
    for path in files:
        if '__pycache__' in path.parts:
            continue
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(), 'Linked QA input is unsupported')
        if path.is_dir():
            continue
        require(path.is_file() and path.resolve().is_relative_to(source.resolve()), 'Invalid QA input')
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        # Read-only input media must not make disposable QA cleanup fail.
        destination.chmod(destination.stat().st_mode | stat.S_IWRITE)


def bind_relocation(proof, app, pin):
    require(proof.get('compiled_fork') is True and proof.get('relocated_package_test') is True and proof.get('original_krita_sentinels_preserved') is True, 'Application relocation gate failed')
    require('error' not in app and app.get('process_architecture') == 'x86_64', 'Application native probe failed')
    return {**proof, 'payload_sha256': pin, 'target_platform': 'windows-x86_64',
            'runtime_scope': 'relocated-package', 'native_execution': True,
            'build_environment_absent': True,
            **{key: app[key] for key in ('process_architecture', 'hardware_architecture', 'execution_mode')}}


def owned_image(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def stop_owned_processes(root):
    """Close only leftovers whose actual image belongs to this fresh QA directory."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    pids = (wintypes.DWORD * 32768)();needed = wintypes.DWORD()
    psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    require(psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed)) and needed.value < ctypes.sizeof(pids), 'Cannot enumerate QA process cleanup')
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD];kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    stopped = []
    for pid in pids[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if not pid or pid == os.getpid():continue
        handle = kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        if not handle:continue  # OS/protected processes are outside this QA lane.
        try:
            path = ctypes.create_unicode_buffer(32768);length = wintypes.DWORD(len(path))
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):continue
            if not owned_image(path.value, root):continue
            if kernel.WaitForSingleObject(handle, 0) == 0:continue
            require(kernel.TerminateProcess(handle, 1), 'Could not stop leftover QA process')
            require(kernel.WaitForSingleObject(handle, 10000) == 0, 'QA process did not stop before profile restoration')
            stopped.append({'pid': pid, 'image': path.value, 'forced_termination': True})
        finally:kernel.CloseHandle(handle)
    return stopped


@contextlib.contextmanager
def safe_profile(paths, temporary, helpers, cleanup, receipt):
    """Use the existing restoration pattern, retaining backups if child state is unknown."""
    paths = [Path(p) for p in paths]
    require(len(set(paths)) == len(paths) and len({p.name for p in paths}) == len(paths), 'Duplicate profile path')
    backup = Path(tempfile.mkdtemp(prefix='flapart-prior-profile-', dir=temporary))
    prepared = []
    try:
        for path in paths:
            saved = backup / path.name;existed = helpers.present(path)
            if existed:shutil.move(str(path), str(saved))
            prepared.append((path, saved, existed))
        yield
    finally:
        try:
            stopped = cleanup()
            if stopped:receipt.setdefault('profile_cleanup_stragglers', []).extend(stopped)
        except Exception:
            receipt.setdefault('retained_profile_backups', []).append(str(backup))
            raise RuntimeError('QA child exit cannot be verified; original profile retained at ' + str(backup))
        errors = []
        for path, saved, existed in reversed(prepared):
            try:
                helpers.remove_test_path(path)
                if existed:
                    require(helpers.present(saved), 'Original profile backup missing')
                    path.parent.mkdir(parents=True, exist_ok=True);shutil.move(str(saved), str(path))
            except (OSError, ValueError) as error:errors.append(str(error))
        if errors or any(backup.iterdir()):
            receipt.setdefault('retained_profile_backups', []).append(str(backup))
            raise RuntimeError('Profile restoration incomplete; retained backup at ' + str(backup) + '; ' + '; '.join(errors))
        backup.rmdir()
        require(not stopped, 'Late QA process required termination; gate remains failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'archive', 'baseline', 'manifest', 'installer-directory', 'installer-binary-output', 'output', 'temporary-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--archive-sha256', required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--hide-build-prefix', type=Path, action='append', required=True)
    parser.add_argument('--https-proxy')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--disposable-windows-host', action='store_true')
    args = parser.parse_args()
    require(platform.system() == 'Windows' and args.disposable_windows_host, 'Explicit disposable native Windows host required')
    require(60 <= args.timeout <= 600, 'Use a bounded application timeout between60 and600seconds')
    candidate, archive, baseline, manifest_path, installer_source, installer_binary, output, temporary = (
        getattr(args, name).resolve() for name in ('candidate', 'archive', 'baseline', 'manifest', 'installer_directory', 'installer_binary_output', 'output', 'temporary_root'))
    check_layout(candidate, archive, output, temporary, installer_binary)
    check_pin(archive, args.archive_sha256, 'Archive')
    check_pin(baseline, args.baseline_sha256, 'Baseline')
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get('sha256') == args.archive_sha256 and manifest.get('status') == 'ci-candidate' and manifest.get('platform') == 'windows-x86_64' and manifest.get('kind') == 'namespaced-compiled-fork' and manifest.get('profileNamespace') == 'flapart-native', 'Require matching private Windows candidate manifest')
    windows = Path(__file__).resolve().parent
    portable = windows.parent / 'portable'
    runtime = load('flapart_runtime_driver', windows / 'test-packaged-runtime.py')
    profiles = load('flapart_preserved_profiles', portable / 'test-relocated.py')
    provenance = load('flapart_package_provenance', portable / 'package-runtime-probe.py')
    installer = load('flapart_installer_journey', installer_source / 'ci_e2e.py')
    required = [windows / name for name in ('test-compiled.py', 'capture-startup.py', 'graphics-probe.py')]
    required += [portable / 'package-runtime-probe.py', windows.parent / 'tls-evaluation/https-validation-probe.py', windows.parent / 'tls-evaluation/tls_fixture.py']
    required += [installer_source / name for name in ('ci_e2e.py', 'FlapartInstaller.cs', 'SyneMono-Regular.ttf')]
    require(all(path.is_file() for path in required), 'Missing qualification helper inputs')
    output.mkdir(parents=True)
    result = {'passed': False, 'release_qualified': False, 'binary_published': False,
              'payload_sha256': args.archive_sha256, 'target_platform': 'windows-x86_64',
              'prefixes_restored': False, 'profiles_restored': False, 'stages': [],
              'input_hashes': {str(path): digest(path) for path in required + [Path(__file__), manifest_path, baseline]}}
    def save():
        (output / 'qualification.json').write_text(json.dumps(result, indent=2) + '\n')
    owned_root = None
    def run(name, command, env, timeout):
        check_pin(archive, args.archive_sha256, 'Archive')
        stage = {'name': name, 'completed': False};result['stages'].append(stage);save()
        started = time.monotonic()
        try:
            with (output / (name + '.log')).open('w') as log:
                process = subprocess.run(list(map(str, command)), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            stage.update(completed=True, returncode=process.returncode)
            require(process.returncode == 0, name + ' failed; inspect retained log and child receipts')
            check_pin(archive, args.archive_sha256, 'Archive')
        finally:
            try:
                if owned_root is not None:
                    stage['leftover_qa_processes'] = stop_owned_processes(owned_root)
                    require(not stage['leftover_qa_processes'], 'Leftover QA processes required termination; gate remains failed')
            finally:
                stage['elapsed_seconds'] = round(time.monotonic() - started, 3);save()
    original = runtime.identities(args.hide_build_prefix)
    local = installer.knownfolder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091')
    roaming = installer.knownfolder('3EB685DB-65F9-4CF6-A03A-E3EF65729F3D')
    profile_paths = [local / 'flapartnativerc', local / 'flapartnativedisplayrc', local / 'flapartnativeshortcutsrc', roaming / 'flapart-native']
    before = installer.snapshot(profile_paths)
    (output / 'profile-before.json').write_text(json.dumps(before, indent=2) + '\n')
    save()
    try:
        runtime.regular_tree(candidate)
        with tempfile.TemporaryDirectory(prefix='Flapart candidate gates ', dir=temporary) as temp:
            work = Path(temp);owned_root = work;root = work / 'runtime';root.mkdir();copy = root / candidate.name
            shutil.copytree(candidate, copy)
            inventory = provenance.archive_inventory(archive, root)
            require({name for _, name in runtime.regular_tree(copy)} == set(inventory), 'Candidate contains files absent from archive')
            staged_probe = work / 'probe';stage_probe(portable, staged_probe)
            staged_installer = work / 'installer';staged_installer.mkdir()
            for name in ('ci_e2e.py', 'FlapartInstaller.cs', 'SyneMono-Regular.ttf'):
                target = staged_installer / name
                shutil.copy2(installer_source / name, target)
                target.chmod(target.stat().st_mode | stat.S_IWRITE)
            system = next((value for key, value in os.environ.items() if key.upper() == 'SYSTEMROOT'), None)
            require(system, 'Missing Windows system directory')
            csc = Path(system) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
            require(csc.is_file(), 'Native .NET Framework C# compiler unavailable')
            installer_binary.parent.mkdir(parents=True, exist_ok=True)
            command = [csc, '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/out:' + str(installer_binary)]
            command += ['/reference:' + name for name in ('System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Web.Extensions.dll', 'System.IO.Compression.dll')]
            command += [staged_installer / 'FlapartInstaller.cs']
            env = dict(os.environ, CI='true', RUNNER_TEMP=str(temporary))
            run('build-installer', command, env, 180)
            shutil.copy2(installer_binary, staged_installer / 'Install Flapart.exe')
            result['installer_binary_sha256'] = digest(installer_binary);save()
            protected = [work, candidate, output, archive, baseline, manifest_path, windows, portable, installer_source, installer_binary, Path(sys.executable)]
            with runtime.hidden_prefixes(args.hide_build_prefix, protected):
                clean = runtime.clean_environment(copy);clean.update(CI='true', RUNNER_TEMP=str(temporary));clean.pop('QT_QPA_PLATFORM', None)
                with safe_profile(profile_paths, temporary, profiles, lambda: stop_owned_processes(work), result):
                    run('application', [sys.executable, windows / 'test-compiled.py', '--packaged', '--prefix', copy, '--probe', staged_probe, '--output', output / 'application', '--timeout', str(args.timeout)], clean, args.timeout + 60)
                proof = json.loads((output / 'application/qualification.json').read_text())
                app = json.loads((output / 'application/result.json').read_text())
                (output / 'relocation.json').write_text(json.dumps(bind_relocation(proof, app, args.archive_sha256), indent=2) + '\n')
                python = copy / 'python/python.exe'
                run('graphics', [python, '-I', '-B', windows / 'graphics-probe.py', '--runtime-root', root, '--archive', archive, '--runtime-scope', 'relocated-package', '--output', output / 'graphics.json'], clean, 120)
                command = [python, '-I', '-B', portable / 'package-runtime-probe.py', '--archive', archive, '--runtime-root', root,
                           '--baseline-extension-manifest', baseline, '--baseline-extension-sha256', args.baseline_sha256,
                           '--openssl', copy / 'bin/openssl.exe', '--output', output / 'runtime', '--runtime-scope', 'relocated-package', '--target-platform', 'windows-x86_64']
                if args.https_proxy:command += ['--https-proxy', args.https_proxy]
                run('embedded-runtime', command, runtime.clean_environment(copy), 360)
                provenance.archive_inventory(archive, root)
                installer_temporary = work / 'installed-runtime';installer_temporary.mkdir()
                installer_env = dict(clean, RUNNER_TEMP=str(installer_temporary))
                with safe_profile(profile_paths, temporary, profiles, lambda: stop_owned_processes(work), result):
                    command = [sys.executable, staged_installer / 'ci_e2e.py', '--archive', archive, '--archive-sha256', args.archive_sha256,
                               '--manifest', manifest_path, '--probe', staged_probe, '--output', output / 'installer', '--architecture', 'x86_64', '--disposable-native-host', '--timeout', str(args.timeout)]
                    run('installer', command, installer_env, args.timeout * 2 + 900)
            require(runtime.identities(args.hide_build_prefix) == original, 'Build prefixes not restored')
            require(installer.snapshot(profile_paths) == before, 'Original Flapart profile changed')
            check_pin(archive, args.archive_sha256, 'Archive')
        result['passed'] = True
    except Exception as error:
        result['passed'] = False
        result['error'] = str(error)
        raise
    finally:
        try:result['prefixes_restored'] = runtime.identities(args.hide_build_prefix) == original
        except OSError:pass
        try:
            after = installer.snapshot(profile_paths)
            (output / 'profile-after.json').write_text(json.dumps(after, indent=2) + '\n')
            result['profiles_restored'] = after == before
        except OSError:pass
        save()
    print('Pinned Windows candidate gates passed. Source closure and publication remain separate.')


if __name__ == '__main__':
    main()
