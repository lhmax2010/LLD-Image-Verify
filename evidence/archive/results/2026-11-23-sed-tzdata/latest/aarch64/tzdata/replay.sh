#!/bin/bash
set -eux
umask 022
export AR=llvm-ar RANLIB=llvm-ranlib
/bin/make -j2 CC=aarch64-tizen-linux-gnu-clang TZDIR=/usr/share/zoneinfo 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"'"'"/etc/localtime"'"'"' -fPIE' 'LDFLAGS= -pie ' AWK=awk KSHELL=/bin/sh zdump zic
mkdir bfd
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -o zdump -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zdump.o localtime.o strftime.o
mv zdump bfd/
(cd bfd && eu-strip --remove-comment -f zdump.debug zdump)
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -o zic -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zic.o
mv zic bfd/
(cd bfd && eu-strip --remove-comment -f zic.debug zic)
mkdir lld
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -o zdump -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zdump.o localtime.o strftime.o
mv zdump lld/
(cd lld && eu-strip --remove-comment -f zdump.debug zdump)
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -o zic -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zic.o
mv zic lld/
(cd lld && eu-strip --remove-comment -f zic.debug zic)
