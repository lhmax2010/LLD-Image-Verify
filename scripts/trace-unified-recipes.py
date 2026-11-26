#!/usr/bin/env python3
"""Extract numbered toolchain, link, and package-provenance lines from Unified build logs."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gzip
import hashlib
from importlib import import_module
import json
from pathlib import Path
import re

log_tools = import_module("sweep-buildlogs")
SNAPSHOT = "tizen-unified-toolchain_20261120.082536"
GROUPS = {
    1: r"^(rust(?:-|$)|rpc-port$|bundle$|appcore-agent$|capi-appfw-|pkgmgr-server$)",
    2: r"^(nntrainer|yaca|onnxruntime|openblas|lapack|hdf5)$",
    3: r"^(angle|libangle)$",
    4: r"^(chromium-efl|emuld|fluoride|netcoredbg|u-boot(?:-[\w.-]+)?|org\.example\.gbs-sample|gbs-sample)$",
    5: r"^(augeas|nnfw|push|stt|tts|voice-control|wakeup-engine-default|security-config|mtp-initiator|org\.tizen\.(?:stt|tts|vc)-engine-default)$",
    6: r"^(linux-(?:jetson|nv|qc|hwpm|amlogic|tizen-modules|rpi)|nv-kernel-display-driver|qc-(?:camera|graphics|video)-kernel|(?:arm64-|arm-)?rpi4-linux-kernel)",
}
RULES = {
    "rust-settings": r"\b(?:RUSTFLAGS|CARGO_ENCODED_RUSTFLAGS|CARGO_TARGET_\w+_LINKER|RUSTC_LINKER)\s*=|\.cargo/config|rustc_std_build|rustc_sysroot|-C\s*link(?:er(?:-flavor|-features)?|-(?:args?|self-contained))\s*=",
    "rust-command": r"\+ (?:\S*/)?rustc(?:\s|$)|rustc .*--crate-(?:name|type)(?:=| )",
    "rust-component": r"components=rustc,|installing component .rust-std|\+ .*\brust-1\.90\.0.*\.tar",
    "export": r"\+ export (?:[^;&]*?\s)?(?:CC|CXX|LD|FC|LLVM)=",
    "meson-linker": r"linker for the host machine:",
    "cmake": r"compiler identification is|\+ cmake (?:-\S|\.)",
    "gn": r"gcc_solink_wrapper|(?:is_clang|use_lld|custom_toolchain|target_toolchain|host_toolchain|is_gcc)\s*=|gn gen",
    "driver-link": r"(?:^|\s)(?:\S*/)?(?:[\w.-]+-)?(?:gcc|g\+\+|clang(?:\+\+)?|gfortran|ld(?:\.(?:lld|bfd|gold))?)(?:-[0-9]+)?\s+.*(?:-shared\b|-Wl,|--start-group|--version|-o\s+(?!\S+\.(?:o|s)(?:\s|$)))",
    "linker-select": r"-fuse-ld=|--ld-path=|\b(?:CMAKE_LINKER|RUSTC_LINKER|KBUILD_LDFLAGS|LD|CC|LLVM)=(?:[^\s]+)|checking (?:if|whether) the linker|\bGNU ld\b|\bLLD \d",
    "kernel-module": r"\bLD\s+\[M\]\s+.*\.ko(?:\s|$)",
    "kernel-build": r"(?:\+ (?:\S*/)?make\b.*(?:ARCH=|CROSS_COMPILE=|LLVM=|LLVM_IAS=|\bLD=|\bCC=|\bmodules\b)|\b(?:LD|AS|CC|AR)\s+(?:vmlinux|built-in\.a)\b)",
    "target": r"Linking (?:C|CXX) (?:shared|executable)|Linking.*(?:\.so|\bdtc\b|\bfw_printenv\b)|\b(?:HOSTLD|LD)\s+(?:.*\.so|.*(?:dtc|fw_printenv))\b",
    "named-target": r"liblc3|libbluetooth\b|libnnfw|haltests|[\w-]+_getengine|lib(?:stt|tts|vc)[\w-]*engine|tizen_clang|tizen_x64|libyaca\.so|libonnxruntime\.so|libopenblas\.so|libhdf5_fortran\.so|/tools/(?:dtc|fw_printenv)|dlog\.so|\.\./[^\s]*/(?:libnetcoredbg|libtest)\.so",
    "strip": r"(?:remove-section|strip-section).{0,12}\.comment|\b(?:strip|llvm-strip|eu-strip)\s.*(?:strip-all|--strip|\.so)|find-debuginfo",
    "install-copy": r"\+ (?:install|cp) .*?(?:\.so(?:[.\w]+)?|\.tpk|\.ko|start4[^ ]*\.elf|_getengine|/pushd)|(?:Installing:|extracting debug info from).*(?:\.so|/bin/)",
}
SELECT = re.compile("|".join(f"(?:{pattern})" for pattern in RULES.values()), re.I)
CATEGORIES = {name: re.compile(pattern, re.I) for name, pattern in RULES.items()}
STAMP = re.compile(r"^\[\s*\d+s\]\s*")


def inspect(row, group, work):
    package, arch, url = (row[key] for key in ("package", "arch", "url"))
    receipt = work / f"{arch}-{package}.json"
    if receipt.exists():
        return json.loads(receipt.read_text())
    excerpts = defaultdict(list)
    count = 0
    raw = log_tools.fetch(url)
    digest = hashlib.sha256(raw).hexdigest()
    for number, line in enumerate(raw.split(b"\n"), 1):
        line = STAMP.sub("", line.decode(errors="replace").rstrip())
        if not SELECT.search(line) or log_tools.SECRET.search(line):
            continue
        count += 1
        limit = 100 if group == 1 else 70
        for name, pattern in CATEGORIES.items():
            bucket = excerpts[name]
            if len(bucket) < limit and pattern.search(line):
                bucket.append([number, line])
    result = dict(group=group, arch=arch, package=package, url=url, sha256=digest,
                  prior_log_same=digest == row["sha256"], matched_lines=count, excerpts=excerpts)
    receipt.write_text(json.dumps(result) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--group", type=int, choices=tuple(GROUPS), action="append")
    parser.add_argument("--workers", type=int, default=18)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out / "receipts"
    cache.mkdir(exist_ok=True)
    targets = []
    with (args.data / "buildlogs.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["snapshot"] != SNAPSHOT:
                continue
            for group in args.group or GROUPS:
                if re.match(GROUPS[group], row["package"]):
                    targets.append((row, group))
    print(f"{len(targets)} published logs selected", flush=True)
    results, errors = [], []
    with ThreadPoolExecutor(args.workers) as pool:
        calls = {pool.submit(inspect, row, group, cache): (row, group) for row, group in targets}
        for call in as_completed(calls):
            try:
                results.append(call.result())
            except OSError as error:
                row, group = calls[call]
                errors.append(dict(group=group, package=row["package"], arch=row["arch"],
                                   url=row["url"], error=str(error)))
    columns = ["group", "package", "arch", "url", "sha256", "prior_log_same", "matched_lines"]
    with ((args.out / "logs.csv").open("w", newline="") as inventory,
          gzip.open(args.out / "log-lines.csv.gz", "wt", newline="") as output):
        logs = csv.DictWriter(inventory, columns, extrasaction="ignore")
        logs.writeheader()
        lines = csv.writer(output)
        lines.writerow(["group", "package", "arch", "url", "line", "category", "text"])
        for result in sorted(results, key=lambda row: (row["group"], row["package"], row["arch"])):
            logs.writerow(result)
            for kind, items in result["excerpts"].items():
                for number, text in items:
                    lines.writerow([*(result[key] for key in columns[:4]), number, kind, text])
    (args.out / "errors.json").write_text(json.dumps(errors, indent=2) + "\n")
    print(f"{len(results)} logs read, {len(errors)} failures", flush=True)


if __name__ == "__main__":
    main()
