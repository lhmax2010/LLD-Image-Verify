#!/bin/bash
set -eux
umask 022
install -m 755 /usr/lib/rpm/config.guess ./build-aux/config.guess
export AR=llvm-ar RANLIB=llvm-ranlib
export 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC'
export 'LDFLAGS= -pie'
export CC=aarch64-tizen-linux-gnu-clang CXX=aarch64-tizen-linux-gnu-clang++
./configure --build=aarch64-tizen-linux-gnu --host=aarch64-tizen-linux-gnu --program-prefix= --prefix=/usr --exec-prefix=/usr --bindir=/usr/bin --sbindir=/usr/sbin --sysconfdir=/etc --datadir=/usr/share --includedir=/usr/include --libdir=/usr/lib64 --libexecdir=/usr/libexec --localstatedir=/var --sharedstatedir=/usr/com --mandir=/usr/share/man --infodir=/usr/share/info --prefix=/usr --mandir=/usr/share/man --infodir=/usr/share/info --disable-nls --without-included-regex aarch64-tizen-linux
/bin/make -j2 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-generate' 'LDFLAGS= -pie -fuse-ld=bfd'
export LLVM_PROFILE_FILE=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed-%p.profraw
/bin/make -j2 check
profile_count=$(find . -maxdepth 1 -name "*.profraw" | wc -l)
printf "Training raw profiles: %s\n" "$profile_count"
llvm-profdata merge -output="$PWD/sed.profdata" ./*.profraw
sha256sum sed.profdata
/bin/make clean
/bin/make -j2 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata'
cd sed
mkdir bfd
aarch64-tizen-linux-gnu-clang -fuse-ld=bfd -Wl,-v  -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata  -pie -o sed  sed.o compile.o execute.o regexp.o fmt.o mbcs.o utils.o ../lib/libsed.a
mv sed bfd/
(cd bfd && eu-strip --remove-comment -f sed.debug sed)
mkdir lld
aarch64-tizen-linux-gnu-clang -fuse-ld=lld -Wl,-v  -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv8-a+fp+simd+crc+crypto -mtune=cortex-a53 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata  -pie -o sed  sed.o compile.o execute.o regexp.o fmt.o mbcs.o utils.o ../lib/libsed.a
mv sed lld/
(cd lld && eu-strip --remove-comment -f sed.debug sed)
