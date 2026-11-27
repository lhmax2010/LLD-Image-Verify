#!/usr/bin/env python3
"""Verify the public release archive and recompute the archived review results."""
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "history"
OLD = "kernel_lld_verification_20261120"
NEW = "kernel_lld_verification_20261125"
P12 = "phase12_controlled_benchmark"
P13 = "phase13_final_acceptance"
P14 = "phase14_product_runtime_acceptance"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_manifest():
    expected = {}
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in expected and re.fullmatch(r"[0-9a-f]{64}", digest), f"Bad checksum entry: {name}")
        path = ROOT / name
        require(path.resolve().is_relative_to(ROOT) and not path.is_symlink(), f"Out-of-tree checksum path: {name}")
        expected[name] = digest
    files = {p.relative_to(ROOT).as_posix(): p for p in ROOT.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
    require(files.keys() == expected.keys(), "SHA256SUMS coverage differs from archive files")
    require(all(sha(file) == expected[name] for name, file in files.items()), "Archive SHA-256 mismatch")
    manifest = {row["path"]: row for row in csv_rows(ROOT / "FILE_MANIFEST.csv")}
    require(manifest.keys() == files.keys()-{"FILE_MANIFEST.csv"}, "Manifest payload coverage differs")
    for name, row in manifest.items():
        require(row["sha256"] == expected[name] and int(row["bytes"]) == files[name].stat().st_size, f"Manifest data mismatch: {name}")
    return {"files": len(files)+1, "bytes": sum(p.stat().st_size for p in files.values())+(ROOT/"SHA256SUMS").stat().st_size}


ALIASES = {
    row["source_relative"]: row["description"].removeprefix("Identical public bytes stored once at ")
    for row in csv_rows(ROOT / "PUBLICATION_ACTIONS.csv")
    if row["disposition"] == "DEDUPLICATED"
}


def original(name):
    path = HISTORY / name
    if not path.is_file() and name in ALIASES:
        path = ROOT / ALIASES[name]
    require(path.is_file() and path.resolve().is_relative_to(ROOT), f"Unresolved archive input: {name}")
    return path


def read(name):
    return json.loads(original(name).read_text())


def import_script(module_name, name):
    spec = importlib.util.spec_from_file_location(module_name, original(name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_values(actual, expected):
    require(len(actual) == len(expected), "Unexpected summary length")
    for saved, regenerated in zip(actual, expected, strict=True):
        require(saved.keys() == regenerated.keys(), "Unexpected summary schema")
        for field, value in regenerated.items():
            same = (math.isclose(float(saved[field]), value, rel_tol=1e-12, abs_tol=1e-12)
                    if isinstance(value, (int, float)) else saved[field] == ("" if value is None else value))
            require(same, f"Summary field failed to recompute: {field}")


def benchmark_results():
    benchmark = import_script("benchmark_linkers", f"{P12}/scripts/benchmark_linkers.py")
    sys.modules["benchmark_linkers"] = benchmark
    design = read(f"{P12}/evidence/benchmark/design.json")
    raw = csv_rows(original(f"{P12}/LINKER_BENCHMARK_RAW.csv"))
    require(len(raw) == 160 and all(row["status"] == "0" for row in raw), "Original benchmark scope changed")
    groups = Counter((r["profile"], r["pair"], r["linker"]) for r in raw)
    require(len(groups) == 160 and set(groups.values()) == {1}, "Invalid pairing")
    for profile in ("default_threads", "one_cpu_one_thread"):
        for tool in ("bfd", "lld"):
            require([int(row["pair"]) for row in raw if row["profile"] == profile and row["linker"] == tool]
                    == list(range(1, 41)), "Mismatched Phase 12 pair indices")
    staged = [{**r, **{f: (float(r[f]) if f.endswith("_ms") else int(r[f])) for f in benchmark.FIELDS}} for r in raw]
    calculated = benchmark.summary(staged, ("default_threads", "one_cpu_one_thread"), 40, design["seed"])
    check_values(csv_rows(original(f"{P12}/LINKER_BENCHMARK_SUMMARY.csv")), calculated)
    sweep = import_script("thread_sweep_archive", f"{P13}/scripts/thread_sweep.py")
    raw = csv_rows(original(f"{P13}/evidence/threads/measurements.csv"))
    design = read(f"{P13}/evidence/threads/design.json")
    require(len(raw) == 288 and all(r["exit_status"] == "0" for r in raw), "Thread sample scope changed")
    require(Counter((int(r["block"]), r["mode"]) for r in raw) ==
            Counter({(n, v): 1 for n in range(1, 49) for v in sweep.MODES}), "Invalid Phase 13 blocks")
    staged = [{**r, "block": int(r["block"]), **{f: (float(r[f]) if f.endswith("_ms") else int(r[f]))
               for f in sweep.METRICS}} for r in raw]
    thread = sweep.summarize(staged, design["seed"])
    check_values(csv_rows(original(f"{P13}/evidence/threads/summary.csv")), thread)
    lld_sha = {r["output_sha256"] for r in raw if r["mode"].startswith("lld")}
    require(len(lld_sha) == 1, "Thread results used different outputs")
    return {"phase12_samples": 160, "phase12_summary_rows": len(calculated), "phase13_samples": 288,
            "phase13_summary_rows": len(thread), "same_lld_output": next(iter(lld_sha))}


def review_exec():
    trace_prefix = re.compile(r'^execve\((".*?"), (\[(?:"(?:[^"\\]|\\.)*"(?:, )?)*\]), ')
    build = read(f"{P12}/evidence/build/controlled-builds.json")
    a, b = (build["groups"][group] for group in ("A", "B"))
    diff = [key for key in sorted(a["source_files"]) if a["source_files"][key] != b["source_files"][key]]
    require(len(a["source_files"]) == len(b["source_files"]) == 53 and diff == ["kernel/Makefile"],
            "Controlled source difference changed")
    old = original(f"{NEW}/evidence/source/old/Makefile").read_bytes()
    new = original(f"{NEW}/evidence/source/new/Makefile").read_bytes()
    removed = b"LD = ${CROSS_COMPILE}ld\n"
    require(old.count(removed) == 1 and old.replace(removed, b"", 1) == new, "Unexpected Makefile change")
    pairs = [[(r["guest_path"], r["sha256"]) for r in group["ordered_inputs"]] for group in (a, b)]
    frozen = read(f"{P12}/evidence/replay/frozen-inputs.json")["ordered_response_and_objects"]
    require(len(frozen) == 22 and len(pairs[0]) == 19 and pairs[0] == pairs[1] ==
            [(row["guest_path"], row["sha256"]) for row in frozen[1:20]], "Frozen input list mismatch")
    require(a["response"]["sha256"] == b["response"]["sha256"] == frozen[0]["sha256"], "Response digest mismatch")
    versions = []
    for record in (a, b):
        for key in ("intermediate", "final"):
            event = record[key]
            trace = original(P12 + "/" + event["exec_trace"]["path"]).read_text().splitlines()
            observed = []
            for line in trace:
                match = trace_prefix.match(line)
                if (match and re.search(r"=\s*0\s*$", line) and
                        str(PurePosixPath(json.loads(match[1]))) == event["executable"]):
                    observed.append(json.loads(match[2]))
            require(observed == [event["argv"]] and event["exit_status"] == 0 and
                    any(line.startswith("exit_group(0)") for line in trace),
                    f"Actual exec or exit evidence does not match: {key}")
            require(re.fullmatch(r"[0-9a-f]{64}", event["executable_sha256"]), "Missing linker payload digest")
            versions.append(event["version"])
    require(versions == ["GNU BFD 2.43", "LLVM LLD 22.1.8", "LLVM LLD 22.1.8", "LLVM LLD 22.1.8"],
            "Unexpected LLVM version chain")
    replay = read(f"{P12}/evidence/replay/link-replay.json")
    for group, binary in ((a,"bfd"), (b,"lld")):
        require(group["intermediate_object"]["sha256"] == replay["products"][binary]["intermediate"]["sha256"],
                "Replayed composite does not match controlled output")
    return {"e4_links": len(versions), "linker_sequence": versions, "frozen_objects": len(pairs[0])}


def validate_sizes_and_gcc():
    tbl = csv_rows(original(f"{P13}/INTERMEDIATE_SIZE_ATTRIBUTION.csv"))
    require(tbl[-1]["category"] == "TOTAL", "Missing physical size total")
    sums = [sum(int(row[k]) for row in tbl[:-1]) for k in ("bfd_file_bytes", "lld_file_bytes", "file_delta_bytes")]
    require(sums == [2505192, 1998564, -506628], "Physical size delta does not reconcile")
    debug = sum(int(row["file_delta_bytes"]) for row in tbl if row["section_or_region"] == ".debug_str")
    require(debug == -506147 and sums[2]-debug == -481, "Debug versus other size deltas differ")
    case = read(f"{P12}/evidence/elf/frozen-stripped.json")
    require(case["right"]["size"]-case["left"]["size"] == -1292, "Frozen final size difference changed")
    mapping = read(f"{P13}/evidence/review/mapping-stripped-review.json")
    markers = [mark for row in mapping for mark in row["removed"]]
    require(len(markers) == 81 and all(row["effective_spans_equal"] for row in mapping) and
            all(mark["kind"] == "d" for mark in markers), "ARM final mapping semantics differ")
    gcc = read(f"{P12}/evidence/gcc/status.json")
    require(gcc["architecture"] == "ARMv7l non-RT" and gcc["gcc_compatibility"] == "PASS", "Wrong GCC scope")
    for row in gcc["runs"].values():
        pair = []
        for ref in row["linker_execution_receipts"]:
            actual = read(f"{P12}/{ref}")
            require(all(v["exit_status"] == 0 and v["linker"] == "GNU BFD 2.43" and "execve(" in v["exec_trace"]
                        for v in actual.values()), "Missing successful real GCC/BFD event")
            entries = read(f"{P12}/{PurePosixPath(ref).parent}/artifacts.json")["installed_modules"]
            require(len(entries) == 7, "Unexpected GCC installed module scope")
            pair.append({path: r["sha256"] if isinstance(r, dict) else r for path, r in entries.items()})
        require(len(pair) == 2 and pair[0] == pair[1], "GCC pair output digests differ")
    require(len(gcc["runs"]) == 3, "GCC comparison count differs")
    return {"intermediate_delta_bytes": sums[2], "debug_delta_bytes": debug, "final_delta_bytes": -1292,
            "avoided_arm_data_markers": len(markers), "gcc_pairs": len(gcc["runs"])}


def runtime_findings():
    runtime = read(f"{P14}/evidence/runtime-result.json")
    inv = csv_rows(original(f"{P14}/evidence/module-runtime-to-rpm.csv"))
    require(len(inv) == 59 and Counter(r["group"] for r in inv) == {"in-tree": 52, "out-of-tree": 7}, "Module scope differs")
    require(all(r["new_qb_file_match"] == "PASS" and r["published_module_sha256"] == r["device_module_sha256"]
                for r in inv), "Runtime module comparison mismatch")
    require(runtime["KERNEL_BOOT"] == "PASS" and runtime["kdbus"]["sysfs"]["initstate"] == "live" and
            runtime["FUNCTIONAL_REGRESSION"] == "NOT_RUN_NO_APPROVED_CASE_AVAILABLE" and
            runtime["PRODUCT_MERGE_READINESS"] == "PENDING", "Runtime acceptance fields differ")
    return {"runtime_matched_modules": len(inv), "kdbus_state": "live", "product_merge": "PENDING"}


def main():
    result = (archive_manifest() | benchmark_results() | review_exec() |
              validate_sizes_and_gcc() | runtime_findings())
    print(json.dumps(result, indent=2))
    print("PASS: archive checksums, two benchmark datasets, linker evidence, sizes, GCC and runtime gates")


if __name__ == "__main__":
    main()
