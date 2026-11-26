# Tizen image linker follow-up

The two ARM rounds each contain **6,892 confirmed LLD instances out of 10,875**. Exact RPM payload matches recovered all 16 previously unattributed LLD instances in each round. The revised Unified rate is **6,892 / 7,071 (97.5%)**. The 3,804 Base instances per round still include zero confirmed LLD instances. The Base repository does contain confirmed LLD files for x86_64, which had no image in this study. [Image denominators](../data/image-class-denominators.csv) · [Recovered RPM ownership](../evidence/recovered-image-rpm-owners.csv) · [Base RPM sample](../evidence/base-sample-rpm-elf-evidence.csv.gz)

## Evidence and denominators

| Evidence class | Whole image, per round | Unified origin, per round | Base origin, per round |
| --- | ---: | ---: | ---: |
| Confirmed LLD | 6,892 / 10,875 | 6,892 / 7,071 | 0 / 3,804 |
| Confirmed GNU ld | 140 / 10,875 | 14 / 7,071 | 126 / 3,804 |
| Prebuilt or generated outside our toolchain | 103 / 10,875 | 103 / 7,071 | 0 / 3,804 |
| GNU ld-like layout | 3,459 / 10,875 | 38 / 7,071 | 3,421 / 3,804 |
| LLD-like layout | 24 / 10,875 | 24 / 7,071 | 0 / 3,804 |
| LLD 22.1.8 excluded by version definitions | 234 / 10,875 | 0 / 7,071 | 234 / 3,804 |
| Insufficient evidence | 23 / 10,875 | 0 / 7,071 | 23 / 3,804 |

Each round has 6,014 distinct native SHA256 hashes. The 12 static archive records per round are outside the native denominator. An ELF can occur in multiple images or partitions. The [per-instance CSV for QB 1234653](../data/image-instances-20261119.012153.csv) and the [per-instance CSV for the Patchset 3 round](../data/image-instances-20261120.082536.csv) preserve those occurrences. The 10 instances per round with multiple candidate RPM owners carry their candidate labels and an empty single-owner NEVRA. The [RPM table](../data/image-rpm-verdicts.csv) has 2,556 rows per round. Its verdicts cover observed native files, and packages with ambiguous ownership or unresolved linker evidence may have an `open` verdict. An RPM containing confirmed LLD files and externally built files is mixed. The `no native files` image verdict means the scan attributed zero native instances to the package. [Archived instance inputs](../evidence/archive/statistics/)

### The original 179 Unified exceptions

The [instance list](../data/unified-exception-instances.csv) and [package and architecture table](../data/unified-exceptions-by-rpm.csv) retain all 179 original exceptions per round, the revised evidence class, the package-level cause or evidence gap, and the GCC-only scope decision. GCC-only means the observed recipe explicitly selected GCC or its Fortran frontend. The tag records the recipe decision. Portability requires a separate build test.

| Original category | Per round | Result |
| --- | ---: | --- |
| Confirmed GNU ld | 14 / 179 | All 14 come from `nntrainer` subpackages. The GNU CC and CXX exports, Meson ld.bfd 2.43 identification, target link traces and RPM byte matches establish the cause. |
| GNU ld-like layout | 96 / 179 | 58 now have prebuilt SHA256 matches. The remaining 38 cover OpenBLAS (8), yaca (8), repacked glibc debuginfo in tizen-debug (8), pkgmgr-server (4), rust-regex (4), rust-regex-syntax (4), and Rust std (2). The OpenBLAS and yaca recipes select GCC. Their final linkers remain open. |
| LLD-like layout | 24 / 179 | `nnfw` configures CMake with Clang 22.1.8 on both ARM architectures. The layout points toward LLD. The files lack a matched debuginfo linker marker or target-level linker trace. |
| Insufficient evidence | 35 / 179 | The 25 STT and 10 VC instances match source RPM members. Their original linkers remain unidentified. |
| MetaWare | 8 / 179 | Four per boot image. The four hashes match literal VideoCore ELF additions in `00d7934-to-8cdc667.diff.gz`. The SRPM applies the patch in preparation and installs those bytes in `/boot`. The marker still identifies MetaWare v5.6.19. |
| Dart AOT | 2 / 179 | Each Homescreen `libapp.so` matches the ARM-specific TPK in the source RPM. The Dart AOT Build ID also recomputes exactly for both artifacts. |

