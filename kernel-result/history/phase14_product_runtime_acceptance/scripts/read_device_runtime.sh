#!/usr/bin/env bash
set -euo pipefail
serial=${TARGET_SDB_SERIAL:?Set TARGET_SDB_SERIAL to an authorized device}
case "${1:-}" in
  modules)
    device_script=$(cat <<'DEVICE'
test "$(uname -r)" = '6.12.80-arm-rpi4-v7l' || exit 3
grep -qx 'BUILD_ID=tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l' /etc/os-release || exit 4
printf '[MODULE_ROOT]\n'
base=/usr/lib/modules/$(uname -r); if [ ! -d "$base" ]; then base=/lib/modules/$(uname -r); fi
printf '%s\n' "$base"
test -d "$base" || exit 5
printf '[MODULE_SHA256]\n'
cd "$base" || exit 6
find . -type f \( -name '*.ko' -o -name '*.ko.gz' -o -name '*.ko.xz' -o -name '*.ko.zst' \) -exec sha256sum {} + || exit 7
printf '[MODULE_SYMLINKS]\n'
find . -type l -name '*.ko*' -print
printf '[RPM_HEADER]\n'
rpm -q --qf '%{NAME} %{EPOCH} %{VERSION} %{RELEASE} %{ARCH} %{SOURCERPM} %{VCS}\n' arm-rpi4-linux-kernel-modules linux-tizen-modules-rpi4
printf '[RPM_HEADER_EXIT]\n%s\n' "$?"
printf '[RPM_FILE_DIGESTS]\n'
rpm -q --qf '[%{FILENAMES}\t%{FILEDIGESTS}\n]' arm-rpi4-linux-kernel-modules linux-tizen-modules-rpi4
printf '[RPM_FILE_DIGESTS_EXIT]\n%s\n' "$?"
printf '[END]\n'
DEVICE
)
    ;;
  boot)
    device_script=$(cat <<'DEVICE'
test "$(uname -r)" = '6.12.80-arm-rpi4-v7l' || exit 3
grep -qx 'BUILD_ID=tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l' /etc/os-release || exit 4
printf '[UPTIME]\n'; cat /proc/uptime
printf '[BOOT_ID]\n'; cat /proc/sys/kernel/random/boot_id
printf '[SYSTEM_STATE]\n'; systemctl is-system-running; printf 'exit=%s\n' "$?"
printf '[BOOT_TARGETS]\n'
for unit in sysinit.target basic.target multi-user.target graphical.target; do
  systemctl show "$unit" --property=Id,LoadState,ActiveState,SubState --no-pager
done
printf '[FAILED_UNITS]\n'; systemctl --failed --no-pager --plain
printf '[DMESG]\n'; dmesg; printf '[DMESG_EXIT]\n%s\n' "$?"
printf '[KERNEL_JOURNAL]\n'; journalctl -k -b --no-pager -o short-monotonic; printf '[KERNEL_JOURNAL_EXIT]\n%s\n' "$?"
printf '[END]\n'
DEVICE
)
    ;;
  kdbus)
    device_script=$(cat <<'DEVICE'
test "$(uname -r)" = '6.12.80-arm-rpi4-v7l' || exit 3
grep -qx 'BUILD_ID=tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l' /etc/os-release || exit 4
printf '[PROC_MODULES]\n'; cat /proc/modules
printf '[KDBUS_SYSFS]\n'
for item in initstate refcnt coresize initsize taint srcversion; do
  name=/sys/module/kdbus/$item
  if [ -r "$name" ]; then printf '%s=' "$item"; cat "$name"; fi
done
printf '[KDBUS_HOLDERS]\n'; if [ -d /sys/module/kdbus/holders ]; then ls -A /sys/module/kdbus/holders; fi
printf '[KDBUS_MOUNTINFO]\n'; grep -i kdbus /proc/self/mountinfo || :
printf '[KDBUS_NODES]\n'
for node in /dev/kdbus /sys/fs/kdbus /run/kdbus; do
  if [ -e "$node" ]; then ls -ld "$node"; ls -l "$node"; fi
done
printf '[KDBUS_UNITS]\n'; systemctl list-units --all --no-pager --plain 'kdbus*' || :
printf '[KDBUS_MODULE_INFO]\n'
if command -v modinfo >/dev/null 2>&1; then modinfo kdbus; printf 'exit=%s\n' "$?"; fi
printf '[TEST_CANDIDATE_PATHS]\n'
for test_file in /usr/libexec/linux-tizen-modules-source/tests/kdbus-test /usr/bin/kdbus-test; do
  if [ -f "$test_file" ]; then ls -l "$test_file"; fi
done
printf '[END]\n'
DEVICE
)
    ;;
  *) printf 'usage: %s {modules|boot|kdbus}\n' "$0" >&2; exit 2;;
esac
exec timeout 35 sdb -s "$serial" shell "$device_script"
