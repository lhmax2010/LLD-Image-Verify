# Kernel owner final justification · LLD-KERNEL-001

The patch is an **LLVM LLD adaptation and binary size optimization** for the external Tizen modules build. The engineering issue is closed, and product merge readiness remains pending. The fixed source revision is `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` in `platform/kernel/linux-tizen-modules-source`. [PM acceptance review](PHASE13_FINAL_ACCEPTANCE_REPORT.md)

## Primary benefits

Removing `LD = ${CROSS_COMPILE}ld` lets the external Makefile respect the Kbuild linker selection, eliminates its unintended GNU BFD override and improves consistency in LLVM builds. For the controlled Raspberry Pi 4 ARMv7l non-RT build, the intermediate `kdbus.o` link moved from GNU BFD 2.43 to LLVM LLD 22.1.8. Both final module links used LLD. The executable, full command arguments, successful process exit and output identities establish E4 for those local runs. [Actual executions and artifacts](evidence/review/audit.json)

## Proven binary size benefits

| Artifact or mechanism | Verified result |
| --- | --- |
| Intermediate `kdbus.o` | 2,505,192 → 1,998,564 bytes, **−506,628 bytes (−20.22%)** |
| Final stripped `kdbus.ko` | 162,584 → 161,292 bytes, **−1,292 bytes (−0.79%)** |
| Avoided redundant ARM data mapping symbols retained in the final file | **81** |

The intermediate saving is dominated by **506,147 bytes** of repeated `.debug_str` strings. The final delta consists of 1,296 fewer symbol-table bytes and four extra bytes for explicit default ARM attributes. The frozen-input replay reproduced the final size delta and preserved ARM, Thumb and data boundaries. The corresponding locally built stripped files also matched the respective old and new published QB module bytes. The controlled file measurements establish the benefit for this case. Published debuginfo package size and device memory were outside those measurements. [Physical size attribution](INTERMEDIATE_SIZE_ATTRIBUTION.csv) · [Mapping and static checks](../phase12_controlled_benchmark/ARM_MAPPING_SYMBOL_ANALYSIS.md)

## Measured trade-offs

With the Phase 12 default thread settings, median wall time rose from **5.647 to 11.878 ms**, a **+6.231 ms** difference between the displayed medians and **+110.33%** on unrounded values. Median linker Peak RSS rose from **7,700 to 53,348 KiB**, an increase of **+45,648 KiB (+592.83%)**. PM accepted these deltas for the recorded `kdbus.o` job. They apply to the specific input, GNU BFD 2.43 and LLVM LLD 22.1.8 builds, and the recovered host environment. [Original measurement review](LINKER_THREAD_PERFORMANCE_REPORT.md)

On the equal-eight-core supplementary test, single-thread LLD improved the local default LLD wall time by 13.82%, with identical output and a higher median RSS. BFD still completed faster and used less peak RSS. This case supports testing per-workload thread tuning. Concurrent small links may compound process memory costs. The measurements leave thread startup, scheduling, allocation and ELF or debug-processing contributions unresolved. [Thread sweep and evidence boundaries](LINKER_THREAD_PERFORMANCE_REPORT.md)

## Compatibility and remaining limitations

Three real GCC/BFD C/D comparisons passed with the corresponding Tizen Unified Dev Raspberry Pi 4 ARMv7l non-RT GCC SDK. Coverage includes native ARM tool execution, the exact published accelerator and an explicit GNU cross-toolchain directory prefix. The seven installed-form modules were byte-identical within each pair. No static ABI regression was observed in the checked LLVM or GCC artifacts. [GCC coverage](../phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md) · [Binary review](../phase12_controlled_benchmark/ARM_MAPPING_SYMBOL_ANALYSIS.md)

Historical QB direct E4 execution remains unavailable. The controlled LLVM environment reused the pinned SDK and LLVM accelerator but depended on an earlier BFD accelerator and compatible libraries because several pinned Base RPMs were unavailable. Runtime memory benefit remains unmeasured. The permitted device address returned a Raspberry Pi 5 running an older AArch64 QB, so boot, module runtime and functional validation for the target new QB remain pending. [Runtime identity](RUNTIME_REGRESSION_REPORT.md) · [Product gates](PRODUCT_MERGE_GATE_MATRIX.csv)