The additional 58 prebuilt matches in the historical layout bucket include 20 more STT/VC instances, 8 more Homescreen files, and 30 speech, push, and pen-wave artifacts. The source RPM URL, VCS, RPM SHA256, member path and matching SHA256 are recorded for each. [QB 1234653 prebuilt proof](../evidence/prebuilt-20261119.012153.csv) · [Patchset 3 prebuilt proof](../evidence/prebuilt-20261120.082536.csv) · [Linux RPi published spec](../evidence/linux-rpi-published.spec) · [Dart Build ID proofs](../evidence/archive/results/2026-11-23-unresolved/)

The 16 historically unattributed LLD instances per round are 12 rootfs paths and four recovery ramdisk copies. The rootfs paths match exact bytes in installed profile-specific `org.tizen.powerkey-syspopup.common`, `org.tizen.system-syspopup.common`, `firmware-update-system-ui-common`, and `system-servant-profile_common` payloads for the same architecture. The payload basenames have a profile suffix or alias. The MIC package lists and payload paths explain why the original path-only ownership join missed them. [Instances](../data/unattributed-lld-instances.csv) · [RPM payloads and MIC membership](../evidence/recovered-image-rpm-owners.csv)

### Debuginfo rule

The rule fires when the paired debuginfo has compiler strings, lacks `Linker: LLD`, and lacks a `.note.gnu.gold-version` section. Every evaluated debug member was independently reread from an RPM verified against repository metadata. Pairing uses the recorded CRC or GNU Build ID, and requires both when both are recorded, with the same ELF machine. [Per-instance test](../data/debuginfo-rule-instances.csv) · [Per-class summary](../data/debuginfo-rule-summary.csv) · [Debug RPM and member receipts](../evidence/image-debuginfo-evidence.csv.gz)

| Architecture, per round | GNU ld agreement | LLD agreement | Combined agreement | Paired coverage |
| --- | ---: | ---: | ---: | ---: |
| aarch64 | 64 / 64 | 3,318 / 3,318 | 3,382 / 3,382 (100%) | 3,382 / 3,516 |
| armv7l | 64 / 64 | 3,329 / 3,329 | 3,393 / 3,393 (100%) | 3,393 / 3,516 |
| x86_64 | — | — | — | 0 image controls |

The GNU ld controls have target or replay evidence independent of the rule. The paired LLD controls are positive mostly because the same debuginfo contains an LLD marker, and no independently confirmed LLD control in either ARM round has an eligible pair. The 100% agreement therefore measures consistency on these controls. It does not validate promotion to a confirmed linker class from marker absence. [Independent-control rows](../data/debuginfo-rule-summary.csv)

In the Patchset 3 round, the rule fires on 1,682 / 1,760 aarch64 and 1,677 / 1,757 armv7l historical GNU ld-like cases. On the 58 historical insufficient-evidence cases it fires on 4 / 25 aarch64 and 11 / 33 armv7l. Those 15 flags are also 15 / 23 of the remaining Base cases after the STT/VC provenance corrections. None of the 24 `nnfw` ELFs has a usable pair. The rule also fires on 234 / 234 version-definition exclusions. The CSV preserves historical buckets and the later provenance class so each count can be recomputed without promoting a heuristic. [Rule application](../data/debuginfo-rule-summary.csv)

## QuickBuild 1234794 and the Base toolchain

