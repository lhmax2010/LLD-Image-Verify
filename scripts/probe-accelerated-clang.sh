#!/usr/bin/env bash
# Inspect the host Clang and linker packed in a Tizen ARM clang-accel RPM.
set -euo pipefail
rpm_file=$(realpath "$1")
arch=$2
out=$(realpath -m "$3")
case "$arch" in
    aarch64) triple=aarch64-tizen-linux-gnu ;;
    armv7l) triple=armv7l-tizen-linux-gnueabi ;;
    *) printf 'Unknown architecture %s\n' "$arch" >&2; exit 2 ;;
esac
mkdir -p "$out"
cd "$out"
rpm2cpio "$rpm_file" | cpio -idm --quiet --no-absolute-filenames \
    './emul/usr/bin/clang-22' './emul/usr/bin/ld.lld' \
    './emul/usr/bin/lld' './emul/usr/lib*/libLLVM*' './emul/usr/lib*/libclang-cpp*'
bin="$out/emul/usr/bin"
libraries="$out/emul/usr/lib64:$out/emul/usr/lib"
sha256sum "$rpm_file" "$bin/clang-22"
readelf -l "$bin/clang-22" | sed -n '/interpreter/p'
for flag in default no-config force-lld; do
    options=()
    case "$flag" in
        no-config) options=(--no-default-config) ;;
        force-lld) options=(--no-default-config -fuse-ld=lld) ;;
    esac
    printf 'Driver probe %s\n' "$flag"
    /lib64/ld-linux-x86-64.so.2 --argv0 "$bin/clang-22" --library-path "$libraries" \
        "$bin/clang-22" -B"$bin" "${options[@]}" -### --target="$triple" -nostdlib -shared -x c /dev/null
done
