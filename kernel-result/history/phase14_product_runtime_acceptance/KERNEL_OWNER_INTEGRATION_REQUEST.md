# Kernel Owner integration review request · LLD-KERNEL-001

**Request** · Review the kdbus change and record your acceptance decision for the documented build performance trade-off. Product merge readiness remains **PENDING** while the authorized functional regression test is outstanding.

The change is commit `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8` in `platform/kernel/linux-tizen-modules-source`, verified in QB `20261125.130358` for Raspberry Pi 4 ARMv7l non-RT. Removing the external Makefile's `LD` override lets the intermediate module link respect Kbuild. The engineering issue is closed. This is an LLVM LLD adaptation and binary size optimization. [PM decision](PM_PHASE13_FINAL_DECISION.md)

| Controlled result | Accepted evidence |
| --- | --- |
| Intermediate object | 506,628 bytes smaller, 20.22% |
| Stripped module | 1,292 bytes smaller, 0.79% |
| ARM data mapping symbols | 81 redundant final markers avoided, required intervals preserved |
| Default linker wall time | +6.231 ms on displayed medians, +110.33% |
| Default linker Peak RSS | +45,648 KiB, +592.83% |
| GCC/BFD and static compatibility | Three real pairs on the matching RPi4 ARMv7l non-RT SDK, seven installed-form modules byte-identical in each pair |

The performance trade-off was measured for the local controlled kdbus intermediate link with GNU BFD 2.43 and LLVM LLD 22.1.8. The eight-core follow-up found a 13.82% change in LLD wall time with `--threads=1` compared with LLD default in that run, with identical output and higher median RSS. The internal causes remain unresolved. Runtime memory benefit remains unmeasured. [Final benefit archive](FINAL_LLD_BENEFIT_SUMMARY.md) · [Performance details and confidence intervals](../phase13_final_acceptance/LINKER_THREAD_PERFORMANCE_REPORT.md)

Phase 14 verified the corrected device `private-address-03:26101`, the target QB's kernel and all 59 module files. Boot and live kdbus state passed, and the readable kernel ring buffer contained no matching kdbus or module-load errors. Kernel journal access was unavailable in the current session. Functional acceptance still requires an approved case run on the correct target, with the actual results recorded. [Runtime evidence](PHASE14_RUNTIME_REGRESSION_REPORT.md)

Please confirm that the tested GCC/BFD scope covers the target product and record your acceptance of the measured build trade-off. After functional regression passes and the runtime evidence is reviewed, the gate matrix can support a product merge decision by PM. [Product merge gates](PRODUCT_MERGE_FINAL_GATE_MATRIX.csv)