**The results refute the blanket previous-snapshot hypothesis.** QB 1234794 ran with `Build Type=Full`, `Build Reference=Live`, and resolved the submitted Base reference to `tizen-base-toolchain_20261030.061318`. It published `tizen-base-toolchain_20261119.042539`. The job triggers the NGBS package build and then publishes the snapshot. Its parent step log and aggregate report show one package-build run and contain no logged full second pass. Later roots in that run contain Clang/LLVM 1.6, and early packages can retain 1.5 in their build logs and output. [QuickBuild parent lines 55, 1767–1777, 2366–2373 and 2646–2669](../evidence/qb-1234794/parent-log-excerpts.txt) · [GBS report](../evidence/qb-1234794/gbs-report-excerpts.txt) · [Published build.xml](../evidence/snapshot-metadata/tizen-base-toolchain_20261119.042539-build.xml)

| Architecture | Clang/LLVM 22.1.8 root release | Binutils 2.43 root release | Source package logs |
| --- | --- | --- | ---: |
| aarch64 | 1.4 on 1, 1.5 on 37, 1.6 on 220 | 1.5 on 2, 1.6 on 15, 1.7 on 241 | 258 / 258 |
| armv7l | 1.5 on 41, 1.6 on 217 | 1.6 on 3, 1.7 on 76, 1.8 on 179 | 258 / 258 |
| x86_64 | 1.5 on 10, 1.6 on 253 | 1.5 on 9, 1.6 on 254 | 263 / 263 |

The table uses actual installing, keeping and cumulate lines. The fixed Base input is a repository pointer. The package-root versions reflect the packages resolved during scheduling. RPM Release numbers vary with the build and architecture, so source VCS, exact RPM SHA256, and executable identity are needed when available. [Per-package build roots and image classes](../data/base-build-roots.csv) · [Snapshot metadata](../evidence/snapshot-metadata/)

On aarch64, `util-linux` started at 14:02:27 UTC with Clang/LLVM 1.5 and Binutils 1.5, exported the Clang driver, and libtool reported `/usr/bin/ld` as GNU ld. LLVM started at 14:24:53 UTC with Clang/LLVM 1.5 and finished at 15:56:53 UTC after writing Release 1.6. ICU, Boost and libsndfile started between 17:01:59 and 17:31:52 UTC and installed Clang/LLVM 1.6. The armv7l logs show the same before-and-after ordering. The x86_64 `util-linux` log, by contrast, starts at 20:43:24 UTC and uses Clang/LLVM 1.6. The corresponding x86_64 `nologin` RPM has an LLD marker in paired debuginfo. [LLVM log excerpts](../evidence/llvm-by-snapshot.txt) · [Base build roots with URLs and line numbers](../data/base-build-roots.csv) · [Base RPM sample](../evidence/base-sample-rpm-elf-evidence.csv.gz)

### How Clang selects LLD

The source change was authored on November 17, 2026. Gerrit 362074/1 adds the setting on `2c661e1c3`, and patch set 2 `f346dd75` applies it on the other LLVM packaging lineage used by QB 1234794. Both spec revisions still declare `Release: 1`. The published build assigned Release 1.6 in this QB. The earlier patch set 2 parent, `7b05a1374`, already built the `lld` project and included `ld.lld` in the main `llvm` package. Its spec had no `CLANG_DEFAULT_LINKER` override. Clang's empty preferred linker falls back to the system `ld`. The Base aarch64 1.5 util-linux probe agrees with that earlier policy. [362074/1 diff](../evidence/llvm-362074-1-spec.diff) · [362074/2 diff](../evidence/llvm-362074-2-spec.diff) · [Parent spec excerpts](../evidence/llvm-parent-spec-excerpts.txt) · [Clang driver source](https://clang.llvm.org/doxygen/ToolChain_8cpp_source.html)

The new spec captures the project `_toolchain` before choosing LLVM's bootstrap compiler and passes `-DCLANG_DEFAULT_LINKER=lld` for Clang projects. That compiled driver preference selects `ld.lld`. The installed `clang.cfg` sets its target, resource directory and `-Wl,-z,nostart-stop-gc` in the Clang project. The `clang++.cfg` symlink selects the same configuration. Clang's explicit linker overrides remain available. Unified `deviced` in `20261120.082536` kept Clang 1.6 at aarch64 line 265, armv7l line 424 and x86_64 line 264. Its ARM targets have independently paired LLD 22.1.8 evidence and its published logs contain no `-fuse-ld` override. [Patchset 2 spec change](../evidence/llvm-362074-2-spec.diff) · [Driver and binary control](../evidence/archive/evidence/2026-11-23/latest-base-probe/) · [Deviced build-log rows](../data/buildlog-package-evidence.csv) · [Deviced image, RPM and debuginfo identities](../evidence/archive/evidence/2026-11-23/ps3/identity.tsv)

