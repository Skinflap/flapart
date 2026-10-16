# SPDX-License-Identifier: GPL-3.0-or-later
"""Relocate embedded-Python search paths without retaining build-prefix access."""
import ntpath

def relocated_lines(text, sdk_root):
    root=ntpath.normpath(str(sdk_root));python=ntpath.join(root,'python');rows=[]
    if not ntpath.isabs(root) or not ntpath.splitdrive(root)[0]:
        raise ValueError('SDK root must be an absolute Windows path')
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):
            continue
        if line=='import site':
            if line not in rows:rows.append(line)
            continue
        if '\x00' in line or line.startswith('import '):
            raise ValueError('Unexpected embedded Python directive')
        if ':' in ntpath.splitdrive(line)[1]:
            raise ValueError('Alternate-stream Python paths are unsupported')
        if ntpath.splitdrive(line)[0] and not ntpath.isabs(line):
            raise ValueError('Drive-relative Python path is ambiguous')
        target=ntpath.normpath(ntpath.join(python,line))
        if ntpath.commonpath([root,target]).casefold()!=root.casefold():
            raise ValueError('Embedded Python path escapes the candidate SDK')
        relative=ntpath.relpath(target,python).replace('\\','/')
        if relative not in rows:rows.append(relative)
    if 'python313.zip' not in rows or '.' not in rows:
        raise ValueError('Embedded Python standard-library paths missing')
    return rows
