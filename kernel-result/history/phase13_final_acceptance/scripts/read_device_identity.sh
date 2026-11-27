#!/usr/bin/env bash
set -euo pipefail
serial=${TARGET_SDB_SERIAL:?Set TARGET_SDB_SERIAL to an authorized device}
device_script=$(cat <<'DEVICE'
printf '[UNAME]\n'; uname -a; uname -r; uname -m
printf '[PROC_VERSION]\n'; cat /proc/version
printf '[IMAGE_BUILD_ID]\n'; grep '^BUILD_ID=' /etc/os-release
printf '[DEVICE_MODEL]\n'
if [ -r /sys/firmware/devicetree/base/model ]; then tr '\000' '\n' </sys/firmware/devicetree/base/model; fi
printf '[BOOT_BANNER]\n'; dmesg | awk '/Linux version/ && !found {print; found=1}'
printf '[KERNEL_NOTES]\n'
if [ -r /sys/kernel/notes ]; then sha256sum /sys/kernel/notes; od -An -v -tx1 /sys/kernel/notes; fi
printf '[KDBUS_FILES]\n'; release=$(uname -r); base=/usr/lib/modules/$release
if [ ! -d "$base" ]; then base=/lib/modules/$release; fi
if [ -d "$base" ]; then
  find "$base" -type f \( -name 'kdbus.ko' -o -name 'kdbus.ko.gz' -o -name 'kdbus.ko.xz' -o -name 'kdbus.ko.zst' \) -exec sha256sum {} \;
fi
printf '[KDBUS_LOADED]\n'; grep '^kdbus ' /proc/modules || :
printf '[KDBUS_NOTE]\n'; p=/sys/module/kdbus/notes/.note.gnu.build-id
if [ -r "$p" ]; then sha256sum "$p"; od -An -v -tx1 "$p"; fi
printf '[END]\n'
DEVICE
)
exec timeout 20 sdb -s "$serial" shell "$device_script"
