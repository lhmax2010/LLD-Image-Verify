# Verify the linker used in Tizen QB 1234653

This kit checks the RPi boot, headed and headless images for aarch64 and armv7l. It uses the published Unified build and its pinned Base snapshot. Artifact access uses the public download server.

[QuickBuild 1234653](https://quickbuild.tizen.org/build/1234653) · [Published images](https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261119.012153/images/standard/) · [Base snapshot](https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_20261117.165617/)

## Prerequisites

Use Linux with Python 3.12 or newer. On Ubuntu 24.04:

```bash
sudo apt-get install python3 curl rpm2cpio cpio e2fsprogs mtools initramfs-tools-core zstd binutils
```

Run the commands below from this directory. Scans read and extract files without booting the image or mounting partitions. The script runs as an ordinary user.

## Quick check using the image manifest

```bash
python3 verify.py sample --arch aarch64
python3 verify.py sample --arch armv7l
```

This downloads the published headed-image package manifest, resolves the exact RPMs by version, architecture and source commit, and inspects their ELF and matching debuginfo. It is a small download compared with the image archive.

| Manifest-selected file | Expected result on both architectures |
|---|---|
| `/usr/bin/deviced` | `lld-confirmed`, LLD 22.1.8 |
| `/usr/bin/wrt-loader` | `lld-confirmed`, LLD 22.1.8 |
| `libtiff.so.6.1.0` | `not-lld-22.1.8`, version definitions include parent nodes |

By default this checks the RPM bytes listed by the manifest. If you have the extracted headed root filesystem, include `--image-root /path/to/rootfs` to verify that the three files in the image have the same SHA256 as the RPM files. Results are in `sample-aarch64.tsv` or `sample-armv7l.tsv`.

## Audit the published image bytes

Run a single image first or scan both architectures and all profiles.

```bash
python3 verify.py --work-dir ./headed-aarch64 image --profile tizen-headed-aarch64
python3 verify.py --work-dir ./all-images image --all --jobs 2
```

By default the tool verifies the archive and manifest checksums, inventories ELF files, matches debuginfo from both repositories and checks the applicable public build logs. A full six-image scan downloads about 1.9 GB in image archives and about 1.6 GB in debuginfo, plus metadata and logs. Allow 20 GB of free working space. Rerunning with the same work directory reuses downloads and completed extractions. Use one process per work directory. The optional `--no-debuginfo` mode downloads the images and build logs and produces a lower-confidence report.

| Output | Contents |
|---|---|
| `elf-linker-audit.tsv` | One row per image file and partition, with SHA256, linker classification and evidence |
| `rpm-linker-audit.tsv` | Per-image RPM, source commit, repository and file counts by classification |
| `summary.json` | Per-image totals and SHA256 deduplication counts |
| `debug-errors-*.jsonl` | Candidate debug RPMs that failed download or inspection. An image scan with these errors emits its available evidence and exits with status 2 |

For this build, a full run should find 10,875 ELF or kernel file instances plus 12 static archives. A file present in multiple images is counted in each image. The complete baseline had 6,878 confirmed LLD instances and 306 instances with evidence excluding this LLD, with remaining cases assigned to layout-only or unresolved classifications.

## Inspect a single extracted ELF

```bash
python3 verify.py elf /path/to/rootfs/usr/bin/deviced --debug /path/to/deviced.debug
python3 verify.py elf /path/to/rootfs/usr/lib64/libtiff.so.6.1.0
```

The tool checks the ELF's `.gnu_debuglink` CRC or its GNU Build ID against the supplied debug file before using its linker marker. Supplying an unrelated debug file produces an error.

You can inspect the same fields with binutils.

```bash
readelf -p .comment /path/to/deviced.debug
readelf -x .gnu_debuglink /path/to/rootfs/usr/bin/deviced
readelf -n /path/to/rootfs/usr/bin/deviced
readelf -V /path/to/rootfs/usr/lib64/libtiff.so.6.1.0
readelf -lW /path/to/rootfs/usr/lib64/libncurses.so.6.6
```

## Interpret the evidence

- `lld-confirmed` uses a linker identification string, a matched debuginfo marker, an embedded kernel version, or a build log that identifies LLD and the linked target. The published runtime RPMs often omit the `.comment` section, while their paired debug files retain it. [LLD marker implementation](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/lld/ELF/SyntheticSections.cpp#L65)
- `gnu-ld-confirmed` and `other-linker-confirmed` have positive evidence for a different linker. `not-lld-22.1.8` means the ELF has a version definition with parent nodes, which this LLD version does not generate. The parent node by itself does not identify a specific alternative linker. [LLD 22.1.8 version definition implementation](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/lld/ELF/SyntheticSections.cpp#L1226)
- `lld-layout` and `gnu-ld-like-layout` are inferences calibrated for these ARM images. `unresolved` means the available data did not establish a linker. GCC or Clang compiler strings, a GNU Build ID by itself, and the absence of a linker string are insufficient evidence of the linker.
- The RPM table counts each evidence class separately. A package can ship ELF files with different linkers. A script, data-only RPM, or static archive does not have a final native ELF link to inspect.
