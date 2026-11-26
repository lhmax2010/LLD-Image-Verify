#!/usr/bin/env python3
"""Generate the Unified linker audit tables from archived scan and trace evidence."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path
import re

SNAPSHOT = "tizen-unified-toolchain_20261120.082536"
SOURCE_ALIASES = {"rpi4-linux-kernel": "linux-rpi", "jetson-linux-kernel": "linux-jetson"}
RUST_SOURCE = re.compile(r"^(rust(?:-|$)|rpc-port$|bundle$|appcore-agent$|capi-appfw-|pkgmgr-server$)")
LINKER_MARKER = re.compile(r"Linker: LLD ([0-9]+\.[0-9]+\.[0-9]+)([^|]*)")
RUST_ID = re.compile(r"\brustc(?: version)? (?:version )?[\d.]+")
RUST_STDLIB = re.compile(r"(?:^|/)lib(?:std|test|proc_macro)-[a-f0-9]+\.so$")
CLANG_ID = re.compile(r"(?:clang version |Tizen clang version )")
CATEGORY = ("rust-command", "rust-settings", "rust-component", "gn", "meson-linker", "cmake", "driver-link",
            "target", "named-target", "kernel-build", "kernel-module", "export", "linker-select", "install-copy")
ROOT_CAUSES = {
    "nntrainer": ("spec _toolchain_override gcc; Meson probes ld.bfd", "Use Clang after qualifying std::move and fixing any additional warnings; GCC + LLD remains a staged option."),
    "yaca": ("spec _toolchain_override gcc; CMake links through GCC", "Retain strict warnings and update the test macro for Clang 22; the production shared library already links under Clang."),
    "onnxruntime": ("spec _toolchain_override gcc and GCC-specific warning options; recorded CMake compiler GNU", "Gate GCC-specific warning switches by compiler and test the full shared target with Clang."),
    "openblas": ("spec _toolchain_override gcc and FC=gfortran; Make links shared variants via GCC", "Test Clang for C, retain gfortran, pass LLD to the actual shared driver for each threading variant and test OpenMP."),
    "lapack": ("spec _toolchain_override gcc; CMake reports GNU Fortran and invokes gfortran for BLAS/LAPACK", "Separate CC from FC; use gfortran -fuse-ld=lld for Fortran links before changing that compiler."),
    "hdf5": ("Clang default for C/C++; spec exports F9X=gfortran and enables Fortran", "Keep Clang for C and C++, use gfortran with LLD for Fortran and check mixed-language symbols/runtime."),
    "angle": ("spec invokes GN is_clang=false; Linux GN defaults to use_gold when LLD is off; wrapper links through target g++", "Use GN is_clang=true use_lld=true with Tizen target triples; provide or disable the Abseil GN dependency and verify generated target commands and four DSOs."),
    "chromium-efl": ("x86_64 GN selects tizen_x64 and is_clang=false; ARM toolchains are separate", "Enable a Tizen Clang/LLD GN toolchain for x86_64 and audit final DSOs individually."),
    "emuld": ("CMake GNU C++ identification precedes the later Clang exports", "Move compiler selection before the first CMake configure and build verbosely."),
    "fluoride": ("GN explicitly sets gcc/g++ and clang flags false for libbluetooth; liblc3 is copied from the SRPM", "Switch the GN driver and link policy for libbluetooth; retain separate provenance for liblc3."),
    "netcoredbg": ("test libtest_breakpoint.so is explicitly linked with unqualified g++; the main debug tool uses Clang", "Use the target-configured CXX for the test helper and validate its dynamic symbols."),
    "org.example.gbs-sample": ("SRPM spec selects tizen build-native -c gcc; no standard-profile published log for any architecture", "Archive a verbose build of each packaging variant and capture link markers before stripping."),
    "augeas": ("Autoconf/Libtool linker probes and installed payload markers are different evidence", "Archive a verbose link of the exact affected output and its unstripped ELF."),
    "nnfw": ("Clang build links onert targets; archived closure alone does not attribute each markerless RPM member", "Capture verbose links and markers before post-install for each unmatched ELF."),
    "push": ("published recipe stages copied executables; exact source byte matches prove prebuilt where listed", "Keep the matched binaries separate and obtain provenance for the other files."),
    "stt": ("Clang CMake build plus copied engine payloads", "Keep SHA-matched files separate; capture pre-strip links for remaining exact targets."),
    "tts": ("Clang CMake build plus copied engine payloads", "Keep SHA-matched files separate; capture pre-strip links for remaining exact targets."),
    "voice-control": ("Clang CMake build plus copied engine payloads", "Keep SHA-matched files separate; capture pre-strip links for remaining exact targets."),
    "wakeup-engine-default": ("CMake configures Clang and the package also stages vendor ELF files", "Keep SHA-matched files separate; capture pre-strip links for remaining exact targets."),
    "security-config": ("SRPM contains prebuilt file/readelf test utilities and recipe also configures Clang", "Keep the utilities separate, enabling CMake verbose links for any remaining tests."),
    "mtp-initiator": ("published mtp-initiator-haltests ELF has LLD 22.1.8; staged libmtp has independent source provenance", "Keep haltests and the nested vendor libmtp RPM separate in counts."),
}


def csv_rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        yield from csv.DictReader(stream)


def write_csv(path, records, columns):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        writer.writerows(records)


def recipe_text(package, arch, group):
    if group == "1":
        if package == "rust":
            return ("RPM packages precompiled Rust distribution components by target.",
                    "Track Rust std provenance separately; changing downstream rustc driver flags leaves the installed std provenance.")
        return ("Published rustc invocations and RPM macro settings are recorded; representative replays resolve target defaults.",
                "Set the dedicated Rust driver and explicit Tizen LLD path at the RPM macro boundary. Validate each target before promotion.")
    if group == "6":
        return ("Inspect Kbuild controls and per-module link actions in the kernel table.",
                "Set LLVM=1 or explicit LD=ld.lld in each Kbuild step where target policy requires it; capture V=1 and module ABI checks.")
    if package.startswith("u-boot"):
        return ("dtc and fw_printenv are HOSTLD targets; inspect HOSTCC at the actual stage.",
                "Control HOSTCC/HOSTLDFLAGS separately from target CROSS_COMPILE.")
    if package.endswith("-engine-default"):
        return ("Published image and RPM ELF files match executable members of source tar/TPK where listed.",
                "Track matched vendor ELF provenance; verify any newly linked targets separately.")
    return ROOT_CAUSES.get(package, ("", ""))


def index_sources(data):
    lookup = {}
    for r in csv_rows(data / "rpm-inventory.csv.gz"):
        if r["snapshot"] == SNAPSHOT:
            lookup[r["arch"], r["nevra"]] = r["source"].removesuffix(".src.rpm").rsplit("-", 2)[0]
    return lookup


def linker_class(path, comments, group, source):
    marker = LINKER_MARKER.search(comments)
    if source == "rust" and RUST_STDLIB.search(path):
        return "rust-distribution-std:" + (marker[1] if marker else "marker-absent")
    if marker:
        if marker[1] == "22.1.8":
            return "tizen-lld-22.1.8"
        if group == "1" and marker[1] == "20.1.8" and "e8a2ffcf322f45b8dce82c65ab27a3e2430a6b51" in marker[2]:
            return "rust-bundled-lld-20.1.8"
        return "other-lld:" + marker[1]
    if RUST_ID.search(comments) or CLANG_ID.search(comments) or "GCC:" in comments:
        return "compiler-comment-only"
    return "no-linker-or-compiler-marker"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "evidence", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    logs = {}
    for row in csv_rows(args.evidence / "logs.csv"):
        logs[row["package"], row["arch"]] = row
    groups = {n: r["group"] for (n, _), r in logs.items()}
    groups["org.example.gbs-sample"] = "4"
    trials = defaultdict(list)
    trial_table = args.evidence / "trial-builds.csv"
    if trial_table.exists():
        for item in csv_rows(trial_table):
            trials[item["package"], item["arch"]].append({key: item[key] for key in ("variant", "exit", "evidence")})
    sources = index_sources(args.data)
    paths = defaultdict(Counter)
    per_rpm = defaultdict(Counter)
    std_files = []
    prebuilt = {(r["scope"], r["arch"], r["image"], r["nevra"], r["path"], r["sha256"])
                for r in csv_rows(args.evidence / "source-sha-matches.csv")}
    for scope, filename in (("rpm-pass", "rpm-elf-evidence.csv.gz"), ("image", "image-instances-20261120.082536.csv")):
        for r in csv_rows(args.data / filename):
            if r["snapshot"] != SNAPSHOT or r.get("repository", "Unified") != "Unified":
                continue
            arch, path, sha = r["arch"], r["path"], r["sha256"]
            nevra = r.get("nevra", r.get("rpm_nevra", ""))
            image = r.get("image", "")
            source = sources.get((arch, nevra), r.get("source", "").removesuffix(".src.rpm").rsplit("-", 2)[0])
            source = SOURCE_ALIASES.get(source, source)
            if source not in groups and not RUST_SOURCE.search(source):
                continue
            group = groups.get(source, "1")
            comment = " | ".join((r["comments"], r["debug_comments"]))
            exact_prebuilt = (scope, arch, image, nevra, path, sha) in prebuilt
            label = "source-sha-match" if exact_prebuilt else linker_class(path, comment, group, source)
            if label.startswith("rust-distribution-std"):
                std_files.append(dict(scope=scope, arch=arch, nevra=nevra, path=path, sha256=sha,
                                      marker=label.split(":", 1)[1], comments=comment))
            if label in ("compiler-comment-only", "no-linker-or-compiler-marker"):
                prior = r["evidence_class"]
                if prior in ("gnu-ld-confirmed", "other-linker-confirmed", "not-linked-by-our-toolchain"):
                    label = prior
            paths[source, arch, scope][label] += 1
            per_rpm[group, source, arch, scope, nevra][label] += 1
    write_csv(args.output / "rust-distribution-std.csv", std_files,
              ("scope", "arch", "nevra", "path", "sha256", "marker", "comments"))
    rpm_results = []
    for (group, source, arch, scope, nevra), counts in sorted(per_rpm.items()):
        for label, count in sorted(counts.items()):
            rpm_results.append(dict(group=group, package=source, arch=arch, scope=scope, nevra=nevra,
                                    evidence_class=label, count=count, denominator=sum(counts.values())))
    write_csv(args.output / "binary-rpm-classes.csv", rpm_results,
              ("group", "package", "arch", "scope", "nevra", "evidence_class", "count", "denominator"))

    excerpts = defaultdict(lambda: defaultdict(dict))
    for r in csv_rows(args.evidence / "log-lines.csv.gz"):
        excerpts[r["package"], r["arch"]][r["category"]][int(r["line"])] = r["text"]
    targets = set(logs) | {(n, a) for n, a, _ in paths}
    table, kernels = [], []
    for name, arch in sorted(targets, key=lambda key: (groups.get(key[0], "1"), *key)):
        group = groups.get(name, "1")
        log = logs.get((name, arch), {})
        lines = excerpts[name, arch]
        cause, fix = recipe_text(name, arch, group)
        evidence = {category: sorted(lines[category])[:12] for category in CATEGORY if lines[category]}
        rpm_counts = paths[name, arch, "rpm-pass"]
        image_counts = paths[name, arch, "image"]
        data = dict(group=group, package=name, arch=arch, snapshot=SNAPSHOT, log_url=log.get("url", ""),
                    status="published-log" if log else "no-published-log-in-index",
                    log_lines=json.dumps(evidence, separators=(",", ":")), root_cause_or_scope=cause, proposed_fix=fix,
                    trials=json.dumps(trials[name, arch], separators=(",", ":")),
                    rpm_elf_denominator=sum(rpm_counts.values()),
                    rpm_elf_classes=json.dumps(rpm_counts, sort_keys=True, separators=(",", ":")),
                    image_instance_denominator=sum(image_counts.values()),
                    image_instance_classes=json.dumps(image_counts, sort_keys=True, separators=(",", ":")))
        table.append(data)
        if group == "6" and log:
            ksettings = {}
            for category in ("export", "kernel-build", "linker-select"):
                for number, value in lines[category].items():
                    settings = re.findall(r"\b(?:LLVM|LLVM_IAS|CC|LD|CROSS_COMPILE)=[^\s'\u0022]+", value)
                    if settings:
                        ksettings[number] = " ".join(settings)
            modules = lines["kernel-module"]
            if not modules:
                state = "no-module-link-line"
            elif any("LLVM=1" in line for line in ksettings.values()):
                state = "LLVM=1 occurs; interpret by build phase"
            else:
                state = "module-action-observed; precise linker unresolved in log"
            kernels.append(dict(arch=arch, package=name, url=log["url"], kbuild_settings=json.dumps(ksettings, sort_keys=True),
                                module_link_count_in_excerpt=len(modules), first_module_link_line=min(modules, default=""),
                                first_module_link_text=next(iter(modules.values()), ""), attribution=state))
    write_csv(args.output / "packages.csv", table,
              ("group", "package", "arch", "snapshot", "log_url", "status", "log_lines", "root_cause_or_scope",
               "proposed_fix", "trials", "rpm_elf_denominator", "rpm_elf_classes", "image_instance_denominator", "image_instance_classes"))
    write_csv(args.output / "kernel-modules.csv", kernels,
              ("arch", "package", "url", "kbuild_settings", "module_link_count_in_excerpt", "first_module_link_line",
               "first_module_link_text", "attribution"))
    print(f"{len(table)} source package/arch records, {len(rpm_results)} binary-RPM class rows, {len(kernels)} kernel logs")


if __name__ == "__main__":
    main()
