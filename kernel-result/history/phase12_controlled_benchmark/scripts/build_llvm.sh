#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
group=${1:?A or B}
case "$group" in A|B) ;; *) exit 2;; esac
dir="$PWD/work/$group/home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0"
prepared=../kernel_lld_verification_20261125/evidence/source
mkdir -p "$dir/kernel" evidence/build
if [[ -e "$dir/kernel/kdbus/kdbus.o" ]]; then
   echo "Experimental group $group already has build outputs. Use an independent workspace for a repeat." >&2
   exit 2
fi
cp -a "$prepared/new/provider-rpm/usr/src/linux-tizen-modules-source/." "$dir/kernel/"
cmp "$prepared/new/Makefile" "$dir/kernel/Makefile"
if [[ "$group" == A ]]; then cp "$prepared/old/Makefile" "$dir/kernel/Makefile"; fi
cat > "$dir/phase12-entry.sh" <<'ENTRY'
set -eu
export AR=llvm-ar RANLIB=llvm-ranlib
export CC=armv7l-tizen-linux-gnueabi-clang CXX=armv7l-tizen-linux-gnueabi-clang++
export MAKEFLAGS='-j1 -k' V=1
export LOGGER_MAIN_BUFFER_SIZE=256 LOGGER_EVENTS_BUFFER_SIZE=256
export LOGGER_RADIO_BUFFER_SIZE=256 LOGGER_SYSTEM_BUFFER_SIZE=256
export TIZEN_INFORM_PATH=/mnt/inform/reboot-param.bin
export BUILD_dm_bow=m BUILD_extcon_usb_fixed=m BUILD_inform_reboot=m
export BUILD_kdbus=m BUILD_logger=m BUILD_proc_tsm=m BUILD_zlogger=m
export THREAD_GROUP_CPUTIME_SUPPORT=1 LLVM=1
sdk=/boot/kernel/devel/kernel-devel-arm-rpi4
find kernel -name Makefile -exec sed -i 's/-Wno-error=missing-attributes//g' {} \;
env | sort
find kernel -type f -print0 | sort -z | xargs -0 sha256sum
make -C kernel clean KERNELDIR="$sdk"
make -C kernel KERNELDIR="$sdk"
make -C kernel modules_install KERNELDIR="$sdk" INSTALL_MOD_STRIP=1 INSTALL_MOD_DIR=extra
ENTRY
cpu=${PHASE12_BUILD_CPU:-4}
taskset -c "$cpu" strace -qq -ff -v -s 65535 -e trace=execve,execveat,exit_group -o "evidence/build/$group.exec" \
    bash scripts/tizen_run.sh "$group" /bin/bash /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/phase12-entry.sh
