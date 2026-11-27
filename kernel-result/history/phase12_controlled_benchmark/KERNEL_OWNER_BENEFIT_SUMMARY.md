# Kernel owner benefit summary · LLD-KERNEL-001

The one-line removal of the external Makefile's `LD` override gives Kbuild control of both link stages. Phase 12 verified the change on the RPi4 ARMv7l non-RT target with the matching LLVM kernel SDK. The original composite link executed GNU BFD 2.43. The fixed composite link executed LLVM LLD 22.1.8. Both final links executed LLD. Successful execution, complete arguments, linker hashes and artifact hashes support **E4 for the local controlled runs**. Historical QB execution evidence remains at its approved level. [Build evidence](evidence/build/controlled-builds.json) · [Build matrix](CONTROLLED_BUILD_MATRIX.csv)

| Finding | Controlled result |
| --- | --- |
| Composite `kdbus.o` | 2,505,192 to 1,998,564 bytes, a reduction of 506,628 bytes |
| Unstripped and release-form `kdbus.ko` | Both stages were 1,292 bytes smaller under LLD |
| Release-form size | 162,584 to 161,292 bytes, a 0.79% reduction |
| Local ARM data mapping symbols | 81 fewer in the final module, with effective code/data boundaries preserved |
| Default-linker wall time, median | 5.647 ms with BFD and 11.878 ms with LLD |
| Default-linker peak RSS, median | 7,700 KiB with BFD and 53,348 KiB with LLD |
| Static ABI and binary correctness | No regression found in checked final artifacts |
| Real GCC/BFD build | Three real C/D pairs passed on the target GCC SDK, including an explicit GNU cross prefix |
| Runtime memory and regression | Memory benefit unmeasured, new-QB runtime verification pending |

Frozen objects reproduced the size difference through an identical final LLD link and equivalent BTF and strip processing. The reduction came from 81 fewer 16-byte local mapping symbols, partly offset by four bytes encoding default ARM attributes. Both locally built stripped modules matched their respective published QB artifacts byte for byte. The six other stripped modules were byte-identical across patch groups. The historical RPM-level compression delta is an observation from the two releases. [Frozen replay](evidence/replay/link-replay.json) · [Mapping and ABI analysis](ARM_MAPPING_SYMBOL_ANALYSIS.md)

The sample supports the change as a Kbuild compatibility fix with a small release-file reduction. On the tested native x86-64 environment, LLD took longer and used more peak process RSS in both the default and single-thread profiles. These results describe the recorded composite-object invocation and tool builds. A targeted follow-up could test other ARM packages with real partial links and retained symbol tables. Product merge readiness is **PENDING**. [Timing and RSS statistics](LINKER_BENCHMARK_SUMMARY.csv) · [GCC compatibility](GCC_COMPATIBILITY_REPORT.md) · [Runtime feasibility](RUNTIME_MEMORY_FEASIBILITY.md) · [Bounded generalization](evidence/runtime/generalization.md)
