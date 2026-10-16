"""Disposable certificate generation independent of a host OpenSSL config.

This affects the fixture CLI only, never the Python or Qt verification contexts.
"""
import os
from pathlib import Path
import subprocess

CONFIG = '[req]\ndistinguished_name = qa_dn\n[qa_dn]\n'

def command(openssl, root, *args):
    root = Path(root).resolve()
    config = root / 'openssl-fixture.cnf'
    if config.exists():
        if config.is_symlink() or config.read_text() != CONFIG:
            raise ValueError('Unexpected fixture configuration')
    else:
        config.write_text(CONFIG)
    env = dict(os.environ, OPENSSL_CONF=str(config))
    result = subprocess.run([str(openssl), *map(str, args)], cwd=root,
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    if result.returncode:
        diagnostic = result.stderr.decode('utf-8', errors='replace')[-4096:]
        raise RuntimeError('OpenSSL fixture ' + str(args[0]) + ' failed (' +
                           str(result.returncode) + '): ' + diagnostic)
