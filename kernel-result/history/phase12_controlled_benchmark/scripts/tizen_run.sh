#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
phase=$PWD
base_root=$(cat evidence/preflight/tizen-arm-root.txt)
group=$1
shift
mkdir -p "work/$group/home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0"
extra=()
path=/usr/sbin:/usr/bin:/sbin:/bin
if [[ -x work/tool-overlays/dwarves/entry/pahole ]]; then
  extra+=(--ro-bind "$phase/work/tool-overlays/dwarves" /mnt)
  path=/mnt/entry:$path
fi
exec bwrap --unshare-user --uid 1000 --gid 1000 \
  --ro-bind "$base_root" / --dev /dev --proc /proc --tmpfs /tmp \
  --bind "$phase/work/$group/home" /home \
  --ro-bind "$phase/work/tool-overlays/emul" /emul \
  --ro-bind "$phase/work/sdk/boot" /boot \
  "${extra[@]}" --clearenv --setenv HOME /home/abuild --setenv LC_ALL C --setenv TZ UTC \
  --setenv PATH "$path" --setenv TMPDIR /tmp \
  --chdir /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0 -- "$@"
