#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")" && pwd)
record="$root/flapart-install.json"
[[ "$(/usr/bin/plutil -extract product raw -o - "$record")" == 'Flapart Studio' && "$(/usr/bin/plutil -extract profileNamespace raw -o - "$record")" == flapart-native ]] || { echo 'Installation record is invalid.' >&2; exit 1; }
release=$(/usr/bin/plutil -extract release raw -o - "$record")
[[ "$release" =~ ^[A-Za-z0-9.-]+$ && "$release" != *..* ]] || exit 1
app="$root/releases/$release/Flapart Studio.app"
[[ -d "$app" && ! -L "$app" ]] || { echo 'The native application is missing.' >&2; exit 1; }
# Honor native macOS security policy; do not strip signatures or quarantine flags.
signature=$(/usr/bin/plutil -extract signature raw -o - "$record")
if [[ "$signature" != unsigned ]] || /usr/bin/codesign -d "$app" >/dev/null 2>&1; then /usr/bin/codesign --verify --deep --strict "$app"; fi
if ! /usr/sbin/spctl --assess --type execute "$app"; then
 echo 'macOS may ask you to review this developer build. After trying to open it, use the per-app Open Anyway option in Privacy & Security only if you trust it.'
 echo 'https://support.apple.com/en-ie/102445'
fi
export FLAPART_NATIVE=1
# Explicit disposable QA launch: normal user invocations retain the original path.
if [[ "${1:-}" == --flapart-qa-architecture ]]; then
 [[ "${FLAPART_QA_EXPECT_COMPILED:-}" == 1 && -n "${FLAPART_QA_OUTPUT:-}" && "$#" == 2 ]] || { echo 'QA launch needs an explicit probe output and architecture.' >&2; exit 1; }
 case "$2" in arm64|x86_64) ;; *) echo 'Unsupported QA architecture.' >&2; exit 1;; esac
 exec /usr/bin/open -n -W --arch "$2" -a "$app"
fi
exec /usr/bin/open -a "$app" --args "$@"
