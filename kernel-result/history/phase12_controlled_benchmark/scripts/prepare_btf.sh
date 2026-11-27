#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root=$PWD
older_bpf=${PHASE12_LIBBPF_ROOT:-/local-user/GBS-ROOT-TIZEN-UNIFIED-LLVM/local/BUILD-ROOTS/scratch.armv7l.0}
python3 -B scripts/get_base_inputs.py --unified --receipt unified-packages dwarves:armv7l libdwarves1:armv7l
target="$repo_root/work/tool-overlays/dwarves"
mkdir -p "$target/entry"
for package in dwarves libdwarves1; do
  (cd "$target"; rpm2cpio "$repo_root/work/rpms/$package-1.29-1.armv7l.rpm" | cpio -idmu --quiet --no-absolute-filenames)
done
cp -a "$older_bpf"/usr/lib/libbpf.so.1* "$target/usr/lib/"
cat > "$target/entry/pahole" <<'ENTRY'
#!/bin/sh
export LD_LIBRARY_PATH=/mnt/usr/lib
exec /mnt/usr/bin/pahole "$@"
ENTRY
chmod +x "$target/entry/pahole"
sha256sum "$older_bpf/usr/lib/libbpf.so.1.6.2" "$target/usr/lib/libbpf.so.1.6.2"
