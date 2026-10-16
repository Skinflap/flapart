#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
 printf 'Flapart requires Python 3 to install. Install Python 3 from your Linux software center, then run this installer again.\n' >&2
 exit 1
fi
exec python3 ./install.py "$@"
