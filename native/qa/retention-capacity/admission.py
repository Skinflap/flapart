#!/usr/bin/env python3
"""Read-only measured capacity report for private candidate retention v1."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat

GIB = 1024 ** 3


def measure(paths, filesystem, reserve=2 * GIB, transport_v2=False):
    """Measure existing exact input files; never mutate, delete, or copy them."""
    seen = set()
    blobs = {}
    logical = largest = count = 0
    for value in paths:
        root = Path(value).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('Symlink input forbidden')
        if not root.exists():
            raise ValueError('Missing input: ' + str(root))
        files = sorted(root.rglob('*')) if root.is_dir() else [root]
        for path in files:
            if path.is_symlink():
                raise ValueError('Symlink input forbidden')
            if path.is_dir():
                continue
            if path in seen:
                raise ValueError('Overlapping input paths')
            seen.add(path)
            before = path.stat()
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Non-regular input forbidden')
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            after = path.stat()
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
            if stamp(before) != stamp(after):
                raise ValueError('Input changed while measuring')
            size = after.st_size
            count += 1
            logical += size
            largest = max(largest, size)
            blobs[(h.hexdigest(), size)] = size
    unique = sum(blobs.values())
    free = shutil.disk_usage(filesystem).free
    # Includes bounded generated metadata, tar headers and encryption overhead.
    # Input content can be incompressible; do not rely on compression savings.
    overhead = 32 * 1024 ** 2 + count * 2048
    if transport_v2:
        # Preparation temporarily holds two private unique copies. Encryption
        # holds the packed copy, tar and ciphertext; no compression assumed.
        overhead = 64 * 1024 ** 2 + count * 2048
        peak = max(2 * unique, 3 * unique) + overhead + reserve
    else:
        peak = unique + logical + max(logical, largest) + overhead + reserve
    return {'schema': 1, 'format': 'private-retention-v2' if transport_v2 else 'private-retention-v1',
            'input_files': count, 'logical_bytes': logical,
            'unique_blobs': len(blobs), 'unique_bytes': unique,
            'largest_file_bytes': largest, 'free_bytes': free,
            'reserve_bytes': reserve, 'estimated_additional_peak_bytes': peak,
            'input_count_with_generated_fits': count + 4 <= 16384 if transport_v2 else count + 3 <= 4096,
            'input_bytes_fit_before_generated': logical <= (32 if transport_v2 else 8) * GIB,
            'unique_storage_with_generated_fits': (len(blobs) + 4 <= 4095 and unique + overhead <= 8 * GIB) if transport_v2 else True,
            'estimated_disk_fits': free >= peak,
            'final_preparer_validation_required': True,
            'source_closure_complete': False, 'release_qualified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', action='append', required=True)
    parser.add_argument('--filesystem', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--transport-v2', action='store_true')
    args = parser.parse_args()
    result = measure(args.input, args.filesystem, transport_v2=args.transport_v2)
    with Path(args.output).open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))
    return 0 if all(result[k] for k in ('input_count_with_generated_fits', 'input_bytes_fit_before_generated', 'unique_storage_with_generated_fits', 'estimated_disk_fits')) else 2


if __name__ == '__main__':
    raise SystemExit(main())
