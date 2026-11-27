#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
phase=$PWD
archive=../kernel_lld_verification_20261125
base_root=${PHASE12_TIZEN_ROOT:-/local-user/lss/LLD_Optimization/experiments/build_env_recovery/attempt-02/GBS-ROOT/local/BUILD-ROOTS/scratch.armv7l.0}
sdk_rpm="$phase/$archive/evidence/repository/rpms/arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm"
accel="$phase/$archive/evidence/build/base/rpms/clang-accel-x86_64-armv7l-0.4-2.3.armv7l.rpm"
mkdir -p work/{sdk,tool-overlays} evidence/{preflight,build}
printf '%s\n' "$base_root" > evidence/preflight/tizen-arm-root.txt
printf '%s  %s\n' 26a83164e3753d10486dac237e3a42cec58d9c3c82c6b8efa806a572579f0020 "$sdk_rpm" \
    11a6a94b835f83c47f724fdfbe77b1e307311b9cec9f5f992b2f878369e64638 "$accel" | sha256sum -c
if [[ ! -f work/sdk/.prepared ]]; then
    (cd work/sdk; rpm2cpio "$sdk_rpm" | cpio -idmu --quiet --no-absolute-filenames)
    touch work/sdk/.prepared
fi
if [[ ! -f work/tool-overlays/.prepared ]]; then
    cp -a --no-preserve=ownership "$base_root/emul" work/tool-overlays/emul
    chmod -R u+w work/tool-overlays/emul
    (cd work/tool-overlays; rpm2cpio "$accel" | cpio -idmu --quiet --no-absolute-filenames './emul/*')
    touch work/tool-overlays/.prepared
fi
sdk=work/sdk/boot/kernel/devel/kernel-devel-arm-rpi4
sha256sum "$sdk/"{.config,include/generated/autoconf.h,include/config/auto.conf,Module.symvers,scripts/module.lds,scripts/basic/fixdep,scripts/mod/modpost,tools/bpf/resolve_btfids/resolve_btfids,vmlinux} > evidence/preflight/llvm-sdk.SHA256SUMS
file "$sdk/"{scripts/basic/fixdep,scripts/mod/modpost,vmlinux}
for path in "$base_root/usr/bin/"{make,ld,pahole} work/tool-overlays/emul/usr/bin/{clang,clang-22,ld,ld.lld,llvm-strip,llvm-objdump,objdump}; do
  if [[ -f "$path" ]]; then sha256sum "$path"; file -L "$path"; fi
done
