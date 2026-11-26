#!/usr/bin/env bash
# Build and split two identified x86_64 linker controls.
set -euo pipefail
emul=$(realpath "$1")
out=$(realpath -m "$2")
mkdir -p "$out"
cd "$out"
export TMPDIR="$out"
cat > control.c <<'C'
int audit_control(void) { return 42; }
C
gcc -g -fPIC -c control.c -o control.o
runtime_loader=/lib64/ld-linux-x86-64.so.2
lld="$emul/usr/bin/ld.lld"
run_lld=("$runtime_loader" --argv0 "$lld" --library-path "$emul/usr/lib64:$emul/usr/lib" "$lld")
ld.bfd --version > bfd-version.txt
"${run_lld[@]}" --version > lld-version.txt
ld.bfd -shared --build-id=sha1 -o bfd.so control.o
"${run_lld[@]}" -shared --build-id=sha1 -o lld.so control.o
for name in bfd lld; do
    objcopy --only-keep-debug "$name.so" "$name.debug"
    objcopy --strip-debug --add-gnu-debuglink="$name.debug" "$name.so"
    readelf -W -n -p .comment "$name.debug" > "$name-paired-debug.txt"
    readelf -W -S "$name.debug" >> "$name-paired-debug.txt"
    readelf -x .gnu_debuglink -n "$name.so" > "$name-runtime-pair.txt"
    sha256sum "$name.so" "$name.debug"
done
