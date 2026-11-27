#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
phase=$PWD
exec bwrap --unshare-user --uid 1000 --gid 1000 --ro-bind /usr /usr \
  --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --dev /dev --proc /proc --ro-bind /sys /sys --tmpfs /tmp \
  --bind "$phase" /phase \
  --ro-bind "$phase/work/replay/home/abuild" /home/abuild \
  --ro-bind "$phase/work/tool-overlays/emul" /emul \
  --ro-bind "$phase/work/sdk/boot" /boot \
  --clearenv --setenv LC_ALL C --setenv TZ UTC --setenv PATH /usr/bin:/bin \
  --chdir /phase -- /usr/bin/python3 -B /phase/scripts/benchmark_linkers.py "$@"
