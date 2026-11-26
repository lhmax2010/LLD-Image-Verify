#!/usr/bin/env python3
"""Explain the historical Unified exceptions by runtime RPM and architecture."""
import argparse
from collections import defaultdict
from importlib import import_module
from pathlib import Path

image = import_module("export-image-evidence")
# GCC-only here describes recipes that explicitly select a GCC toolchain.
SOURCES = {
    "nntrainer": ("nntrainer", "yes", "The recipe exports GNU CC and CXX. Meson and the target link trace identify ld.bfd 2.43."),
    "yaca": ("yaca", "yes", "The recipe exports GNU CC and CXX. CMake calls the GCC driver for libyaca.so. The exact linker remains open."),
    "openblas": ("openblas", "yes", "The recipe selects GCC and passes FC=gfortran for the OpenBLAS variants. The exact linker remains open."),
    "nnfw": ("nnfw", "no", "The package builds with Clang 22.1.8 in CMake. The tested image ELFs have LLD-like layout and lack a paired debuginfo linker marker or target-level linker trace."),
    "pkgmgr-server": ("pkgmgr-server", "no", "The final binary is built by rustc. The command has no explicit linker selection. CMake separately configures Clang for the native components."),
    "rust": ("rust", "not applicable", "The Rust RPM installs a distribution rust-std component. The original linker of the layout-only std object remains open."),
    "rust-regex": ("rust-regex", "no", "The target is built by rustc as a dylib. The command has no explicit linker selection."),
    "rust-regex-syntax": ("rust-regex-syntax", "no", "The target is built by rustc as a dylib. The command has no explicit linker selection."),
    "tizen-debug": ("tizen-debug", "not applicable", "The package takes Base glibc debuginfo files and repacks them with eu-elfcompress."),
    "linux-rpi": ("linux-rpi", "not applicable", "The kernel spec installs four already-linked VideoCore firmware files. Source patch bytes match the image SHA256 and the ELF comments identify MetaWare."),
    "homescreen-app": ("org.tizen.homescreen", "not applicable", "The image bytes are present in the source RPM's TPK member. Dart produced libapp.so directly."),
    "stt-engine-default": ("org.tizen.stt-engine-default", "not applicable", "The source RPM supplies byte-identical speech inference binaries."),
    "vc-engine-default": ("org.tizen.vc-engine-default", "not applicable", "The source RPM supplies byte-identical voice inference binaries."),
    "tts-engine-default": ("org.tizen.tts-engine-default", "not applicable", "The source RPM supplies byte-identical speech synthesis binaries."),
    "sppc": ("push", "not applicable", "The push source RPM supplies byte-identical payload files."),
    "hand-drawing-engine": ("pen-wave", "not applicable", "The pen-wave source RPM supplies the byte-identical native library."),
    "wakeup-engine-default": ("wakeup-engine-default", "not applicable", "The RPM installs the source-distributed wakeup engine library."),
    "voice-control": ("voice-control", "not applicable", "The RPM installs a source-distributed vc_getengine helper. The other targets in the package have Clang build logs."),
    "stt": ("stt", "not applicable", "The RPM installs a source-distributed voice_getengine helper. The other targets in the package have Clang build logs."),
    "tts": ("tts", "not applicable", "The RPM installs a source-distributed tts_getengine helper. The other targets in the package have Clang build logs."),
}
SOURCE_TARGET_EVIDENCE = {"tizen-debug", "yaca", "openblas", "nnfw", "stt", "tts", "voice-control", "wakeup-engine-default",
                          "rust", "pkgmgr-server", "rust-regex", "rust-regex-syntax"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    by_package = defaultdict(list)
    for row in image.rows(args.data / "unified-exception-instances.csv"):
        by_package[tuple(row[key] for key in ("snapshot", "arch", "rpm_nevra", "source",
                                              "historical_class", "evidence_class"))].append(row)
    buildlogs = {(r["snapshot"], r["arch"], r["package"]): r
                 for r in image.rows(args.data / "buildlog-package-evidence.csv")}
    rows = []
    for (snapshot, arch, rpm, source, old_class, verdict), files in sorted(by_package.items()):
        project = source.rsplit("/", 1)[1]
        package, gcc_only, reason = SOURCES[project]
        if gcc_only == "not applicable" and verdict != "not-linked-by-our-toolchain" and project not in {"tizen-debug", "rust"}:
            reason = "Source prebuilt provenance is unverified for these bytes. " + reason
            gcc_only = "undetermined"
        log = buildlogs.get((snapshot, arch, package), {})
        signal = log.get("meson_host_linker") or log.get("cmake_compiler") or log.get("cc_cxx_export", "")
        rows.append(dict(snapshot=snapshot, arch=arch, rpm_nevra=rpm, source=source, historical_class=old_class,
                         evidence_class=verdict, instances=len(files), historical_exception_denominator=179,
                         distinct_sha256=len({f["sha256"] for f in files}), gcc_only_by_recipe=gcc_only,
                         root_cause_or_limit=reason, log_url=log.get("url", ""), log_lines=signal,
                         target_evidence=(f"evidence/unified-target-log-excerpts/{project}-target.log"
                                          if project in SOURCE_TARGET_EVIDENCE else ""),
                         instance_evidence="data/unified-exception-instances.csv"))
    image.write_csv(args.data / "unified-exceptions-by-rpm.csv", rows)


if __name__ == "__main__":
    main()
