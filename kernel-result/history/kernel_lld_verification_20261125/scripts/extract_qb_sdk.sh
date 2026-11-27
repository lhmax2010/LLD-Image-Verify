#!/usr/bin/env bash
set -euo pipefail
sdk=evidence/repository/rpms/arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm
target=evidence/repository/sdk
p=./boot/kernel/devel/kernel-devel-arm-rpi4
mkdir -p "$target"
rpm2cpio "$sdk" | (
    cd "$target"
    cpio -idm --no-absolute-filenames --no-preserve-owner \
      "$p/.config" "$p/Module.symvers" "$p/Makefile" \
      "$p/include/generated/compile.h" "$p/include/generated/utsversion.h" "$p/include/generated/utsrelease.h" \
      "$p/include/generated/autoconf.h" "$p/include/config/auto.conf" "$p/include/config/kernel.release" \
      "$p/scripts/Makefile.build" "$p/scripts/Makefile.modfinal" "$p/scripts/Makefile.modpost" \
      "$p/scripts/Makefile.lib" "$p/scripts/Kbuild.include" "$p/scripts/link-vmlinux.sh" \
      "$p/scripts/Makefile.compiler" "$p/scripts/Makefile.clang" "$p/scripts/Makefile.llvm" \
      "$p/scripts/ld-version.sh" "$p/scripts/Makefile.vmlinux" "$p/scripts/Makefile.vmlinux_o" \
      "$p/arch/arm/Makefile" "$p/arch/arm/kernel/module.c" "$p/arch/arm/boot/compressed/Makefile" \
      "$p/arch/arm64/Makefile" "$p/scripts/module.lds"
)
find "$target" -type f -print | sort
