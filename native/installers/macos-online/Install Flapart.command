#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Candidate only: release.json must be frozen after native packaging qualification.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
manifest="$source_dir/release.json"
read_value() { /usr/bin/plutil -extract "$1" raw -o - "$manifest"; }
[[ "$(uname -s)" == Darwin ]] || { echo 'This installer is for macOS.' >&2; exit 1; }
if [[ "$(read_value status)" != qualified || "$(read_value kind)" != namespaced-compiled-fork || "$(read_value profileNamespace)" != flapart-native ]]; then
 echo 'This installer candidate has no qualified independent Mac payload yet. Nothing was downloaded or installed.' >&2; exit 1
fi
version=$(read_value version); digest=$(read_value sha256); url=$(read_value url); app_path=$(read_value app); platform=$(read_value platform)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ && "$digest" =~ ^[a-f0-9]{64}$ ]] || { echo 'Invalid release pin.' >&2; exit 1; }
[[ "$url" == https://accounts.flaptown.com/flapsoft/downloads/* && "$url" != *'?'* && "$url" != *'#'* ]] || exit 1
[[ "$app_path" == 'Flapart Studio.app' ]] || { echo 'Unexpected native package layout.' >&2; exit 1; }
case "$platform:$(uname -m)" in macos-universal:arm64|macos-universal:x86_64|macos-x86_64:x86_64|macos-arm64:arm64) ;; *) echo 'This package is not for this Mac architecture.' >&2; exit 1;; esac
# Optional CLI arguments: an already downloaded pinned ZIP, then install folder.
archive_input=${1:-}; destination=${2:-"$HOME/Applications/Flapart Studio"}
[[ "$destination" == /* && "$destination" != *$'\n'* && "$destination" != *$'\r'* ]] || { echo 'Choose an absolute ordinary installation folder.' >&2; exit 1; }
walk="$destination"
while [[ "$walk" != / ]]; do [[ ! -L "$walk" ]] || { echo 'Linked installation folders are not supported.' >&2; exit 1; }; walk=$(dirname -- "$walk"); done
if [[ -e "$destination" ]]; then
 [[ -f "$destination/flapart-install.json" ]] && [[ "$(/usr/bin/plutil -extract product raw -o - "$destination/flapart-install.json")" == 'Flapart Studio' ]] || { echo 'That folder is not a recognized Flapart installation.' >&2; exit 1; }
fi
mkdir -p -- "$destination/releases"
lock="$destination/.install-lock"
mkdir -- "$lock" 2>/dev/null || { echo 'Another installation is running. If it was interrupted, remove the empty .install-lock folder before retrying.' >&2; exit 1; }
stage=$(mktemp -d "$destination/.staging.XXXXXXXX")
cleanup() { rm -rf -- "$stage"; rmdir -- "$lock"; }
trap cleanup EXIT
if [[ ! -f "$destination/flapart-install.json" ]]; then printf '{"product":"Flapart Studio","status":"not yet installed"}\n' > "$destination/flapart-install.json"; fi
printf '%s\n' 'Flapart Studio — installing the independent native workspace.' 'Your Krita settings and artwork are preserved. No administrator password is used.'
archive="$stage/runtime.zip"
if [[ -n "$archive_input" ]]; then cp -- "$archive_input" "$archive"; else
 /usr/bin/curl --fail --show-error --proto '=https' --tlsv1.2 --max-time 1800 --max-filesize 4294967296 --output "$archive" "$url"
fi
actual=$(/usr/bin/shasum -a 256 "$archive"); actual=${actual%% *}
[[ "$actual" == "$digest" ]] || { echo 'Download checksum failed. The current application was not changed.' >&2; exit 1; }
# Hash-pinned reviewed ZIP; disallow traversal before extracting it.
/usr/bin/unzip -Z -1 "$archive" > "$stage/entries"
while IFS= read -r entry; do
 [[ "$entry" != /* && "$entry" != *\\* && "$entry" != '..' && "$entry" != ../* && "$entry" != */../* && "$entry" != */.. ]] || { echo 'Unsafe archive path.' >&2; exit 1; }
 [[ "$entry" == "$app_path"/* || "$entry" == "$app_path/" ]] || { echo 'Unexpected content outside the application bundle.' >&2; exit 1; }
done < "$stage/entries"
mkdir "$stage/payload"
/usr/bin/ditto -x -k "$archive" "$stage/payload"
app="$stage/payload/$app_path"
[[ -d "$app" && ! -L "$app" ]] || { echo 'The application bundle is missing.' >&2; exit 1; }
# Preserve existing quarantine. curl downloads need provenance metadata; a local
# source-built archive without quarantine remains local code, not an invented download.
if ! /usr/bin/xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then
 if [[ -z "$archive_input" ]]; then
  /usr/bin/xattr -w com.apple.quarantine "0083;$(printf '%x' "$(date +%s)");Flapart Studio;" "$app"
 elif quarantine=$(/usr/bin/xattr -p com.apple.quarantine "$archive_input" 2>/dev/null); then
  /usr/bin/xattr -w com.apple.quarantine "$quarantine" "$app"
 fi
fi
# Preserve the publisher's signature and normal Gatekeeper policy. Never remove quarantine.
signature=$(read_value signature)
case "$signature" in unsigned|adhoc|developer-id) ;; *) echo "Unknown signature designation." >&2; exit 1;; esac
if /usr/bin/codesign -d --verbose=2 "$app" 2> "$stage/signature.txt"; then
 /usr/bin/codesign --verify --deep --strict "$app"
 if /usr/bin/grep -q '^Signature=adhoc' "$stage/signature.txt"; then actual_signature=adhoc
 elif /usr/bin/grep -q '^Authority=Developer ID Application:' "$stage/signature.txt"; then actual_signature=developer-id
 else echo 'Unrecognized signing identity; this release does not claim Developer ID.' >&2; exit 1; fi
 [[ "$signature" == "$actual_signature" ]] || { echo 'Signature status differs from reviewed release.' >&2; exit 1; }
else
 [[ "$signature" == unsigned ]] || { echo 'Expected application signature is absent.' >&2; exit 1; }
fi
if /usr/sbin/spctl --assess --type execute "$app" 2> "$stage/gatekeeper.txt"; then
 echo 'The app passed this Mac’s current security assessment.'
else
 echo 'This developer build may require your own per-app approval in macOS. The installer will not approve it for you.'
 echo 'After attempting to open it, review System Settings → Privacy & Security → Open Anyway, only if you trust this release.'
 echo 'Apple instructions: https://support.apple.com/en-ie/102445'
fi
release_id="$version-${digest:0:12}"
final="$destination/releases/$release_id"
[[ ! -e "$final" ]] || { echo 'This release is already installed. Open the existing Flapart launcher.' >&2; exit 1; }
mv -- "$stage/payload" "$final"
cp -- "$stage/signature.txt" "$final/signature-assessment.txt"
cp -- "$stage/gatekeeper.txt" "$final/gatekeeper-assessment.txt"
# Fixed syntax validated above; metadata contains no user path requiring shell evaluation.
printf '{"product":"Flapart Studio","version":"%s","release":"%s","sha256":"%s","profileNamespace":"flapart-native","signature":"%s","app":"Flapart Studio.app"}\n' "$version" "$release_id" "$digest" "$signature" > "$stage/receipt.json"
cp -- "$source_dir/Flapart Studio.command" "$stage/launcher.command"
chmod 755 "$stage/launcher.command"
cp -- "$destination/flapart-install.json" "$destination/flapart-install.previous.json"
mv -- "$stage/receipt.json" "$destination/flapart-install.json"
mv -- "$stage/launcher.command" "$destination/Flapart Studio.command"
printf '\n%s\n' "Installed. Open $destination/Flapart Studio.command" 'Painting and export work offline. Previous runtimes and your creations are retained.'
