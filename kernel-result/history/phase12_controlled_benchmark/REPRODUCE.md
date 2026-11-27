# Phase 12 · 复验与证据范围

从 `phase12_controlled_benchmark/` 执行。原始 Phase 10、Phase 11 和旧 QB 归档保留在工作区相邻目录。派生文件会在重跑时改写，在独立实验副本复跑以保留现有结果。当前 Phase 12 的分组目录已含构建结果，复跑构建应使用空的 `work/A` 与 `work/B`。

## 校验证据

    python3 -B scripts/finalize_phase12.py verify
    sha256sum -c PHASE12_EVIDENCE_BUNDLE.tar.gz.sha256

JSON、CSV、日志、受控关键 ELF、顺序化冻结对象、地图、实际执行回执及脚本可从压缩包读取。大文件依赖如 SDK、工具链 RPM、构建根和重复的 ELF 全量汇编保存在原工作区。包内 `PHASE12_BUNDLE_CONTENTS.csv` 记录所包含文件的 SHA-256 和同内容归档别名。对于源 RPM 和 SDK，回执中保留各自固定发布链接和摘要。 [证据包清单](PHASE12_BUNDLE_CONTENTS.csv) · [测试范围](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## LLVM 构建和冻结输入重放

依赖 ARM binfmt/QEMU 用户环境、bubblewrap、strace、RPM 工具、GNU 工具及 Phase 11 验证的 ARMv7l SDK、Clang/LLD 和源码 RPM。脚本默认从原工作区的先前隔离 Tizen ARM 构建根读取基础工具。可通过 `PHASE12_TIZEN_ROOT` 和 `PHASE12_LIBBPF_ROOT` 指向手工恢复的等价只读环境，使用日志与工具摘要确认一致。命令记录 Phase 12 使用的旧 BFD 用户空间恢复依赖和固定新 SDK。 [构建可行性回执](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [工具摘要](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [构建 argv](evidence/build/controlled-builds.json)

    python3 -B scripts/capture.py evidence/preflight/prepare-llvm bash scripts/prepare_llvm.sh
    python3 -B scripts/capture.py evidence/preflight/prepare-btf bash scripts/prepare_btf.sh
    python3 -B scripts/capture.py evidence/build/A-build bash scripts/build_llvm.sh A
    python3 -B scripts/capture.py evidence/build/B-build bash scripts/build_llvm.sh B
    python3 -B scripts/capture.py evidence/replay/run python3 -B scripts/llvm_replay.py replay
    python3 -B scripts/capture.py evidence/packaging/control python3 -B scripts/measure_packaging.py

`build_llvm.sh` 默认 CPU 4，需要时以 `PHASE12_BUILD_CPU` 选择可用 CPU，并在 A、B 保持一致。后续重放核对两组响应文件、对象及参数，生成相同 LLD 最终链接和后处理产物。 [冻结输入](evidence/replay/frozen-inputs.json)

## 耗时和 RSS

在已重放的冻结输入上单独运行计时。默认 CPU 4–7，可以通过参数指定同一连续可用 CPU 集合。RSS 来自低占用 C 计时器的 `wait4`，strace 只用于独立的线程观察和正确性检查。 [设计](evidence/benchmark/design.json)

    cc -std=c11 -Wall -Wextra -Werror -O2 scripts/bench_timer.c -o evidence/benchmark/bench-timer
    python3 -B scripts/capture.py evidence/benchmark/native-benchmark bash scripts/benchmark_namespace.sh --pairs 40 --cpus 4,5,6,7

## ELF、真实 GCC 与运行内存

- 运行 [ARM 映射符号报告](ARM_MAPPING_SYMBOL_ANALYSIS.md) 中的 ELF 命令。报告包含历史和受控 ELF、响应文件、原始诊断及 map。
- 运行 [GCC 兼容性报告](GCC_COMPATIBILITY_REPORT.md) 中的 GCC SDK 获取及 C/D 命令。工作区的 `evidence/gcc` 保留原 RPM，轻量包保留目标对象、核对结果、工具链来源及摘要。
- [运行内存可行性](RUNTIME_MEMORY_FEASIBILITY.md) 中的脚本从已归档的精确 kernel 源码与 SDK 复核静态机制。
