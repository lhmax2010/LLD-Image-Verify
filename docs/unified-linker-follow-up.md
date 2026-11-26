# Unified linker follow-up

Snapshot `tizen-unified-toolchain_20261120.082536`. The [source package table](../data/unified-20261120/packages.csv) has 509 package and architecture rows. It references numbered lines from the [published log excerpts](../evidence/unified-20261120/log-lines.csv.gz). All 506 retrieved logs matched the SHA256 already recorded in the snapshot inventory. Three rows cover `org.example.gbs-sample`, whose published source RPM is available and whose standard-profile logs returned HTTP 404. The package list supplied in the request was unavailable at the specified Downloads path. This audit reconstructed scope from the archived RPM evidence, image evidence and published log index. [Log receipts](../evidence/unified-20261120/logs.csv) · [Binary RPM counts](../data/unified-20261120/binary-rpm-classes.csv)

The ELF counts use scanned RPM members or installed image instances as indicated. The image data cover ARM and retain repeat appearances across images. The RPM pass covers archived ARM off-image members and x86_64 members. The counts are independent. A positive marker, a link-driver selection in the published log, a controlled replay, and a SHA match each record their own evidence. Compiler strings without a linker marker remain a selection criterion.

## 1. Rust

The sweep covers 139 source recipe names across three architectures, including 123 names beginning `rust-` and the named mixed-language recipes. The 417 logs provide per-package compiler/linker arguments. The two control replays establish the behavior of the shared default. Native C and C++ targets and Rust targets with other settings retain their own evidence. [Per-package log references](../data/unified-20261120/packages.csv)

`/etc/rpm/macros.rust-toolset` invokes `/usr/bin/rustc` directly for `%rustc_std_build` and `%rustc_dylib_build`. It sets `LD_LIBRARY_PATH` and Rust library search directories. Its Cargo setup writes `.cargo/config` with the same compiler path and global rustflags for optimization, debuginfo and RELRO/NOW hardening. These macro paths leave linker selection to the target. The chosen `rust-regex` and `pkgmgr-server` commands have no explicit `-C linker`, linker-flavor override or linker-selection link argument. [RPM Rust macros, lines 9–35 and 40–72](../evidence/unified-20261120/rust/aarch64/rust-macros-1.txt)

| Arch | Published rust-regex command | Published pkgmgr-server command | Observed control linker | Tizen LLD prototype |
| --- | --- | --- | --- | --- |
| aarch64 | [line 230](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/aarch64/succeeded/rust-regex.buildlog.txt) | [line 560](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/aarch64/succeeded/pkgmgr-server.buildlog.txt) | `gnu-cc` → GCC `collect2` → GNU ld 2.43 | 2/2 markers and 2/2 export sets equal |
| armv7l | [line 204](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/armv7l/succeeded/rust-regex.buildlog.txt) | [line 527](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/armv7l/succeeded/pkgmgr-server.buildlog.txt) | `gnu-cc` → GCC `collect2` → GNU ld 2.43 | 2/2 markers and 2/2 export sets equal |
| x86_64 | [line 226](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/x86_64/succeeded/rust-regex.buildlog.txt) | [line 664](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/x86_64/succeeded/pkgmgr-server.buildlog.txt) | `gnu-lld-cc` → GCC `collect2` → sysroot `gcc-ld/ld.lld` → rust-lld 20.1.8 | 2/2 markers and 2/2 export sets equal |

