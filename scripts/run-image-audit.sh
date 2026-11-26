#!/usr/bin/env bash
# Audit a public Unified Toolchain snapshot and keep the result in this directory.
set -euo pipefail
if (( $# < 1 )) || [[ ! $1 =~ ^[0-9]{8}\.[0-9]{6}$ ]]; then
    echo "Usage: $0 YYYYMMDD.HHMMSS [--profile PROFILE] [--jobs 1|2] [--no-debuginfo]" >&2
    exit 2
fi
stamp=$1
shift
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname -- "$here")
snapshot="tizen-unified-toolchain_$stamp"
mkdir -p "$root/results"
out=${AUDIT_RESULTS:-$(mktemp -d "$root/results/$(TZ=America/Los_Angeles date +%F)-$stamp.XXXXXX")}
work=${AUDIT_WORK:-$(mktemp -d "${TMPDIR:-/tmp}/tizen-lld-$stamp.XXXXXX")}
mkdir -p "$out"
printf 'Result directory: %s\nScratch directory: %s\n' "$out" "$work"
status=0
python3 "$here/audit-snapshot.py" --snapshot "$snapshot" --jobs 2 --work-dir "$work" "$@" \
    |& tee "$out/image-run.log" || status=$?
python3 "$here/save-scan-evidence.py" "$work" "$out/image"
printf '%s\n' "$status" > "$out/image-exit-code.txt"
exit "$status"
