#!/usr/bin/env python3
"""Join package logs with image ELF classes and summarize compiler and linker settings."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from importlib import import_module
import json
from pathlib import Path
import re

image = import_module("export-image-evidence")
ROOT_VERSION = re.compile(r"\b(clang|llvm|libllvm|binutils|gcc)-(\d[\w.+~-]*-[\w.+~-]+)\b")
EXEC_GCC = re.compile(r"""\b(?:CC|CXX)=["']?(?:[^\s"'=]*/)?(?:[\w.]+-)*(?:gcc|g\+\+)(?:-\d[^\s"']*)?(?:\s|["']|$)""")
EXEC_CLANG = re.compile(r"""\b(?:CC|CXX)=["']?(?:[^\s"'=]*/)?(?:[\w.]+-)*clang(?:\+\+)?(?:-\d[^\s"']*)?(?:\s|["']|$)""")
START = re.compile(r'started "build[^"]*" at (.+ UTC \d{4})')
GCC_RECIPES = {"gcc", "gcc-aarch64", "gcc-armv7hl", "gcc-armv7l", "gcc-riscv64", "glibc"}
SNAPSHOT_DATE = re.compile(r"_(\d{8})\.")
CATEGORIES = ("root_toolchain", "cc_cxx_export", "cmake_compiler", "meson_compiler",
              "meson_host_linker", "linker_override", "linker_probe", "llvm_configuration",
              "configure_compiler", "root_start")


def compact(entries, max_entries=8):
    excerpts = [f"L{entry['first_line']} {entry['text']}" for entry in entries[:max_entries]]
    if len(entries) > max_entries:
        excerpts.append(f"{len(entries) - max_entries} further distinct lines in buildlog-lines.csv.gz")
    return " | ".join(excerpts)


def compiler_kind(entries):
    text = lambda key: "\n".join(e["text"] for e in entries[key])
    exports = text("cc_cxx_export")
    ids = text("cmake_compiler") + "\n" + text("meson_compiler")
    gcc = bool(EXEC_GCC.search(exports) or re.search(r"identification is GNU |machine: .*\(gcc ", ids))
    clang = bool(EXEC_CLANG.search(exports) or re.search(r"identification is (?:Apple)?Clang |machine: .*\(clang ", ids))
    if gcc and clang:
        return "GCC and Clang"
    if gcc:
        return "GCC"
    if clang:
        return "Clang"
    return "compiler selection not recorded by extracted signals"


def source_counts(data):
    counts = defaultdict(Counter)
    for unified, _ in image.ROUNDS.values():
        path = data / f"image-instances-{unified}.csv"
        for r in image.rows(path):
            if not r["source"] or r["evidence_class"] == "static-archive":
                continue
            snapshot = r["base_snapshot"] if r["repository"] == "Base" else r["snapshot"]
            key = (snapshot, r["arch"], r["source"].rsplit("/", 1)[1])
            counts[key][r["evidence_class"]] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    quotes = defaultdict(lambda: defaultdict(list))
    for r in image.rows(args.logs / "buildlog-lines.csv"):
        # Root setup entries are included in the full excerpt table.
        if r["category"] in CATEGORIES:
            quotes[r["url"]][r["category"]].append(r)
    elf = source_counts(args.data)
    output = []
    spans = defaultdict(list)
    for r in image.rows(args.logs / "buildlogs.csv"):
        entries = quotes[r["url"]]
        versions = defaultdict(set)
        for entry in entries["root_toolchain"]:
            text = entry["text"]
            if "cumulate " not in text and "#" not in text and not re.search(r"installing |keeping |updating ", text):
                continue
            for pkg, version in ROOT_VERSION.findall(text):
                versions[pkg].add(version)
        effect = (r["snapshot"], r["arch"], r["package"])
        root_start = next((START.search(line["text"]) for line in entries["root_start"] if
                           START.search(line["text"])), None)
        start = datetime.strptime(root_start[1], "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=timezone.utc) if root_start else None
        if start and r["repository"] == "Base" and r["duration_seconds"]:
            date = datetime.strptime(SNAPSHOT_DATE.search(r["snapshot"])[1], "%Y%m%d").replace(tzinfo=timezone.utc)
            if date <= start < date + timedelta(days=2):
                spans[r["snapshot"], r["arch"]].append((start, start + timedelta(seconds=int(r["duration_seconds"]))))
        compiler = compiler_kind(entries)
        gcc_only = ""
        if r["repository"] == "Base":
            if compiler == "GCC" and r["package"] in GCC_RECIPES:
                gcc_only = "yes"
            elif compiler == "Clang":
                gcc_only = "no"
            else:
                gcc_only = "undetermined"
        output.append(dict(
            **{key: r[key] for key in ("repository", "snapshot", "arch", "status", "package", "url",
                                        "sha256", "lines", "duration_seconds", "error")},
            build_start_utc=start.isoformat() if start else "",
            **{f"root_{key}_evr": " | ".join(sorted(versions[key])) for key in ("clang", "llvm", "libllvm", "binutils", "gcc")},
            compiler_observed=compiler, gcc_only_by_recipe=gcc_only,
            **{key: compact(entries[key], 4) for key in CATEGORIES if key != "root_start"},
            image_elf_instances=sum(elf[effect].values()),
            image_elf_evidence_counts=json.dumps(elf[effect], sort_keys=True),
        ))
    image.write_csv(args.data / "buildlog-package-evidence.csv", output)
    base_roots = [r for r in output if r["repository"] == "Base"]
    image.write_csv(args.data / "base-build-roots.csv", base_roots)
    by_toolchain = defaultdict(Counter)
    for row in base_roots:
        if row["image_elf_instances"]:
            key = row["snapshot"], row["arch"], row["root_clang_evr"], row["compiler_observed"]
            by_toolchain[key].update(json.loads(row["image_elf_evidence_counts"]))
    image.write_csv(args.data / "base-image-cross-check.csv", [
        dict(snapshot=snapshot, arch=arch, clang_build_root=clang, compiler=compiler,
             evidence_class=category, instances=count, denominator=sum(counts.values()))
        for (snapshot, arch, clang, compiler), counts in sorted(by_toolchain.items())
        for category, count in sorted(counts.items())
    ])
    image.write_csv(args.data / "base-build-window.csv", [
        dict(snapshot=snapshot, arch=arch, logs_in_build_window=len(times),
             first_build_start=min(t[0] for t in times).isoformat(),
             last_build_end=max(t[1] for t in times).isoformat(),
             span_minutes=round((max(t[1] for t in times) - min(t[0] for t in times)).total_seconds() / 60, 1))
        for (snapshot, arch), times in sorted(spans.items())
    ])


if __name__ == "__main__":
    main()
