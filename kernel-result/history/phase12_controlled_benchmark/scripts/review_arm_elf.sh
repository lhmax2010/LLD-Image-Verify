#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tools="$PWD/work/tool-overlays/emul/usr"
loader="$tools/lib64/ld-linux-x86-64.so.2"
gnu="$loader --library-path $tools/lib64 $tools/bin/objdump"
llvm="$loader --library-path $tools/lib64 $tools/bin/llvm-objdump"
python3 -B scripts/capture.py evidence/elf/comparison-run \
  python3 -B scripts/compare_arm_elf.py --gnu-objdump "$gnu" --llvm-objdump "$llvm" "$@"
python3 -B scripts/capture.py evidence/elf/render-run python3 -B scripts/render_arm_elf_report.py
cat evidence/elf/render-run.out
