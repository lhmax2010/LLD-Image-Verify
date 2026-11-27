#!/usr/bin/env python3
"""Bind Phase 12 runtime feasibility analysis to archived Tizen RPM inputs."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import re
import struct
import subprocess
import tarfile
from tempfile import TemporaryDirectory

RUN = Path(__file__).resolve().parents[1]
WORKSPACE = RUN.parent
OLD = WORKSPACE / "kernel_lld_verification_20261120"
NEW = WORKSPACE / "kernel_lld_verification_20261125"
OUT = RUN / "evidence/runtime"
REVISION = "platform/kernel/linux-rpi#42aeefac58edeb081aff440f0b60be71cbe49755"
SDK_PREFIX = "boot/kernel/devel/kernel-devel-arm-rpi4/"
DEBUG_PREFIX = "usr/src/debug/rpi4-linux-kernel-6.12.80-0.arm/"
SOURCES = (
    "kernel/module/main.c",
    "kernel/module/kallsyms.c",
    "kernel/module/internal.h",
    "kernel/module/strict_rwx.c",
    "kernel/kallsyms.c",
    "arch/arm/kernel/module.c",
    "arch/arm/kernel/module-plts.c",
    "arch/arm/include/asm/page.h",
    "include/linux/module.h",
    "mm/vmalloc.c",
)
CONFIG_KEYS = (
    "MODULES", "MODULE_UNLOAD", "KALLSYMS", "KALLSYMS_ALL", "MODULES_USE_ELF_REL",
    "ARM", "ARM_THUMB", "THUMB2_KERNEL", "ARM_MODULE_PLTS", "ARM_LPAE", "CPU_BIG_ENDIAN",
    "MMU", "PAGE_SIZE_4KB", "PAGE_SHIFT", "ARCH_WANTS_MODULES_DATA_IN_VMALLOC", "LIVEPATCH", "STRICT_MODULE_RWX", "MODVERSIONS", "MODULE_SIG", "MODULE_DECOMPRESS",
    "MODULE_COMPRESS", "MODULE_COMPRESS_NONE", "DEBUG_INFO_BTF_MODULES", "LTO_NONE",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"{path}: SHA-256 {actual} differs from {expected}")
    return actual


def rpm_members(rpm):
    result = subprocess.check_output(
        ["rpm", "-qp", "--qf", "[%{FILENAMES}\t%{FILEDIGESTS}\n]", rpm], text=True)
    return dict(line.split("\t", 1) for line in result.splitlines())


def extract_rpm(rpm, target, members):
    with subprocess.Popen(["rpm2cpio", rpm], stdout=subprocess.PIPE) as archive:
        patterns = [item for member in members for item in (member, "./" + member)]
        subprocess.run(["cpio", "-idm", "--quiet", "--no-absolute-filenames", *patterns],
                       cwd=target, stdin=archive.stdout, check=True)
        if archive.wait():
            raise RuntimeError(f"rpm2cpio failed for {rpm}")
    digests = rpm_members(rpm)
    for member in members:
        verify(target / member, digests.get(member, digests.get("/" + member)))


def source_records(rows):
    source = rows["KERNEL_SRPM"]
    prior_debug = rows["KERNEL_DEBUGSOURCE"]
    src = OLD / "evidence/repository/rpms" / source["filename"]
    debug = OLD / "evidence/repository/rpms" / prior_debug["filename"]
    for rpm in (src, debug):
        vcs = subprocess.check_output(["rpm", "-qp", "--qf", "%{VCS}", rpm], text=True)
        if vcs != REVISION:
            raise ValueError(f"Unexpected source revision for {rpm}: {vcs}")
    verify(src, source["published_checksum"])
    verify(debug, prior_debug["old_metadata_checksum"])
    expected = set(SOURCES)
    extracted = OUT / "source"
    extracted.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".kernel-source-", dir=OUT) as scratch:
        temp = Path(scratch)
        member_names = rpm_members(src)
        patch_names = sorted(name for name in member_names if ".patch" in name or ".diff" in name)
        tar_name = "linux-kernel-6.12.80.tar.xz"
        spec = "linux-rpi.spec"
        extract_rpm(src, temp, [tar_name, spec, *patch_names])
        applied = (temp / spec).read_text()
        (extracted / spec).write_text(applied)
        declared = dict(re.findall(r"^Patch(\d+):\s+([^\s]+)", applied, re.M))
        patch_order = [declared[index] for index in re.findall(r"^%patch(\d+) -p1$", applied, re.M)]
        if set(patch_order) != set(patch_names) or len(patch_order) != len(patch_names):
            raise ValueError("Patch member list and SPEC prep order differ")
        patches = {}
        for patch in patch_order:
            path = temp / patch
            patch_bytes = path.read_bytes()
            if path.suffix == ".gz":
                patch_bytes = gzip.decompress(patch_bytes)
            touched = set(re.findall(
                rb"^(?:---|\+\+\+) [ab]/([^\s]+)", patch_bytes, re.M
            ))
            patches[patch] = {
                "diff_paths": len(touched),
                "inspected_source_files_modified": sorted(
                    name.decode() for name in touched if name.decode() in expected),
                "sha256": sha(path),
            }
        source_hashes = {}
        with tarfile.open(temp / tar_name, mode="r|xz") as archive:
            for member in archive:
                relative = member.name.partition("/")[2]
                if relative not in expected:
                    continue
                item = extracted / relative
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_bytes(archive.extractfile(member).read())
                source_hashes[relative] = {
                    "srpm_tar_member": member.name,
                    "srpm_member_before_patches_sha256": sha(item),
                }
        if source_hashes.keys() != expected:
            raise ValueError("Matched source files missing in SRPM tar")
        for patch, detail in patches.items():
            paths = detail["inspected_source_files_modified"]
            if paths:
                path = temp / patch
                patch_bytes = path.read_bytes()
                if path.suffix == ".gz":
                    patch_bytes = gzip.decompress(patch_bytes)
                argv = ["git", "apply", "-p1", *[f"--include={name}" for name in paths], "-"]
                subprocess.run(argv, cwd=extracted, input=patch_bytes, check=True)
                detail["command"] = argv
                detail["exit_status"] = 0
        for relative in source_hashes:
            source_hashes[relative]["sha256"] = sha(extracted / relative)
        prior_members = rpm_members(debug)
        available = [DEBUG_PREFIX + src for src in SOURCES if "/" + DEBUG_PREFIX + src in prior_members]
        extract_rpm(debug, temp, available)
        for member in available:
            relative = member.removeprefix(DEBUG_PREFIX)
            verify(temp / member, source_hashes[relative]["sha256"])
            source_hashes[relative]["old_debugsource_byte_match"] = True
    return {
        "kernel_revision": REVISION,
        "kernel_srpm": str(src.relative_to(WORKSPACE)),
        "kernel_srpm_published_sha256": source["published_checksum"],
        "new_debugsource_published_url": prior_debug["download_url"],
        "new_debugsource_published_sha256": prior_debug["published_checksum"],
        "old_debugsource": str(debug.relative_to(WORKSPACE)),
        "old_debugsource_published_sha256": prior_debug["old_metadata_checksum"],
        "sources": source_hashes,
        "spec_patches_scanned": patches,
    }


def xz_payload_measurement(path):
    data = path.read_bytes()

    def header_end(offset):
        if data[offset:offset + 4] != bytes.fromhex("8eade801"):
            raise ValueError(f"Missing RPM header at byte {offset} in {path}")
        index_count, size = struct.unpack_from(">II", data, offset + 8)
        return offset + 16 + 16 * index_count + size

    if data[:4] != bytes.fromhex("edabeedb"):
        raise ValueError(f"Invalid RPM lead in {path}")
    offset = header_end((header_end(96) + 7) & ~7)
    payload = data[offset:]
    if not payload.startswith(bytes.fromhex("fd377a585a00")):
        raise ValueError(f"No XZ payload at RPM payload offset {offset}")
    archive = lzma.decompress(payload, format=lzma.FORMAT_XZ)
    if not archive.startswith(b"070701") or b"TRAILER!!!" not in archive[-1024:]:
        raise ValueError(f"Unexpected payload contents in {path}")
    return {"xz_payload_offset": offset, "xz_payload_bytes": len(payload),
            "decompressed_cpio_bytes": len(archive)}


def published_artifacts(rows, phase11):
    sdk = NEW / "evidence/repository/rpms" / rows["KERNEL_DEV"]["filename"]
    verify(sdk, rows["KERNEL_DEV"]["published_checksum"])
    config = NEW / phase11["sdk_identity"]["new"]["config"]["path"]
    verify(config, rpm_members(sdk)["/" + SDK_PREFIX + ".config"])
    config_text = config.read_text()
    (OUT / "sdk-config.selected").write_text("".join(
        line + "\n"
        for line in config_text.splitlines()
        if any(line.startswith((f"CONFIG_{key}=", f"# CONFIG_{key} is not set"))
               for key in CONFIG_KEYS)))
    packages = {}
    out = rows["OUT_OF_TREE_MODULES"]
    for side, archive in (("old", OLD), ("new", NEW)):
        rpm = archive / "evidence/repository/rpms" / out["filename"]
        expected = out["old_metadata_checksum" if side == "old" else "published_checksum"]
        verify(rpm, expected)
        format_row = subprocess.check_output(
            ["rpm", "-qp", "--qf", "%{PAYLOADFORMAT}\t%{PAYLOADCOMPRESSOR}\t%{PAYLOADFLAGS}\t%{SIZE}", rpm],
            text=True).split("\t")
        packages[side] = {"sha256": expected, "bytes": rpm.stat().st_size,
                          "payload_format": format_row[0], "payload_compressor": format_row[1],
                          "payload_flags": format_row[2], "rpm_size_tag_bytes": int(format_row[3]),
                          **xz_payload_measurement(rpm)}
    return {"kernel_sdk_sha256": sha(sdk), "kernel_sdk_config_sha256": sha(config),
            "out_of_tree_rpms": packages}


def is_mapping(symbol):
    return (symbol["defined"] and symbol["binding"] == "LOCAL" and symbol["type"] == "NOTYPE"
            and symbol["size"] == 0 and re.fullmatch(r"\$[adt](?:\..+)?", symbol["name"]))


def module_mapping(parsed):
    sections = {section["name"]: section for section in parsed["sections"]}
    markers = Counter((symbol["section"], symbol["value"], symbol["name"][1])
                      for symbol in parsed["symbols"] if is_mapping(symbol))
    executable = Counter({key: count for key, count in markers.items()
                          if sections[key[0]]["flags"] & 0x4})
    init_sections = (".init", ".ARM.extab.init", ".ARM.exidx.init")
    discarded_sections = {".modinfo", "__versions"}
    # ARM's module_init_section() controls the prefixes. The loader clears
    # SHF_ALLOC on modinfo and versions, and specially retains per-CPU symbols
    # under KALLSYMS_ALL. The observed modules contain no per-CPU mapping.
    eligible = Counter({
        key: count for key, count in markers.items()
        if key[0] == ".data..percpu" or (
            sections[key[0]]["flags"] & 0x2 and key[0] not in discarded_sections
            and not key[0].startswith(init_sections))
    })
    return sections, markers, executable, eligible


def published_mapping_sample():
    parsed = NEW / "evidence/binary/parsed"
    paths = sorted(p.relative_to(parsed / "old") for p in (parsed / "old/extra").rglob("*.ko.json"))
    if len(paths) != 7 or any(not (parsed / "new" / p).is_file() for p in paths):
        raise ValueError("Expected the seven same-RPM modules in the matched archive")
    results = {}
    for path in paths:
        sides = tuple(json.loads((parsed / side / path).read_text()) for side in ("old", "new"))
        for side in sides:
            artifact = NEW / side["artifact"]
            verify(artifact, side["elf_sha256"])
        left, right = (module_mapping(side) for side in sides)
        removed = left[1] - right[1]
        added = right[1] - left[1]
        results[str(path).removesuffix(".json")] = {
            "identical_packaged_elf_bytes": sides[0]["elf_sha256"] == sides[1]["elf_sha256"],
            "elfs": [{"sha256": side["elf_sha256"], "bytes": side["elf_size"]}
                     for side in sides],
            "symtab_section_flags": [item[0][".symtab"]["flags"] for item in (left, right)],
            "mapping_counts": [{kind: sum(count for key, count in item[1].items() if key[2] == kind)
                                for kind in "adt"} for item in (left, right)],
            "mapping_counts_eligible_under_core_filter": [sum(left[3].values()), sum(right[3].values())],
            "executable_section_marker_multisets_equal": left[2] == right[2],
            "removed": {name: sum(count for key, count in removed.items() if key[0] == name)
                        for name in sorted({key[0] for key in removed})},
            "removed_core_filter_eligible": sum((left[3] - right[3]).values()),
            "removed_map_classes": sorted({key[2] for key in removed}),
            "added_map_classes": sorted({key[2] for key in added}),
        }
    output = {
        "scope": "Phase 11 packaged seven-module comparison. Both QB environments differ.",
        "interpretation": "Historical observation only. Core-filter counts are a source/ELF eligibility model.",
        "modules": results,
    }
    (OUT / "published-module-mapping-sample.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n")


def controlled_sibling_sample():
    # Compare the seven installed/stripped modules from the same Phase 12 run.
    # The two success receipts and logs bind artifact checks to build stages.
    root_suffix = "home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0"
    extra_suffix = "lib/modules/6.12.80-arm-rpi4-v7l/extra"
    installed = [RUN / "work" / group / root_suffix / extra_suffix for group in ("A", "B")]
    relatives = sorted(path.relative_to(installed[0]) for path in installed[0].rglob("*.ko"))
    if len(relatives) != 7 or set(relatives) != {
        path.relative_to(installed[1]) for path in installed[1].rglob("*.ko")
    }:
        raise ValueError("Both controlled build install trees must contain the same seven modules")
    modules = {}
    for module in relatives:
        files = [root / module for root in installed]
        lengths = [file.stat().st_size for file in files]
        hashes = [sha(file) for file in files]
        modules[str(module)] = {"bytes_A_B": lengths, "sha256_A_B": hashes,
                                "identical": hashes[0] == hashes[1]}
    build_context = {}
    for group in ("A", "B"):
        log = RUN / f"evidence/build/{group}-build.out"
        receipt = log.with_suffix(".cmd.json")
        if json.loads(receipt.read_text())["exit_status"]:
            raise ValueError(f"Group {group} did not build successfully")
        targets = {str(i): line.strip().split()[-1] for i, line in enumerate(log.read_text().splitlines(), 1)
                   if re.match(r"^\s+LD \[M\].*\.o$", line)}
        build_context[group] = {"log": str(log.relative_to(RUN)), "log_sha256": sha(log),
                                "intermediate_ld_targets": targets, "receipt_sha256": sha(receipt)}
    result = {
        "scope": "Phase 12 same build A/B seven-module sample after modules_install with strip",
        "modules": modules,
        "build_context": build_context,
    }
    (OUT / "controlled-seven-module-sample.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"PASS: {len(modules)} controlled modules sampled, {sum(m['identical'] for m in modules.values())} unchanged byte-for-byte")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controlled-sample", action="store_true", help="compare existing Phase 12 A/B install outputs")
    if parser.parse_args().controlled_sample:
        controlled_sibling_sample()
        return
    with (NEW / "11A_RPM_INVENTORY.csv").open(newline="") as stream:
        rows = {row["role"]: row for row in csv.DictReader(stream)
                if row["role"] in ("KERNEL_SRPM", "KERNEL_DEBUGSOURCE", "KERNEL_DEV", "OUT_OF_TREE_MODULES")}
    phase11 = json.loads((NEW / "11A_QB_IDENTITY.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    result = source_records(rows) | published_artifacts(rows, phase11)
    (OUT / "provenance.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    published_mapping_sample()
    print(f"PASS: matched SRPM, {len(result['sources'])} source files, SDK config, and two published RPMs")


if __name__ == "__main__":
    main()
