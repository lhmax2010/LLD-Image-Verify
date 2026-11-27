#!/usr/bin/env bash
# Read SOURCE/DEVEL artifacts previously verified against the pinned RPM repository.
set -euo pipefail

rpms=evidence/repository/rpms
devel="$rpms/arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm"
source_pkg="$rpms/rpi4-linux-kernel-6.12.80-0.src.rpm"
external="$rpms/linux-tizen-modules-11.0.0-0.src.rpm"
devel_prefix=./boot/kernel/devel/kernel-devel-arm-rpi4
devel_members=(
    .config Makefile include/config/auto.conf include/generated/autoconf.h
    include/generated/compile.h include/generated/utsrelease.h include/generated/utsversion.h
    scripts/Kbuild.include scripts/Makefile.modfinal scripts/Makefile.vmlinux
    scripts/ld-version.sh scripts/link-vmlinux.sh scripts/mkcompile_h
    init/Kconfig scripts/Kconfig.include scripts/Makefile.lib scripts/Makefile.vmlinux_o
    arch/arm/Makefile
    arch/arm/boot/compressed/Makefile arch/arm/configs/tizen_bcm2711_defconfig
)
devel_paths=()
for member in "${devel_members[@]}"; do
    devel_paths+=("$devel_prefix/$member")
done
python3 scripts/record.py build/devel-extract bash scripts/extract_build_evidence.sh evidence/build/devel "$devel" "${devel_paths[@]}"
python3 scripts/record.py build/source-extract bash scripts/extract_build_evidence.sh evidence/build/source "$source_pkg" linux-rpi.spec linux-rpi.manifest 0008-configs-packaging-modularize-defconfig-with-RT-and-L.patch
python3 scripts/record.py build/external-source-extract bash scripts/extract_build_evidence.sh evidence/build/external-source "$external" linux-tizen-modules.spec linux-tizen-modules.manifest
