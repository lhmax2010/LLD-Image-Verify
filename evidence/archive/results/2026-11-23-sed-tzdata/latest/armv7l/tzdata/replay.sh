#!/bin/bash
set -eux
umask 022
export AR=llvm-ar RANLIB=llvm-ranlib
/bin/make -j2 CC=armv7l-tizen-linux-gnueabi-clang TZDIR=/usr/share/zoneinfo 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"'"'"/etc/localtime"'"'"' -fPIE' 'LDFLAGS= -pie ' AWK=awk KSHELL=/bin/sh zdump zic
mkdir bfd
armv7l-tizen-linux-gnueabi-clang -fuse-ld=bfd -Wl,-v -o zdump -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zdump.o localtime.o strftime.o
mv zdump bfd/
(cd bfd && eu-strip --remove-comment -f zdump.debug zdump)
armv7l-tizen-linux-gnueabi-clang -fuse-ld=bfd -Wl,-v -o zic -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zic.o
mv zic bfd/
(cd bfd && eu-strip --remove-comment -f zic.debug zic)
mkdir lld
armv7l-tizen-linux-gnueabi-clang -fuse-ld=lld -Wl,-v -o zdump -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zdump.o localtime.o strftime.o
mv zdump lld/
(cd lld && eu-strip --remove-comment -f zdump.debug zdump)
armv7l-tizen-linux-gnueabi-clang -fuse-ld=lld -Wl,-v -o zic -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -DHAVE_GETTEXT=1 -DTZDEFAULT='"/etc/localtime"' -fPIE -pie  zic.o
mv zic lld/
(cd lld && eu-strip --remove-comment -f zic.debug zic)
