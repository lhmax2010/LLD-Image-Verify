#!/usr/bin/env python3
"""Reconcile, seal, and independently verify the pinned Phase 11 evidence."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
OLD = WORKSPACE / "kernel_lld_verification_20261120"
PHASE10 = WORKSPACE / "phase10_kdbus_sandbox"
PREFIX = "KDBUS_LLD_FIX_"
SUMMARY = ROOT / (PREFIX + "QB_VERIFICATION_SUMMARY.json")
MATRIX = ROOT / (PREFIX + "GATE_MATRIX.csv")
BUNDLE = ROOT / (PREFIX + "EVIDENCE_BUNDLE.tar.gz")
BUNDLE_SUM = BUNDLE.with_name(BUNDLE.name + ".sha256")
NEW_SUMS = ROOT / "SHA256SUMS"
OLD_SUMS = ROOT / "SHA256SUMS_REUSED_INPUTS"
RECONCILE = ROOT / "evidence/preflight/final-reconciliation.json"
SDK = Path("evidence/build/devel/boot/kernel/devel/kernel-devel-arm-rpi4")
KEY = "extra/kdbus/kdbus.ko"
RELEASE = "6.12.80-arm-rpi4-v7l"
PROJECT = "platform/kernel/linux-tizen-modules-source"
FIX = "1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8"
PARENT = "25797e8af7ed95a5783bbe84c11959560aaf7e92"

PHASE_FILES = (
    "11A_PREFLIGHT.md", "11A_QB_IDENTITY.json", "11A_RPM_INVENTORY.csv",
    "11B_PATCH_INCLUSION_REPORT.md", "11B_SOURCE_DIFF.patch", "11B_SOURCE_PROVENANCE.json",
    "11C_INTERMEDIATE_DIRECT_EVIDENCE.md", "11C_INTERMEDIATE_LINK_COMMANDS.json",
    "11D_INTERMEDIATE_LINKER_CAUSAL_ANALYSIS.md", "11D_LINKER_VARIABLE_TRACE.json",
    "11D_LINKER_RULE_MATRIX.csv", "11E_BEFORE_AFTER_REPRODUCTION.md",
    "11E_REPRODUCTION_RESULTS.csv", "11E_MAKE_VARIABLE_TRACE.json",
    "11F_MODULE_BINARY_COMPARISON.md", "11F_MODULE_SIZE_COMPARISON.csv",
    "11F_MODULE_SYMBOL_DIFF.csv", "11F_MODULE_RELOCATION_DIFF.csv", "11F_MODULE_ABI_SUMMARY.json",
    "11G_KERNEL_LLD_REGRESSION_REPORT.md", "11G_MODULE_INVENTORY_DIFF.csv",
    "11H_RUNTIME_VERIFICATION.md", "11H_RUNTIME_IDENTITY.json",
)


def require(ok, description):
    if not ok:
        raise ValueError(description)


def data(path):
    return json.loads((ROOT / path).read_text())


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def store(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def artifact(path):
    value = Path(path)
    if value.is_absolute():
        index = next(i for i, part in enumerate(value.parts)
                     if part in (ROOT.name, OLD.name, PHASE10.name))
        return WORKSPACE.joinpath(*value.parts[index:])
    return ROOT / value


def verify_report_links(allow_missing_matrix=False):
    doc_paths = [ROOT / x for x in PHASE_FILES if x.endswith(".md")]
    doc_paths.extend(ROOT.glob(PREFIX + "*.md"))
    for doc in doc_paths:
        for link in re.findall(r"\]\(([^()]+)\)", doc.read_text()):
            path = link.lstrip("<").split("#", 1)[0].rstrip(">")
            if path and not re.match(r"^[a-z]+://", path):
                target = doc.parent / path
                require(target.exists() or (allow_missing_matrix and target == MATRIX),
                        f"{doc.name}: missing link {link}")


def reconcile(allow_missing_matrix=False):
    for name in PHASE_FILES:
        require((ROOT / name).stat().st_size > 0, f"Missing or empty deliverable {name}")
    verify_report_links(allow_missing_matrix)
    identity = data("11A_QB_IDENTITY.json")
    provenance = data("11B_SOURCE_PROVENANCE.json")
    direct = data("11C_INTERMEDIATE_LINK_COMMANDS.json")
    trace = data("11D_LINKER_VARIABLE_TRACE.json")
    make = data("11E_MAKE_VARIABLE_TRACE.json")
    abi = data("11F_MODULE_ABI_SUMMARY.json")
    runtime = data("11H_RUNTIME_IDENTITY.json")
    phase10 = data(PHASE10 / "evidence/remote-object-verification.json")

    require(identity["preflight_status"] == "PASS", "QB preflight not passed")
    require(identity["new"]["project_revisions"][PROJECT] == provenance["new_qb_source_commit"] ==
            phase10["remote_head"] == FIX and phase10["parent"] == PARENT,
            "Phase 10 commit, QB manifest and source provenance disagree")
    require(provenance["status"] == "PATCH_INCLUDED" and identity["target_wrapper_rebuilt"] and
            provenance["source_payload_member_comparison"]["changed_members"] == ["Makefile"],
            "Patch inclusion or release binding not proven")
    require(identity["kernel_release"] == RELEASE and identity["config_comparison"]["byte_identical"],
            "Non-RT release or configuration mismatch")
    for side in ("old", "new"):
        config = identity["sdk_identity"][side]["config"]
        require(digest(artifact(config["path"])) == config["sha256"], f"{side} SDK config checksum")
    rpm_rows = [row for row in identity["rpm_rows"] if row["local_sha256"]]
    for row in rpm_rows:
        require(digest(artifact(row["artifact_path"])) == row["local_sha256"] ==
                row["published_checksum"] and row["repository_checksum_verification"] == "PASS",
                f"Published RPM checksum {row['nevra']}")
    assignment = b"LD = ${CROSS_COMPILE}ld\n"
    old_make = (ROOT / "evidence/source/old/Makefile").read_bytes()
    new_make = (ROOT / "evidence/source/new/Makefile").read_bytes()
    require(old_make.count(assignment) == 1 and old_make.replace(assignment, b"", 1) == new_make and
            (ROOT / "evidence/source/old/kdbus/Makefile").read_bytes() ==
            (ROOT / "evidence/source/new/kdbus/Makefile").read_bytes(), "Not the expected single deletion")

    require(direct["status"] == "HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE" and
            direct["actual_argv"] is None and not direct["e4_established"], "Unexpected E4 assertion")
    require(trace["status"] == "E3_ENGINEERING_VERIFIED" and trace["original_ld_override"] == "REMOVED" and
            trace["bfd_bypass_risk"] == "NO_REASONABLE_BFD_PATH_IDENTIFIED", "Unexpected E3 or BFD classification")
    log_info = trace["successful_external_log"]
    log = artifact(log_info["path"])
    require(digest(log) == log_info["sha256"], "External job log checksum")
    log_lines = log.read_text().splitlines()
    for stage in ("intermediate", "final"):
        link = trace[stage]
        line = log_lines[link["observed_log_line"] - 1]
        require(link["target"] in line and link["selected_command_name"] == "ld.lld" and
                link["version"] == identity["lld_version"]["new"] and link["evidence_level"] == "E3",
                f"Inconsistent job linkage for {stage}")
    module_data = trace["released_module"]["module"]
    require(digest(artifact(module_data["path"])) == module_data["sha256"] and
            trace["released_module"]["rpm_file_digest_verified"], "Released kdbus content binding")

    make_rows = rows(ROOT / "11E_REPRODUCTION_RESULTS.csv")
    runs = len({(row["snapshot"], row["case"]) for row in make_rows})
    calls = sum(bool(json.loads(row["mocked_argv"])) for row in make_rows)
    require(make["status"] == "PASS" and runs == len(make["results"]) == make["runs"] == 46 and
            len(make_rows) == make["observations"] == 322 and calls == make["modeled_calls"] == 92 and
            all(row["status"] == "PASS" and row["actual_linker_executed"] == "False" for row in make_rows) and
            not make["historical_link_proven"], "Unexpected Make result scope or counts")
    inventory = rows(ROOT / "11G_MODULE_INVENTORY_DIFF.csv")
    require(len({row["module_path"] for row in inventory}) == len(inventory) == 59 and
            Counter(row["module_group"] for row in inventory) == {"in-tree": 52, "out-of-tree": 7} and
            Counter(row["status"] for row in inventory) == {"CHANGED": 53, "IDENTICAL": 6} and
            all(row["new_parse_status"] == "PASS" for row in inventory), "Module coverage mismatch")
    for row in inventory:
        require(digest(artifact(row["new_source_artifact"])) == row["new_sha256"],
                f"Module payload checksum: {row['module_path']}")

    kdbus = abi["modules"][KEY]
    require(abi["status"] == "PASS_STATIC_CHECKS" and not abi["failures"] and not abi["new_parser_failures"] and len(abi["modules"]) == 7 and
            kdbus["new"]["artifact_sha256"] == module_data["sha256"] and
            kdbus["old_file_size"] == 162584 and kdbus["new_file_size"] == 161292 and
            kdbus["new_reloc_total"] == kdbus["old_reloc_total"] == 2972, "kdbus ELF metrics mismatch")
    require(not rows(ROOT / "11F_MODULE_RELOCATION_DIFF.csv"), "Unexpected relocation deltas")
    require(all(item["vermagic_equal"] and item["kernel_exports_equal"] and
                not item["imports_added"] and not item["imports_removed"] and
                not item["defined_global_weak_shapes_added"] and not item["defined_global_weak_shapes_removed"] and
                not item["import_crc_changes"] and not item["metadata_changed"] and
                not item["new_reloc_types"] and not item["removed_reloc_types"] and
                item["new_import_crc_validation"]["summary"] ==
                {"MATCH": item["new_import_crc_validation"]["imported_crc_count"]}
                for item in abi["modules"].values()), "Measured module compatibility deltas")
    imports = sum(item["new_import_crc_validation"]["imported_crc_count"] for item in abi["modules"].values())
    require(imports == 356, "Versioned import count mismatch")
    require(runtime["status"] == "PENDING_NEW_IMAGE_DEPLOYMENT" and runtime["observed_old_snapshot"] and
            not runtime["new_snapshot_verified"] and not runtime["mutation_performed"], "Runtime identity mismatched")

    values = {
        "NEW_QB_PATCH_INCLUDED": provenance["status"],
        "NEW_QB_SOURCE_COMMIT": FIX,
        "NEW_QB_KERNEL_RELEASE": RELEASE,
        "NEW_QB_COMPILER": "Clang " + identity["clang_version"]["new"],
        "NEW_QB_LINKER": "LLVM LLD " + identity["lld_version"]["new"],
        "KDBUS_INTERMEDIATE_LINKER": trace["intermediate"]["linker"] + " " + trace["intermediate"]["version"],
        "KDBUS_INTERMEDIATE_EVIDENCE": trace["intermediate"]["evidence_level"],
        "KDBUS_FINAL_LINKER": trace["final"]["linker"] + " " + trace["final"]["version"],
        "KDBUS_FINAL_EVIDENCE": trace["final"]["evidence_level"],
        "ORIGINAL_LD_OVERRIDE": trace["original_ld_override"],
        "BFD_BYPASS_RISK": trace["bfd_bypass_risk"],
        "STATIC_ABI_COMPATIBILITY": "PASS",
        "GCC_SIMULATION": "PASS",
        "GCC_REAL_BUILD": "PENDING",
        "RUNTIME_VALIDATION": runtime["status"],
        "ENGINEERING_ACCEPTANCE": "PASS",
        "STRICT_ACCEPTANCE": "CONDITIONAL_PASS",
        "LLD_KERNEL_001": "RECOMMEND_ENGINEERING_CLOSE_PM_DECISION_PENDING",
        "PRODUCT_MERGE_READINESS": "PENDING",
        "PM_REVIEW_REQUIRED": "YES",
    }
    gate_rows = [
        ("A", "Patch included", "PASS", "PASS", "Exact Phase 10 commit and prepared RPM source",
         "11B_SOURCE_PROVENANCE.json", ""),
        ("B", "Intermediate kdbus.o linker", "PASS", "PENDING_E4", "E3 LLVM LLD 22.1.8, original override gone",
         "11C_INTERMEDIATE_LINK_COMMANDS.json;11D_LINKER_VARIABLE_TRACE.json", "Recover historically linked executable, argv and successful execution for strict acceptance"),
        ("C", "Final kdbus.ko linker", "PASS", "PASS", "E3 LLVM LLD 22.1.8, separate modfinal proof",
         "11D_LINKER_VARIABLE_TRACE.json", ""),
        ("D", "Build and binary regression", "PASS", "PASS", "Published 59/59 parse, seven detailed ABI checks",
         "11F_MODULE_ABI_SUMMARY.json;11G_MODULE_INVENTORY_DIFF.csv", ""),
        ("E", "GCC/BFD compatibility", "PASS_SIMULATION", "PENDING_REAL_BUILD", "Tool-selection model passed",
         "11E_MAKE_VARIABLE_TRACE.json", "Validate targeted real GCC/BFD product build"),
        ("F", "Runtime regression", runtime["status"], runtime["status"], "Authorized device still runs old QB",
         "11H_RUNTIME_IDENTITY.json", "Verify identity and run read-only checks after authorized new image deployment"),
        ("G", "Evidence integrity", "PASS", "PASS", "SHA256, separate snapshots, raw receipts and scripts",
         "SHA256SUMS;SHA256SUMS_REUSED_INPUTS;KDBUS_LLD_FIX_EVIDENCE_INDEX.md", ""),
    ]
    details = {
        "old_qb": identity["old"]["id"],
        "new_qb": identity["new"]["id"],
        "platform": "RPi4 ARMv7l non-RT",
        "repository": PROJECT,
        "sandbox_ref": phase10["ref"],
        "historical_source_commit": PARENT,
        "old_qb_intermediate_linker": "BFD_PATH_POSSIBLE",
        "direct_evidence": direct["status"],
        "runtime_observed_image": runtime["image_build_id"],
        "module_counts": abi["counts"],
        "static_scope": "Released ELF and module ABI, seven out-of-tree modules in detail",
        "kdbus": {
            "old_sha256": kdbus["old"]["artifact_sha256"], "new_sha256": module_data["sha256"],
            "old_size_bytes": kdbus["old_file_size"], "new_size_bytes": kdbus["new_file_size"],
            "delta_bytes": kdbus["file_size_delta"], "relocations_each": kdbus["new_reloc_total"],
            "import_crcs_each": kdbus["new_import_crc_validation"]["imported_crc_count"],
        },
        "make_model": {"runs": runs, "observations": make["observations"], "mock_calls": make["modeled_calls"]},
        "new_unified_rpms_checksum_verified": len(rpm_rows),
        "gates": {row[0]: dict(engineering=row[2], strict_or_remaining=row[3]) for row in gate_rows},
        "limitations": [
            "E4 historical direct execution unavailable for the composite link.",
            "Real GCC/BFD build and new device deployment runtime remain pending.",
            "The current device is a separate old QB control.",
            "Base QB, build host and toolchain package revisions changed. Binary differences cannot be attributed solely to the one-line patch.",
        ],
    }
    return values, details, gate_rows


def reusable_files():
    paths = {
        OLD / "02_kernel_rpm_inventory.csv",
        OLD / "05_kernel_module_inventory.csv",
        OLD / "evidence/repository/manifest.out",
        OLD / "evidence/repository/publication-build.out",
        OLD / "evidence/build/linux-tizen-modules-armv7l.out",
        OLD / "evidence/build/linux-rpi-armv7l.out",
        OLD / "pm_review_round2/evidence/external/linux-tizen-modules-source-11.0.0-0.armv7l.rpm",
        PHASE10 / "KDBUS_LD_FIX_SUBMISSION_SUMMARY.json",
        PHASE10 / "evidence/remote-object-verification.json",
        PHASE10 / "evidence/remote-fetched-diff.out",
    }
    paths.update(OLD / SDK / p for p in (".config", "include/generated/compile.h", "include/generated/utsrelease.h"))
    paths.update(OLD / "evidence/repository/rpms" / name for name in (
        "rpi4-linux-kernel-6.12.80-0.src.rpm", "linux-tizen-modules-11.0.0-0.src.rpm",
        "linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm",
        "arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm"))
    paths.update(OLD / row["file"] for row in rows(OLD / "05_kernel_module_inventory.csv")
                 if row["scope"] == "repository" and f"/modules/{RELEASE}/" in row["path"])
    for report in ROOT.glob("*.md"):
        for external in re.findall(r"\]\((\.\./[^)#]+)", report.read_text()):
            path = (ROOT / external).resolve()
            if path.is_file() and (path.is_relative_to(OLD) or path.is_relative_to(PHASE10)):
                paths.add(path)
    return sorted(paths)


def snapshot_files():
    excluded = {BUNDLE, BUNDLE_SUM, NEW_SUMS, OLD_SUMS, BUNDLE.with_suffix(".tmp")}
    paths = sorted(path for path in ROOT.rglob("*")
                   if path.is_file() and path not in excluded and "__pycache__" not in path.parts)
    return [path for path in paths if not path.is_symlink()]


def write_manifest(path, paths):
    path.write_text("".join(f"{digest(p)}  {os.path.relpath(p, ROOT)}\n" for p in paths))


def read_manifest(path):
    result = {}
    for line in path.read_text().splitlines():
        checksum, rel = line.split("  ", 1)
        candidate = (ROOT / rel).resolve()
        require(candidate.is_relative_to(WORKSPACE) and candidate not in result, f"Invalid manifest entry {line}")
        result[candidate] = checksum
    return result


def verify_disk():
    recorded_new = read_manifest(NEW_SUMS)
    recorded_old = read_manifest(OLD_SUMS)
    require(set(recorded_new) == set(snapshot_files()), "New manifest file coverage mismatch")
    require(set(recorded_old) == set(reusable_files()), "Reused manifest file coverage mismatch")
    for path, checksum in (recorded_new | recorded_old).items():
        require(digest(path) == checksum, f"Evidence checksum mismatch {path}")
    values, details, gates = reconcile()
    require(data(SUMMARY) == {**values, **details}, "Final summary differs from evidence")
    with MATRIX.open(newline="") as stream:
        reader = csv.reader(stream)
        next(reader)
        require([tuple(row) for row in reader] == gates, "Final gate matrix differs from evidence")
    return recorded_new | recorded_old


def symlinks():
    recorded = {}
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            target = os.readlink(path)
            require(not Path(target).is_absolute() and path.resolve().is_relative_to(ROOT) and path.is_file(),
                    f"Unexpected or unsafe evidence symlink {path}")
            recorded[path.relative_to(WORKSPACE).as_posix()] = target
    return recorded


def verify_bundle(files):
    require(BUNDLE_SUM.read_text() == f"{digest(BUNDLE)}  {BUNDLE.name}\n", "Bundle SHA256 mismatch")
    expected = {path.relative_to(WORKSPACE).as_posix(): sha for path, sha in files.items()}
    expected.update({p.relative_to(WORKSPACE).as_posix(): digest(p) for p in (NEW_SUMS, OLD_SUMS)})
    links = symlinks()
    with tarfile.open(BUNDLE, "r|gz") as archive:
        for item in archive:
            if item.issym():
                require(item.name in links and links.pop(item.name) == item.linkname, f"Unexpected symlink {item.name}")
                continue
            require(item.isreg() and item.name in expected, f"Unexpected file {item.name}")
            stream = archive.extractfile(item)
            require(hashlib.file_digest(stream, "sha256").hexdigest() == expected.pop(item.name),
                    f"Bundle member digest mismatch: {item.name}")
    require(not (expected or links), "Incomplete archived evidence")


def seal():
    values, details, gates = reconcile(allow_missing_matrix=True)
    store(SUMMARY, {**values, **details})
    with MATRIX.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("gate", "scope", "engineering_status", "strict_or_remaining_status", "reason", "evidence", "open_requirement"))
        writer.writerows(gates)
    store(RECONCILE, {"status": "PASS", "checked": list(PHASE_FILES),
                      "counts": details["module_counts"], "gates": details["gates"],
                      "stage": "Semantic reconciliation before evidence archive creation"})
    write_manifest(NEW_SUMS, snapshot_files())
    write_manifest(OLD_SUMS, reusable_files())
    files = verify_disk()
    tmp = BUNDLE.with_suffix(".tmp")
    with tarfile.open(tmp, "w:gz", compresslevel=4) as archive:
        for path in sorted(set(files) | {NEW_SUMS, OLD_SUMS}):
            archive.add(path, arcname=path.relative_to(WORKSPACE).as_posix(), recursive=False)
        for name in symlinks():
            archive.add(WORKSPACE / name, arcname=name, recursive=False)
    tmp.replace(BUNDLE)
    BUNDLE_SUM.write_text(f"{digest(BUNDLE)}  {BUNDLE.name}\n")
    verify_bundle(files)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--seal", action="store_true", help="regenerate PM summary, checksum manifests and evidence bundle")
    mode.add_argument("--verify-bundle", action="store_true", help="verify workspace and compressed members")
    mode.add_argument("--unpacked", action="store_true", help="verify unpacked evidence and reused inputs")
    args = cli.parse_args()
    if args.seal:
        seal()
    elif args.verify_bundle:
        verify_bundle(verify_disk())
    elif args.unpacked:
        verify_disk()
    else:
        reconcile()
    print("PASS: Phase 11 deliverable reconciliation" +
          (" and end-to-end archive validation" if args.seal or args.verify_bundle else ""))


if __name__ == "__main__":
    main()
