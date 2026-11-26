#!/bin/bash
set -eux
make -j2 -f unix/Makefile generic 'CC=aarch64-tizen-linux-gnu-clang -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie' 'CPP=aarch64-tizen-linux-gnu-clang -E' prefix=/usr
mkdir -p bfd
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zip  zip.o zipfile.o zipup.o fileio.o util.o globals.o crypt.o ttyio.o unix.o crc32.o zbz2err.o deflate.o trees.o  
mv zip bfd/
(cd bfd && eu-strip --remove-comment -f zip.debug zip)
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipcloak  zipcloak.o zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o   crypt_.o ttyio.o 
mv zipcloak bfd/
(cd bfd && eu-strip --remove-comment -f zipcloak.debug zipcloak)
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipnote  zipnote.o  zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o  
mv zipnote bfd/
(cd bfd && eu-strip --remove-comment -f zipnote.debug zipnote)
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipsplit  zipsplit.o zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o  
mv zipsplit bfd/
(cd bfd && eu-strip --remove-comment -f zipsplit.debug zipsplit)
mkdir -p lld
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zip  zip.o zipfile.o zipup.o fileio.o util.o globals.o crypt.o ttyio.o unix.o crc32.o zbz2err.o deflate.o trees.o  
mv zip lld/
(cd lld && eu-strip --remove-comment -f zip.debug zip)
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipcloak  zipcloak.o zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o   crypt_.o ttyio.o 
mv zipcloak lld/
(cd lld && eu-strip --remove-comment -f zipcloak.debug zipcloak)
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipnote  zipnote.o  zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o  
mv zipnote lld/
(cd lld && eu-strip --remove-comment -f zipnote.debug zipnote)
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -DLARGEFILE_SOURCE -D_FILE_OFFSET_BITS=64 -fPIC -pie -o zipsplit  zipsplit.o zipfile_.o fileio_.o util_.o globals.o unix_.o crc32_.o  
mv zipsplit lld/
(cd lld && eu-strip --remove-comment -f zipsplit.debug zipsplit)