QB's project config specifies `Required: binutils glibc rpm-build libtool` and `Support: clang llvm-devel` at lines 1330 and 1333. In the matching spec `clang` requires the same-version and same-release `llvm` RPM. All 779 logged roots for the QB have Clang and LLVM. The earlier historical x86_64 LLVM 1.5 payload lists `/usr/bin/ld.lld -> lld`. ARM Clang accelerator RPMs also contain a separate `/emul/usr/bin/ld.lld`, and the project preinstalls the accelerator on ARM. The published post-build driver probe uses the RPM's sibling linker and demonstrates lookup sensitivity. The probe does not resolve the executable pathname and hash used by every historical ARM link. [QB project config](../evidence/qb-1234794/parent-log-excerpts.txt) · [LLVM files and dependencies](../evidence/llvm-parent-spec-excerpts.txt) · [Earlier LLVM 1.5 payload](../evidence/historical-llvm-1.5-x86_64-payload.json) · [Accelerator receipts](../evidence/accelerator/)

### GCC recipe inventory

The six source names selecting GCC are `gcc`, `gcc-aarch64`, `gcc-armv7hl`, `gcc-armv7l`, `gcc-riscv64`, and `glibc`. GCC and glibc are GCC-only under the recipe scope used here, including applicable compiler bootstrap and cross-build variants. Five of 258 aarch64 builds, five of 258 armv7l builds, and six of 263 x86_64 builds show that selection. The log table includes the actual package and architecture combinations. Compiler strings from linked startup objects are insufficient to put a Clang package in this group. GCC supports `-fuse-ld=lld`. Target linker scripts, linker plugins, GCC LTO objects, and compiler runtime startup files still need package-level verification before changing the linker. [Base compiler inventory with exported drivers](../data/base-build-roots.csv) · [GCC link options](https://gcc.gnu.org/onlinedocs/gcc/Link-Options.html)

### Newer Base verification

Eight targets per architecture were checked in each of three published Base repositories. The sample consists of `nologin`, `libsndfile.so.1.0.37`, the ICU `tz2icu` and `zic` programs, and the Boost filesystem, program_options, system and thread libraries. All 72 sampled runtime ELFs were paired with debuginfo. [Sample payload and pair details](../evidence/base-sample-rpm-elf-evidence.csv.gz) · [Build start and toolchain lines](../evidence/newer-base-sample-log.txt)

| Base snapshot | aarch64 LLD | armv7l LLD | x86_64 LLD |
| --- | ---: | ---: | ---: |
| `20261119.042539` | 0 / 8 | 0 / 8 | 8 / 8 |
| `20261120.145751` | 7 / 8 | 7 / 8 | 7 / 8 |
| `20261125.143635` | 0 / 8 | 0 / 8 | 0 / 8 |

The `20261120.145751` libsndfile, ICU, and Boost roots used Clang 1.7 on aarch64, 1.8 on armv7l and 1.4 on x86_64. All three published versions came from `f346dd75`, and all sampled files from those packages displayed the LLD marker. The `nologin` targets lacked it; the ARM logs show Clang 1.5. In `20261125.143635`, the LLVM configure lines omit the option and the emitted Release 2.1 packages carry `7a54d3ff`. The ARM libsndfile, ICU and Boost logs in that repository date to October 29, so the published snapshot mixes rebuilt and reused results. [LLVM configure and timing excerpts](../evidence/llvm-by-snapshot.txt) · [Sample build logs and RPM evidence](../evidence/base-sample-rpm-elf-evidence.csv.gz)

### Proposed rebuild

Publish LLVM/Clang, binutils dependencies and any ARM accelerator binaries in a first stage. Before rebuilding Base, prove each architecture uses the expected compiler, config path and resolved linker binary with an in-root `clang -###` and a linked ELF marker. Rebuild the full Base against the pinned stage-one result with binary reuse disabled for the intended closure, or rebuild that closure after publishing the toolchain. Verify early packages such as util-linux alongside late ones. The current logs show 264 distinct Base source package names and 779 package/architecture builds, of which 763 select Clang. The authenticated QB parent log spans about 17 hours from the first trigger step to the end of publication. LLVM's three package builds each took about 1.5–1.9 hours. Budget roughly one more full QB window for a full rebuild, plus roughly 2–6 hours if a separate toolchain stage has to run first, subject to worker scheduling and queue time. [Source counts and elapsed package windows](../data/base-build-window.csv) · [QB timing](../evidence/qb-1234794/parent-log-excerpts.txt)

Gate the rebuild on unchanged target ABI and runtime behavior using same-source RPM pairs. Check SONAME, symbol/version definitions and inheritance, exports, DT_NEEDED, TLS and relocations, loader compatibility, page permissions and RELRO, linker scripts, unwind data, and kernel/module boot artifacts. Run loader and symbol lookup tests on all three architectures. Verify ARM device boot, upgrades, package installation, rollback and services before promoting the snapshot. [Prior ABI and loader findings](handoff.md)

## Published build logs

The sweep read all 7,598 listed logs for the two image rounds and their Base inputs across the requested architectures. It extracted CC/CXX exports, CMake and Meson compiler IDs, Meson host linker lines, configure linker probes, `-fuse-ld`, `--ld-path`, and explicit LD and CMake linker settings. Each package line carries its source log URL and first and last occurrence. Grouped repeated excerpts retain their occurrence counts. A configure probe records what the configure script detected. Final linker assignments use the target and payload evidence. [Per-package extraction](../data/buildlog-package-evidence.csv) · [Full excerpt table](../data/buildlog-lines.csv.gz) · [Log listings and file hashes](../data/buildlogs.csv)

| Published snapshot | aarch64 | armv7l | x86_64 |
| --- | ---: | ---: | ---: |
| Base `20261117.165617` | 258 / 258 | 258 / 258 | 263 / 263 |
| Base `20261119.042539` | 258 / 258 | 258 / 258 | 263 / 263 |
| Unified `20261119.012153` | 1,023 / 1,023 | 1,006 / 1,006 | 991 / 991 |
| Unified `20261120.082536` | 1,023 / 1,023 | 1,006 / 1,006 | 991 / 991 |

The numerator is scanned logs and the denominator is published log files discovered across the snapshot's standard architecture directories. Repository RPM files and source packages have different denominators. Logs retained by a newer snapshot can refer to an earlier actual build date. [Directory receipts](../data/buildlog-indexes.csv)

## Reproduce the audit

Run the scripts from this checkout. Keep the evidence and scratch directories in the current workspace. The image tables can be regenerated from the archived scan and replay records.

```bash
mkdir -p results/replay/cache
python3 scripts/export-image-evidence.py \
  --archive evidence/archive --repodata-cache results/replay/cache \
  --output results/replay
python3 scripts/test-debuginfo-rule.py \
  --data results/replay --debuginfo evidence/image-debuginfo-evidence.csv.gz
python3 scripts/sweep-buildlogs.py \
  --output results/replay/buildlogs --cache results/replay/cache/buildlogs
python3 scripts/summarize-buildlogs.py \
  --logs results/replay/buildlogs --data results/replay
python3 scripts/summarize-unified-exceptions.py --data results/replay
```

The [source-member matcher](../scripts/check-prebuilt-members.py) verifies SHA256 against sources. The [owner recovery script](../scripts/recover-image-rpm-owners.py) joins the headed MIC package lists with the released RPM scan. The [historical image scan and replay scripts](../scripts/) and the [standalone verifier](../share/tizen-lld-verify/) cover the original evidence chain. The [QB excerpt extractor](../scripts/extract-qb-1234794.py) retains source line numbers from an authenticated QB capture.