All three Rust distributions contain a runnable `rust-lld` that reports 20.1.8. The ARM target specifications leave self-contained linking disabled by default. The x86_64 target enables the self-contained linker component and the GNU LLD compiler-driver flavor. Its executed command includes the sysroot `-B` path and `-fuse-ld=lld`, which resolve the wrapper. The control receipts log successful executions, compiler and linker versions, and the ELF comments. [Control and prototype receipts](../evidence/unified-20261120/rust) · [Rust codegen options](https://doc.rust-lang.org/rustc/codegen-options/index.html#link-self-contained)

For the prototype, append the following options to the RPM macro's rustc invocation. Supply the same options through `[target.<rust-target>]` linker and rustflags for Cargo recipes, preserving their existing hardening flags. `TIZEN_TRIPLE` means `aarch64-tizen-linux-gnu`, `armv7l-tizen-linux-gnueabi`, or `x86_64-tizen-linux-gnu`.

```bash
-C linker=/usr/bin/${TIZEN_TRIPLE}-clang -C link-arg=--ld-path=/usr/bin/ld.lld
# Also for x86_64
-C link-self-contained=-linker
```

The 6/6 candidate ELFs contain `Linker: LLD 22.1.8`. The 6/6 sets of defined global, weak or unique dynamic exports with default or protected visibility match both the control and the published ELF, including symbol type and version. The 6/6 `DT_NEEDED` sets match their controls. The replays use the original logged rustc commands, SRPM sources and pinned RPM inputs. The `pkgmgr-server` trial links the exact published companion C DSOs and checks the Rust executable. Service startup and end-to-end RPM tests remain open. [Symbol and hash comparisons](../evidence/unified-20261120/rust)

### Rust distribution and version counts

`rust.buildlog.txt` installs the upstream target std component on [aarch64, lines 490–501](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/aarch64/succeeded/rust.buildlog.txt), [armv7l, lines 482–493](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/armv7l/succeeded/rust.buildlog.txt) and [x86_64, lines 462–473](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/x86_64/succeeded/rust.buildlog.txt). The installed std copies have a 20.1.0 marker on aarch64, no linker marker on armv7l, and a 20.1.8 marker on x86_64. Changing the downstream crate macro leaves these distribution binaries as shipped. [Std per-file evidence](../data/unified-20261120/rust-distribution-std.csv)

| Scope and arch | Tizen 22.1.8 | Rust bundled 20.1.8 | Rust distribution std | Other LLD 20.1.0 | Compiler comment only | Denominator |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RPM pass aarch64 | 48 | 0 | 2 | 15 | 140 | 205 |
| RPM pass armv7l | 48 | 0 | 2 | 0 | 171 | 221 |
| RPM pass x86_64 | 48 | 152 | 2 | 3 | 0 | 205 |
| Image aarch64 | 52 | 0 | 2 | 0 | 6 | 60 |
| Image armv7l | 52 | 0 | 2 | 0 | 6 | 60 |

## 2. GCC recipe trials

The published logs distinguish GCC-selected C/C++ recipes from gfortran targets. The first isolated GBS trial reached dependency resolution and stopped in the privileged helper with a user namespace UID mapping error. The test matrix uses `rpmbuild -bc` with the pinned Tizen RPM payloads, project toolchain macros and archived source RPM specs. Each successful output marker establishes the tested link. This matrix includes partial builds and separately records their exit status. [GBS attempt](../evidence/unified-20261120/isolated-gbs-yaca.log) · [Trial commands and exit status](../evidence/unified-20261120/trial-builds.csv) · [Pre-strip output markers](../evidence/unified-20261120/trial-elf-markers.csv)

The workstation restarted during some trials. The recovered table has 100 attempt records, including 6 completed build stages, 42 nonzero exits, 43 timeouts and 9 interrupted runs without a recorded exit. The pre-strip table captures 29 native outputs across those attempts. Evidence collection after restart uses targeted file paths, one process, a total CPU quota equivalent to 25% of one logical CPU, a 1 GiB memory cap and idle I/O scheduling.

| Source recipe | Published cause and proposed fix |
| --- | --- |
| `nntrainer` | The spec selects GCC and Meson identifies `ld.bfd 2.43` on ARM. The first aarch64 Clang build stops at `tflite_interpreter.cpp:337` on unqualified `std::move` under `-Werror`. Qualify it and address any remaining Clang diagnostics. GCC + LLD reached the aarch64 C/C++ linker probes. |
| `yaca` | The spec selects GCC. Clang links `libyaca.so` with Tizen LLD on both ARM architectures. The initial tests hit `__COUNTER__` warnings promoted to errors. Once those warnings were allowed, Clang diagnosed out-of-range enum values in `constexpr` test fixtures. Update the test macro and exercise invalid C enum inputs at the C API boundary. GCC + LLD also produced both ARM libraries. The aarch64 build reached a successful `%build` exit. |
| `onnxruntime` | The spec selects GCC and adds GCC-specific warning flags. Clang passed CMake compiler detection on both ARM arches before the runs reached their time limits during dependency configuration. Gate the switches by compiler and complete the shared target build. |
| `openblas` | The spec selects GCC and passes `FC=gfortran`. The published shared links explicitly invoke target GCC. Clang plus gfortran produced LLD 22.1.8 markers in 2/2 serial libraries on ARM. Both OpenMP links initially failed on `-lomp`. Replaying those same shared links with the pinned `libomp` and `libomp-devel` packages produced LLD 22.1.8 in 2/2 OpenMP libraries. Add the build dependency and validate the remaining pthread variants. |
| `lapack` | The recipe selects GCC and CMake logs GNU Fortran shared-library links. The aarch64 gfortran + LLD trial produced `libblas.so.3.7.1` and `liblapack.so.3.7.1` with the 22.1.8 marker. Retain the Fortran compiler and direct the Fortran links through LLD. |
| `hdf5` | The published C and C++ compiler selection is Clang. The spec sets `F9X=gfortran` and enables Fortran, with visible gfortran library links. The aarch64 trial marked the C and C++ DSOs with LLD 22.1.8. Keep the split compiler configuration and verify the Fortran DSO independently. |

The six recipes provide evidence of the configured compiler and trial behavior. The Fortran parts of OpenBLAS, LAPACK and HDF5 require a Fortran compiler. Their stock recipes supply gfortran. A Clang C/C++ trial with gfortran retained tests the mixed compiler path. [Published ARM log lines](../evidence/unified-20261120/log-lines.csv.gz)

Standalone GCC and gfortran shared-library probes produced 4/4 LLD 22.1.8 markers across aarch64 and armv7l. The armv7l probes explicitly use `-L/usr/lib -L/lib` for the guest linker search. These probes establish toolchain support for the proposed flags. The per-package build records give the separate recipe and target results. [Executed GCC and gfortran linker probes](../evidence/unified-20261120/gcc-lld-probes)

[OpenBLAS OpenMP replay commands and ELF records](../evidence/unified-20261120/openblas-openmp)

## 3. ANGLE

The RPM exports Clang. GN separately passes `is_clang=false` and leaves `custom_toolchain` at its empty default. Its Linux toolchain chooses target GCC and gold. The final `gcc_solink_wrapper.py` commands for `libGLESv2_angle.so` explicitly use target `g++ -fuse-ld=gold` at [aarch64 lines 335 and 4527](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/aarch64/succeeded/angle.buildlog.txt) and [armv7l lines 353 and 1547](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/builddata/buildlogs/standard/armv7l/succeeded/angle.buildlog.txt).

Set `is_clang=true use_lld=true clang_base_path="/usr" clang_use_chrome_plugins=false`, use the Tizen target triple, and provide the Abseil GN files or explicitly disable `angle_enable_abseil`. The first two-arch trial stopped because enabling Clang enabled Abseil and the SRPM lacked the GN dependency. Disabling it exposed the aarch64 generic target triple's C++ include-path failure. The revised trial uses `aarch64-tizen-linux-gnu`. Both ARM manifests select Clang++ with `-fuse-ld=lld` for 4/4 shared targets and reached compilation before the trials stopped. Completed shared outputs and EGL/GLES tests remain open. [aarch64 generated links](../evidence/unified-20261120/trials/recipe-builds-final-aarch64-angle-clang-fixed-generated-link-settings.tsv) · [armv7l generated links](../evidence/unified-20261120/trials/recipe-builds-final-armv7l-angle-clang-fixed-generated-link-settings.tsv) · [Trial output](../evidence/unified-20261120/trial-builds.csv)

## 4. Other recipes

| Source recipe | Finding and proposed fix |
| --- | --- |
| `chromium-efl` | The x86_64 GN args name `//tizen_src/build/toolchain/tizen:tizen_x64` and `is_clang=false` at lines 1792, 1821 and 1852. Change the x86_64 GN toolchain to one using Tizen Clang and LLD. The published args establish the toolchain selection. Final linker commands need a verbose target build. |
| `emuld` | The x86_64 log configures CMake at 494, identifies GNU C++ at 504 and later exports the Clang driver at 559. Move compiler selection before configure and regenerate the cache. The exact final linker executable is unresolved. |
| `fluoride` | `libbluetooth.so` is built by a GN configuration with `cc="gcc"`, `cxx="g++"`, and the Clang switches false. See aarch64 324/1637, armv7l 307/1620 and x86_64 333/1646. `liblc3.so` matches a source member on 3/3 architectures, and the spec copies it at line 96. Switch `libbluetooth.so` in GN and treat the copied LC3 payload according to its provenance. |
| `netcoredbg` | The test DSO uses an explicit `g++ -g -fPIC -shared` at aarch64 1546, armv7l 1872 and x86_64 1571. Select the target `CXX` and preserve the test DSO's symbols. The main debugger links via Clang. |
| `u-boot-tools` | The aarch64 RPi log shows a Clang `HOSTCC` override in the tools phases at 428/459 and 594/607. The armv7l equivalents are 418/449 and 583/596. The subsequent ordinary build relinks `dtc` at aarch64 638 and armv7l 627 without the spec's Clang `HOSTCC` assignment. The archived Makefile defaults to `HOSTCC=cc`. `tools/env/Makefile:9` overrides `HOSTCC` with the target `CC` for `fw_printenv` even during the earlier envtools step. Set `HOSTCC` consistently for `dtc` and control target `CC` in the envtools step. Record the final drivers and ELF markers in a verbose build. |
| `org.example.gbs-sample` | The SRPM spec line 74 calls `tizen build-native -c gcc` and lines 77–86 stage stripped and unstripped copies. The standard log returned 404 for all three architectures. Capture the SDK's verbose final link if the actual linker executable is required. |

[Per-package published URLs and numbered lines](../data/unified-20261120/packages.csv) · [Numbered source excerpts](../evidence/unified-20261120/source-excerpts.txt)

## 5. Stripped and prebuilt files

The SHA pass searched 16 published SRPMs, including nested application archives and nested RPM payloads. It found 191 file-to-source pairs across the archived image and RPM scopes. Matches cover the engine application packages, `push`, files in `stt`, `tts`, `voice-control`, `wakeup-engine-default`, the `security-config` test tools `file` and `readelf`, Fluoride's `liblc3.so` and the nested `libmtp` payloads. Each row gives the SHA256 and the exact source member. A missing SHA match leaves provenance open. [SHA matches](../evidence/unified-20261120/source-sha-matches.csv) · [Source RPM receipts](../evidence/unified-20261120/provenance-source-rpms.json)

- The three published `mtp-initiator-haltests` executables have positive LLD 22.1.8 evidence. CMake logs the haltests targets at aarch64 464, armv7l 457 and x86_64 553.
- `nnfw` logs Clang 22.1.8 C and C++ and CMake links for named shared targets. Its spec has an install-strip option. Both local builds reached CMake generation and stopped at the unresolved `flatbuffers::flatbuffers-23.5.26` target. The published targets are recorded, and the remaining exact files need pre-strip proof.
- `augeas` shows the selected compiler and Libtool checks. The five runtime ELF rows per architecture lack a marker in the archived pass. Direct pre-strip marker evidence from a successful trial describes the tested build.
- `stt`, `tts` and `voice-control` have both real CMake link targets and byte-matched copies. `wakeup-engine-default` also configures Clang and ships matched copies. Keep target build actions separate from the sources of copied files.

## 6. Kernel modules

The [kernel CSV](../data/unified-20261120/kernel-modules.csv) records 18 architecture and source-log pairs. It contains the observed `LLVM=`, `CC=`, `LD=` and `CROSS_COMPILE=` settings, when present, and numbered `LD [M]` actions in 14/18 logs.

- Jetson, NV OOT, nvgpu, HWPM and NV display each export `LLVM=1` in the aarch64 module build. RPi does so in the aarch64 and armv7l regular and RT build phases. With standard Kbuild that selects `LD=ld.lld`. The log lines locate the corresponding module actions. [Kbuild LLVM configuration](https://docs.kernel.org/kbuild/llvm.html#the-llvm-argument)
- Tizen modules export `LLVM=1` in selected sub-builds. The aarch64 first listed action at 458 occurs before the first logged `LLVM=1` at 583. Use the settings for that sub-build when assigning link evidence. The source/helper RPM has userspace links and no recorded `LD [M]` action.
- Qualcomm kernel, camera, graphics and video each record an actual aarch64 link action. Their standard logs do not show a module-phase LLVM or LD override. The aarch64 Amlogic log also records module link actions with no such override. The armv7l Amlogic log lacks a module link action. A `V=1` capture would expose the exact executable at each site.

## Reproduction

- `trace-unified-recipes.py` reads the pinned build-log index and records numbered, SHA-checked excerpts.
- `prepare-unified-replay.py` fetches the selected source and binary RPMs into workspace-local roots. `replay-unified-rust.py` runs the control and prototype with the exact logged Rust commands and compares the defined dynamic exports.
- `prepare-unified-recipes.py`, `try-unified-gbs.sh` and `build-unified-trials.py` stage and run the recipe trials. `probe-unified-gcc-lld.py` and `replay-unified-openblas.py` test the two ARM driver families and the OpenMP link inputs.
- `match-unified-prebuilts.py` checks ELF SHA256s across source archives. `capture-unified-source-lines.sh`, `collect-unified-trial-evidence.py` and `export-unified-linker-audit.py` produce the published receipts and tables.
- `run-unified-bounded.sh` applies the resource limits to a command and its child processes.
