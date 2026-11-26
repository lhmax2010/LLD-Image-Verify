#!/bin/bash
set -eux
umask 022
export AR=llvm-ar RANLIB=llvm-ranlib
export 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC'
export 'LDFLAGS= -pie'
export CC=armv7l-tizen-linux-gnueabi-clang CXX=armv7l-tizen-linux-gnueabi-clang++
./configure --build=armv7l-tizen-linux-gnueabi --host=armv7l-tizen-linux-gnueabi --program-prefix= --prefix=/usr --exec-prefix=/usr --bindir=/usr/bin --sbindir=/usr/sbin --sysconfdir=/etc --datadir=/usr/share --includedir=/usr/include --libdir=/usr/lib --libexecdir=/usr/libexec --localstatedir=/var --sharedstatedir=/usr/com --mandir=/usr/share/man --infodir=/usr/share/info --prefix=/usr --mandir=/usr/share/man --infodir=/usr/share/info --disable-nls --without-included-regex armv7l-tizen-linux
/bin/make -j2 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-generate' 'LDFLAGS= -pie -fuse-ld=bfd'
export LLVM_PROFILE_FILE=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed-%p.profraw
/bin/make -j2 check
profile_count=$(find . -maxdepth 1 -name "*.profraw" | wc -l)
printf "Training raw profiles: %s\n" "$profile_count"
llvm-profdata merge -output="$PWD/sed.profdata" ./*.profraw
sha256sum sed.profdata
/bin/make clean
/bin/make -j2 'CFLAGS=-Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata'
cd sed
mkdir bfd
armv7l-tizen-linux-gnueabi-clang -fuse-ld=bfd -Wl,-v  -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata  -pie -o sed  sed.o compile.o execute.o regexp.o fmt.o mbcs.o utils.o ../lib/libsed.a
mv sed bfd/
(cd bfd && eu-strip --remove-comment -f sed.debug sed)
mkdir lld
armv7l-tizen-linux-gnueabi-clang -fuse-ld=lld -Wl,-v  -Os -ffunction-sections -fdata-sections -fstack-protector -Wno-unused-command-line-argument -Wno-error=unused-but-set-variable -Wno-error=unused-command-line-argument  -g2 -gdwarf-4 -pipe -Wall -Wp,-D_FORTIFY_SOURCE=2 -fexceptions -Wformat -Wformat-security -fmessage-length=0 -frecord-gcc-switches -march=armv7-a -mtune=cortex-a8 -mlittle-endian -mfpu=neon -mfloat-abi=softfp -mthumb -Wp,-D__SOFTFP__ -D_FILE_OFFSET_BITS=64 -g -Wall -Wstrict-prototypes -Wpointer-arith -Wformat-security -fPIC -Wno-error=coverage-mismatch -fprofile-use=/home/abuild/rpmbuild/BUILD/sed-4.1c/sed.profdata  -pie -o sed  sed.o compile.o execute.o regexp.o fmt.o mbcs.o utils.o ../lib/libsed.a
mv sed lld/
(cd lld && eu-strip --remove-comment -f sed.debug sed)
