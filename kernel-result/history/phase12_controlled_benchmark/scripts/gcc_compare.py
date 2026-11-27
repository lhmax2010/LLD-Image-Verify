#!/usr/bin/env python3
"""Reconcile GCC/BFD execution, ABI, and pair-wise build products."""
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from gcc_build import ACCEL_RPM, EVIDENCE, OLD_ROOT, PREFIX, ROOT, SDK, WORK, bubblewrap, digest, dump, run

sys.path.insert(0, str(ROOT.parent / "kernel_lld_verification_20261125/scripts"))
from elf32_module import parse_module, readelf_arm_names

RELEASE = "6.12.80-arm-rpi4-v7l"
TARGETS = ("kdbus.o", "kdbus.ko")
GNU = "GNU BFD 2.43"


def expect(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def execution(group):
    folder = EVIDENCE / "builds" / group
    want_exe = PREFIX + "ld" if group.endswith("-prefix") else "/usr/bin/ld"
    tool_hashes = read_json(EVIDENCE / "tool-hashes.json")
    accelerated = group.endswith("-accel")
    actual_exe = "/emul//usr/bin/ld" if accelerated else want_exe
    if accelerated:
        actual_path = WORK / "rpm-extract" / ACCEL_RPM / "emul/usr/bin/ld"
        identity = digest(actual_path)
        expect(identity == "1bcdd64ed3e5465da8431e46787dd1d04d584f0e243203643c921db427ad406f",
               "Pinned accelerated BFD payload hash")
        tool_hashes[actual_exe] = {"source_rpm": ACCEL_RPM, "sha256": identity, "resolved_path": "/emul/usr/bin/ld"}
    results = {}
    expect(read_json(folder / "make.cmd.json")["exit_status"] == 0 and
           read_json(folder / "install.cmd.json")["exit_status"] == 0,
           f"Build or install failure {group}")
    with gzip.open(folder / "make.strace.gz", "rt") as events:
        trace = events.readlines()
    pending = {}
    for index, item in enumerate(trace):
        pid = item.partition(" ")[0]
        if "execve(" in item and item.rstrip().endswith("<unfinished ...>"):
            pending[pid] = index
        if "<... execve resumed>" in item and pid in pending:
            start = pending.pop(pid)
            trace[start] = trace[start].split(" <unfinished ...>")[0] + item.split("<... execve resumed>", 1)[1]
    for name in TARGETS:
        outfile = '"-o", "/tmp/work/module/kdbus/' + name + '"'
        execs = []
        for pos, line in enumerate(trace, 1):
            pid = line.partition(" ")[0]
            if outfile in line and f'execve("{actual_exe}", ' in line and " = 0" in line:
                execs.append((pid, pos, line.strip()))
        expect(len(execs) == 1, f"Expected one exact successful exec of {actual_exe} to build {name} ({group}), got {execs}")
        pid, pos, line = execs[0]
        if accelerated:
            expect(any(item.startswith(pid + " ") and f'execve("{want_exe}",' in item and outfile in item
                       and " = 0" in item for item in trace[:pos]),
                   f"Missing same-process dispatcher exec before accelerator {group} {name}")
        exit_pos, exit_line = next((i, item.strip()) for i, item in enumerate(trace[pos:], pos + 1)
                                   if item.startswith(pid + " ") and "exit_group(0)" in item)
        dispatch = [item.strip() for item in trace[pos:exit_pos - 1]
                    if item.startswith(pid + " ") and "execve(" in item and item.strip().endswith("= 0")]
        emulator = None
        if accelerated:
            expect(not dispatch, f"Unexpected subsequent exec after accelerated tool for {group} {name}")
        else:
            expect(len(dispatch) == 1 and 'execve("/usr/bin/qemu-arm", ' in dispatch[0] and want_exe in dispatch[0],
                   f"Unexpected native QEMU dispatch for {group} {name}: {dispatch}")
            emulator = {"path": "/usr/bin/qemu-arm", "trace": dispatch[0],
                        "sha256": digest(WORK / "stage/usr/bin/qemu-arm")}
        results[name] = {
            "linker": GNU, "executable": actual_exe, "tool": tool_hashes[actual_exe],
            "evidence_level": "E4_DIRECT_EXECUTION_OBSERVED_FOR_LOCAL_BUILD",
            "pid": int(pid), "exec_trace_line": pos, "exec_trace": line, "emulator": emulator,
            "exit_trace_line": exit_pos, "exit_trace": exit_line, "exit_status": 0,
            "saved_kbuild_command": (folder / f".{name}.cmd").read_text().splitlines()[0],
            "output_sha256": digest(folder / name),
        }
    return results


def module_abi(lane, path, expected_crc):
    label = re.sub(r"[^A-Za-z0-9_.-]", "_", str(path.relative_to(WORK / lane / "installed")))
    stem = EVIDENCE / "builds" / lane / "elf" / (label + "-readelf")
    code = run(stem, ["readelf", "-aW", "-A", "-n", "-p", ".modinfo", str(path)])
    if code:
        raise ValueError(f"GNU readelf failed for {path}")
    raw = stem.with_suffix(".out").read_text(errors="replace")
    model = parse_module(path.read_bytes(), detail=True, arm_relocations=readelf_arm_names(raw))
    versions = model["versions"]["imports"]
    mismatches = {name: {"observed": crc, "expected": expected_crc.get(name)} for name, crc in versions.items()
                  if expected_crc.get(name) != crc}
    expect(model["module_release"] == RELEASE and " modversions " in model["model"]["vermagic"][0],
           f"Unexpected vermagic {path}")
    if path.name == "kdbus.ko":
        reference = (EVIDENCE / "published-gcc-kdbus-modinfo.out").read_text()
        reference_vermagic = next(line.partition("vermagic=")[2] for line in reference.splitlines()
                                  if "vermagic=" in line)
        expect(model["model"]["vermagic"][0] == reference_vermagic, f"Published GCC vermagic mismatch in {lane}")
    expect(versions and not mismatches, f"CRC mismatch or missing CRCs {path}: {mismatches}")
    relocations = Counter(r["type"] for r in model["relocations"])
    expect(all(not r.startswith("R_ARM_UNKNOWN_") for r in relocations), f"Unknown ARM relocations in {path}")
    interface = sorted([s[k] for k in ("name", "binding", "section", "visibility", "size")]
                       for s in model["symbols"] if s["binding"] in ("GLOBAL", "WEAK") or not s["defined"])
    return {
        "sha256": digest(path), "bytes": path.stat().st_size, "header": model["header"],
        "build_ids": model["build_ids"], "modinfo": model["model"], "signature": model["signature"],
        "import_crc_count": len(versions), "exports": model["exports"], "symbol_interface": interface,
        "relocations": dict(relocations), "mapping_symbols": dict(Counter(s["name"].split(".", 1)[0]
                            for s in model["symbols"] if re.fullmatch(r"\$[adt](?:\..*)?", s["name"]))),
        "alloc_sections": [{"name": s["name"], "size": s["size"], "flags": s["flags"], "alignment": s["alignment"],
                            "sha256": s["content_sha256"]} for s in model["sections"] if s["flags"] & 2],
    }


def inspect(lane, sdk):
    target = WORK / lane / "installed"
    artifacts = {str(path.relative_to(target)): module_abi(lane, path, sdk) for path in sorted(target.rglob("*.ko"))}
    expect(len(artifacts) == 7, f"Unexpected count of GCC modules for {lane}")
    group = WORK / lane
    folder = EVIDENCE / "builds" / lane
    scoped_argv = bubblewrap(OLD_ROOT, group, lane.endswith("-prefix"), "14-15", lane.endswith("-accel"))
    bfd_file = "/tmp/work/installed/lib/modules/" + RELEASE + "/extra/kdbus/kdbus.ko"
    exit_code = run(folder / "kdbus-normalized-disassembly",
                    [*scoped_argv, "/usr/bin/objdump", "-dr", "--no-show-raw-insn", bfd_file])
    expect(exit_code == 0, f"objdump failed for {lane}")
    commands = execution(lane)
    inputs = read_json(folder / "ordered-inputs.json")
    dump(folder / "abi.json", artifacts)
    dump(folder / "linker-execution.json", commands)
    return {
        "exec": commands, "ordered_input_sha256": inputs, "installed_modules": artifacts,
        "gc_unstripped_sha256": digest(folder / "kdbus.ko"),
        "gc_intermediate_sha256": digest(folder / "kdbus.o"),
        "gc_installed_sha256": digest(folder / "kdbus.installed.ko"),
        "normalized_disassembly_sha256": digest(folder / "kdbus-normalized-disassembly.out"),
    }


def compare(pairs, sdk):
    rows = {}
    for label, left, right in pairs:
        files = {lane: inspect(lane, sdk) for lane in (left, right)}
        a, b = files[left], files[right]
        scopes = ("ordered_input_sha256", "installed_modules", "gc_unstripped_sha256", "gc_intermediate_sha256",
                  "gc_installed_sha256", "normalized_disassembly_sha256")
        equivalent = {name: a[name] == b[name] for name in scopes}
        expect(all(equivalent.values()), f"Unexplained controlled GNU A/B differences: {label} {equivalent}")
        mod = next(m for name, m in a["installed_modules"].items() if name.endswith("/kdbus/kdbus.ko"))
        rows[label] = {
            "groups": [left, right], "compared": equivalent,
            "both_linkers": GNU, "module_count": len(a["installed_modules"]),
            "module_import_crcs_each": sum(m["import_crc_count"] for m in a["installed_modules"].values()),
            "kdbus_import_crcs_each": mod["import_crc_count"],
            "kdbus_installed_bytes": mod["bytes"],
            "kdbus_unstripped_sha256": a["gc_unstripped_sha256"],
            "kdbus_intermediate_sha256": a["gc_intermediate_sha256"],
            "kdbus_installed_sha256": a["gc_installed_sha256"],
            "kdbus_relocations": mod["relocations"], "kdbus_modules_build_ids": mod["build_ids"],
            "linker_execution_receipts": [str((EVIDENCE / "builds" / group / "linker-execution.json").relative_to(ROOT))
                                           for group in (left, right)],
        }
    return rows


def main():
    sdk_dir = WORK / "sdk" / SDK
    sdk = {parts[1]: parts[0] for line in (sdk_dir / "Module.symvers").read_text().splitlines()
           if (parts := line.split())}
    pairs = [("qb_native", "C", "D")]
    if all((EVIDENCE / "builds" / group / "kdbus.installed.ko").exists() for group in ("C-prefix", "D-prefix")):
        pairs += [("explicit_packaged_binutils_prefix", "C-prefix", "D-prefix")]
    if all((EVIDENCE / "builds" / group / "kdbus.installed.ko").exists() for group in ("C-accel", "D-accel")):
        pairs += [("exact_publication_acceleration", "C-accel", "D-accel")]
    rows = compare(pairs, sdk)
    module_lds = sdk_dir / "scripts/module.lds"
    (EVIDENCE / "sdk-module.lds").write_bytes(module_lds.read_bytes())
    sources = read_json(EVIDENCE / "source-manifests.json")
    for lane, tree in sources.items():
        for relative, expected in tree.items():
            member = WORK / lane / "module" / relative
            observed = "symlink:" + os.readlink(member) if member.is_symlink() else digest(member)
            expect(observed == expected, f"Kbuild altered frozen input {lane}/{relative}")
    result = {
        "status": "PASS_REAL_GCC_BFD_BUILD",
        "gcc_real_build": "PASS",
        "gcc_compatibility": "PASS",
        "gcc_simulation": "PASS_PHASE11",
        "qb": "tizen-unified-dev_20261120.082616",
        "kernel_release": RELEASE, "architecture": "ARMv7l non-RT",
        "same_kernel_commit_as_llvm_qb": "42aeefac58edeb081aff440f0b60be71cbe49755",
        "gcc_wrapper_commit": "46316fa8f9dd0d0d51726ad5fbe299daa2d16af6",
        "kernel_config_sha256": digest(sdk_dir / ".config"),
        "module_symvers_sha256": digest(sdk_dir / "Module.symvers"),
        "module_symvers_symbols": len(sdk),
        "module_linker_script_sha256": digest(module_lds),
        "compiler": "Tizen GCC 14.2.0-1.6.armv7l",
        "linker_package": "binutils-2.43-1.6.armv7l.rpm",
        "runs": rows, "scope": "C/D targeted external-module build and Kbuild modules_install, not RPM packaging or runtime",
    }
    dump(EVIDENCE / "status.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
