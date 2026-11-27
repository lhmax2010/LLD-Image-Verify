# Kernel owner change justification · LLD-KERNEL-001

Phase 11 engineering acceptance is **PASS** and the engineering issue is **CLOSED** by PM decision. The fix is commit `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` in `platform/kernel/linux-tizen-modules-source`. Phase 11 verified the commit in QB `20261125.130358` for the Raspberry Pi 4 ARMv7l non-RT target, kernel release `6.12.80-arm-rpi4-v7l`. Product merge readiness remains **PENDING**. [PM decision](PM_PHASE11_FINAL_ACCEPTANCE.md) · [Source inclusion](../kernel_lld_verification_20261125/11B_PATCH_INCLUSION_REPORT.md)

## Why remove the assignment

The external module Makefile assigned `LD = ${CROSS_COMPILE}ld`. That file-level assignment could replace the exported linker selected by Kbuild when the external Makefile was evaluated, allowing the relocatable composite `kdbus.o` link to resolve to GNU `ld` in an LLVM build. Removing this single assignment lets the composite link and the final `kdbus.ko` link inherit Kbuild's toolchain choice. The change keeps GNU-prefixed linker selection in GCC configurations and respects explicit `LD` selection. The 46 passing GNU Make comparisons covered LLVM and GCC selection and both explicit linker choices. The real GCC/BFD build remains pending. [Source diff](../kernel_lld_verification_20261125/11B_SOURCE_DIFF.patch) · [Makefile comparisons](../kernel_lld_verification_20261125/11E_BEFORE_AFTER_REPRODUCTION.md)

## What the QB verified

The published manifest, source RPM and packaged source matched the fix. The observed job enabled `LLVM=1`. Its matching Kbuild selected and exported `ld.lld`. Both the composite link and the final module link were traced independently through their Kbuild rules, matching the successful job log and the released module RPM. Both were verified at **E3** as LLVM LLD 22.1.8. Under the observed configuration the original override was removed and no other plausible GNU BFD path was identified. The historical executable path, actual arguments and successful execution trace remain unavailable, so strict acceptance is **CONDITIONAL_PASS**. [Build chain](../kernel_lld_verification_20261125/11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md) · [Direct evidence assessment](../kernel_lld_verification_20261125/11C_INTERMEDIATE_DIRECT_EVIDENCE.md)

## Size and static ABI

| `kdbus.ko` measurement | Old QB (bytes) | New QB (bytes) | Change |
| --- | ---: | ---: | ---: |
| File | 162,584 | 161,292 | −1,292 (−0.79%) |
| `.symtab` | 14,032 | 12,736 | −1,296 (−9.24%) |
| `.text` | 67,428 | 67,428 | 0 |
| `.rodata` | 1,256 | 1,256 | 0 |
| `.data` | 52 | 52 | 0 |
| `.bss` | 29 | 29 | 0 |

The file-size difference consists of 81 fewer local ARM `$d` mapping symbols in `.symtab` and four extra bytes for two explicitly encoded default values in `.ARM.attributes`. The measurements compare published artifacts from different Base snapshots, toolchain package revisions and build environments. The isolated effect of the patch was not measured. Runtime memory and performance were not measured. [Binary comparison](../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md) · [QB inputs and build environment](../kernel_lld_verification_20261125/11A_PREFLIGHT.md)

Static ABI compatibility **PASS** covers the reviewed module interfaces. All 59 target kernel module ELFs parsed. All 2,972 `kdbus.ko` relocations were equivalent in the comparison, and 356 out-of-tree import CRCs in each QB matched its corresponding SDK. The other six out-of-tree modules were byte-identical. The assessed symbol interfaces, module metadata and effective ARM attributes remained compatible. Runtime verification awaits deployment of the new QB. [Static ABI evidence](../kernel_lld_verification_20261125/11F_MODULE_ABI_SUMMARY.json) · [Module coverage](../kernel_lld_verification_20261125/11G_KERNEL_LLD_REGRESSION_REPORT.md) · [Remaining test plan](PRODUCT_MERGE_REMAINING_TEST_PLAN.md)
