#!/usr/bin/env bash
# Collect read-only evidence from one already booted Tizen device.
set -euo pipefail
if (( $# < 1 || $# > 2 )); then
    echo "Usage: $0 DEVICE_SERIAL [OUTPUT_DIRECTORY]" >&2
    exit 2
fi
serial=$1
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname -- "$here")
mkdir -p "$root/results"
out=${2:-${AUDIT_RESULTS:-$(mktemp -d "$root/results/$(TZ=America/Los_Angeles date +%F)-device.XXXXXX")}}
mkdir -p "$out"
sdb devices > "$out/devices.txt"
if ! awk -v serial="$serial" '$1 == serial && $2 == "device" {found=1} END {exit !found}' "$out/devices.txt"; then
    echo "Device $serial is not available in sdb devices." >&2
    exit 2
fi
sdb -s "$serial" shell '
    uname -a
    cat /etc/os-release
    rpm -q deviced libdeviced wrtjs libsolv app-installers
    for file in /usr/bin/deviced /usr/sbin/deviced-request-shutdown /usr/bin/wrt-loader; do
        if [ -f "$file" ]; then sha256sum "$file"; fi
    done
    systemctl status --no-pager deviced.service
    journalctl -b -u deviced.service -n 80 --no-pager
' > "$out/boot-and-deviced.txt" 2>&1
printf 'Saved %s and %s\n' "$out/devices.txt" "$out/boot-and-deviced.txt"
