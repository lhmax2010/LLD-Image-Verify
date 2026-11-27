#!/usr/bin/env python3
"""Summarize the verified ELF scan and check the new QB's kernel link rules."""
import csv
import json
import re
from collections import Counter

from compare_qb_modules import E, OLD, REPO, ROOT, SDK_MEMBER_ROOT, need, rel_path, sha, write_json

ABI_REFERENCE = "https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst"
ARM_DEFAULTS = {"Tag_ABI_PCS_R9_use": "V6", "Tag_ABI_FP_exceptions": "Unused"}
ABI_FIELDS = (
    "metadata_changed", "imports_added", "imports_removed", "defined_global_weak_shapes_added",
    "defined_global_weak_shapes_removed", "import_crc_changes", "crc_imports_added", "crc_imports_removed",
    "relocation_diff_rows", "new_reloc_types", "relocation_origin_payload_changes",
)
CHECKED_MEMBERS = (".config", "Makefile", "include/generated/compile.h", "include/config/kernel.release",
    "scripts/Makefile.vmlinux", "scripts/link-vmlinux.sh", "scripts/Makefile.lib", "scripts/Makefile.modfinal",
    "arch/arm/Makefile", "arch/arm/boot/compressed/Makefile")


def checked_defaults(module):
    old, new = (module[side]["arm_attributes"] for side in ("old", "new"))
    if old == new:
        return True
    if "Tag_nodefaults" in (old.keys() | new.keys()):
        return False
    return all(old.get(tag, ARM_DEFAULTS.get(tag)) == new.get(tag, ARM_DEFAULTS.get(tag))
               for tag in (old.keys() | new.keys()))


def abi_review(scan, identity):
    totals = {"old": Counter(), "new": Counter()}
    issues = []
    for path, module in scan["modules"].items():
        module["arm_attribute_semantics_equal"] = checked_defaults(module)
        for field in ABI_FIELDS:
            if module[field]:
                issues.append([path, field])
        for field in ("basic_header_equal", "arm_attribute_semantics_equal", "vermagic_equal",
                      "kernel_exports_equal", "signatures_equal", "module_release_equal"):
            if not module[field]:
                issues.append([path, field])
        for side in ("old", "new"):
            per_module = module[f"{side}_import_crc_validation"]
            totals[side].update(per_module["summary"])
            if (not per_module["imported_crc_count"] or
                    per_module["summary"].get("MATCH") != per_module["imported_crc_count"]):
                issues.append([path, f"{side}_import_crc_validation"])
    incomplete = bool(scan["failures"] or scan["new_parser_failures"] or len(scan["modules"]) != 7)
    scan.update(status="REVIEW_REQUIRED" if incomplete or issues else "PASS_STATIC_CHECKS",
        abi_assessment={"scope": "Observed packaged module interfaces and relocation compatibility checks",
            "unresolved_findings": issues, "crc_verification_totals": totals, "runtime_proven": False,
            "arm_abi_reference": ABI_REFERENCE,
            "arm_abi_default_values": {tag: {"encoding": 0, "readelf": value} for tag, value in ARM_DEFAULTS.items()}},
        cross_qb_confounders=identity["confounders"],
        same_kernel_config=identity["config_comparison"]["byte_identical"])


def log_hits(path, pattern, *, minimum=1, maximum=None):
    matches = []
    for line, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if (maximum is None or line <= maximum) and line >= minimum and re.search(pattern, raw):
            matches.append({"line": line, "raw": raw})
    return matches


def rule_sources(sdk):
    rules = {
        "kbuild_llvm_ld": ("Makefile", r"^LD\s*= \$\(LLVM_PREFIX\)ld\.lld\$\(LLVM_SUFFIX\)"),
        "kbuild_export": ("Makefile", r"^export .*\bCROSS_COMPILE LD CC\b"),
        "kernel_dispatch": ("Makefile", r"scripts/Makefile\.vmlinux$"),
        "kernel_final": ("scripts/Makefile.vmlinux", r'\$< "\$\(LD\)"'),
        "kernel_script": ("scripts/link-vmlinux.sh", r'ld="\$\{LD\}"|\$\{ld\} \$\{ldflags\} -o'),
        "arm_decompressor": ("arch/arm/boot/compressed/Makefile", r"^\$\(obj\)/vmlinux:|if_changed,ld\)"),
        "arm_decompressor_ld": ("scripts/Makefile.lib", r"^\s*cmd_ld\s*= \$\(LD\) "),
        "module_final": ("scripts/Makefile.modfinal", r"\$\(LD\) -r|^%\.ko:|if_changed_except,ld_ko_o"),
    }
    result = {name: {"file": rel_path(sdk / member), "lines": log_hits(sdk / member, expression)}
              for name, (member, expression) in rules.items()}
    need(all(rule["lines"] for rule in result.values()), "Expected link rule missing. Review the new Kbuild sources")
    return result


def kernel_review(scan):
    sdk = REPO / "sdk" / SDK_MEMBER_ROOT.lstrip("/")
    headers = dict(line.split("\t", 1) for line in (E / "rpm/new-sdk-digests.out").read_text().splitlines())
    for member in CHECKED_MEMBERS:
        need(headers[SDK_MEMBER_ROOT + member] == sha(sdk / member), f"SDK RPM member digest mismatch for {member}")
    config = dict(line.split("=", 1) for line in (sdk / ".config").read_text().splitlines()
                  if line.startswith("CONFIG_") and "=" in line)
    compiler = re.search(r'^#define\s+LINUX_COMPILER\s+"([^\"]+)"', (sdk / "include/generated/compile.h").read_text(), re.M)
    release = (sdk / "include/config/kernel.release").read_text().strip()
    need(compiler and release == scan["new_release"], "New SDK compiler banner or target release inconsistent")
    kernel = ROOT / "evidence/build/linux-rpi-armv7l.out"
    modules = ROOT / "evidence/build/linux-tizen-modules-armv7l.out"
    main_start = log_hits(kernel, r"\+ make O=build/arm-rpi4 -j\d+")[0]["line"]
    rt_start = log_hits(kernel, r"\+ make O=build/arm-rpi4-rt headers_install")[0]["line"]
    kernel_targets = log_hits(kernel, r"\]\s+LD\s+(?:vmlinux(?:\.o)?|arch/arm/boot/compressed/vmlinux)$",
                              minimum=main_start, maximum=rt_start - 1)
    kernel_llvm = log_hits(kernel, r"\+ export LLVM=1$", maximum=main_start)
    package_writes = log_hits(kernel, r"Wrote: .*arm-rpi4-linux-kernel(?:-modules|-devel)?-[0-9][^/]+\.armv7l\.rpm$")
    external_start = log_hits(modules, r"\+ export LLVM=1$")
    if not external_start:
        external_start = log_hits(modules, r"\+ LLVM=1$")
    need(external_start, "External build LLVM=1 line missing")
    rt_module_start = log_hits(modules, r"Entering directory.*kernel-devel-arm-rpi4-rt")
    need(rt_module_start, "Expected external RT build scope delimiter")
    external_targets = log_hits(modules, r"\]\s+LD \[M\]\s+\S+\.ko$", maximum=rt_module_start[0]["line"] - 1)
    wrapper_writes = log_hits(modules, r"Wrote: .*linux-tizen-modules-rpi4-[0-9][^/]+\.armv7l\.rpm$")
    assignments = r"\]\s+\+ .*\b(?:LD\s*=\s*\S+|ld\.bfd\b)|^\[.*?\]\s+\+\s+(?:\S*/)?\S*ld\.bfd(?:\s|$)"
    possible_overrides = log_hits(kernel, assignments, maximum=rt_start - 1) + log_hits(
        modules, assignments, maximum=rt_module_start[0]["line"] - 1)
    with (ROOT / "11G_MODULE_INVENTORY_DIFF.csv").open() as file:
        inventory = list(csv.DictReader(file))
    names = sorted(row["module_path"].removeprefix("extra/") for row in inventory
                   if row["module_group"] == "out-of-tree" and row["new_present"] == "True")
    module_targets = sorted(hit["raw"].split("/kernel/", 1)[-1] for hit in external_targets)
    warning_expression = r"resolve_btfids: unresolved symbol|btf_encoder__tag_kfunc"
    archived_kernel = OLD / "evidence/build/linux-rpi-armv7l.out"
    warnings = log_hits(kernel, warning_expression)
    old_warnings = log_hits(archived_kernel, warning_expression)
    warning_counts_equal = Counter(hit["raw"].split("] ", 1)[-1] for hit in warnings) == Counter(
        hit["raw"].split("] ", 1)[-1] for hit in old_warnings)
    complete = (len(kernel_targets) == 3 and kernel_llvm and len(package_writes) == 3 and names == module_targets
                and len(wrapper_writes) == 1 and not possible_overrides and config.get("CONFIG_LD_IS_LLD") == "y"
                and scan["counts"]["new_total"] == scan["counts"]["new_parsed"])
    return {"status": "PASS_SCOPED_REGRESSION_CHECK" if complete else "REVIEW_REQUIRED",
            "release": release, "compiler_linker_metadata": compiler.group(1),
            "metadata_origin": "Pinned development RPM generated compile.h and .config",
            "checked_sdk_members": {member: sha(sdk / member) for member in CHECKED_MEMBERS},
            "config": {key: config.get(key) for key in ("CONFIG_CC_IS_CLANG", "CONFIG_CC_VERSION_TEXT",
                "CONFIG_LD_IS_LLD", "CONFIG_LLD_VERSION", "CONFIG_LD_IS_BFD", "CONFIG_MODVERSIONS", "CONFIG_MODULE_SIG")},
            "rules": rule_sources(sdk), "kernel_log": rel_path(kernel), "modules_log": rel_path(modules),
            "kernel_make_start_line": main_start, "rt_kernel_scope_start_line": rt_start,
            "kernel_llvm": kernel_llvm, "kernel_targets": kernel_targets, "kernel_package_writes": package_writes,
            "external_llvm": external_start, "external_targets": external_targets, "external_rpm_write": wrapper_writes,
            "external_packaged_path_match": names == module_targets, "explicit_ld_shell_candidates": possible_overrides,
            "btf_warnings_match_baseline": warning_counts_equal, "new_btf_warnings": warnings, "old_btf_warnings": old_warnings,
            "inventory": scan["counts"], "newly_assigned_e3": [],
            "limits": ["Scoped SDK, build rules, quiet log and module payload validation.",
                       "The new main kernel, vmlinux and ARM decompressor ELF payloads were not independently analyzed here.",
                       "No historical executable trace or runtime inference."]}


def main():
    scan_path = ROOT / "11F_MODULE_ABI_SUMMARY.json"
    scan = json.loads(scan_path.read_text())
    abi_review(scan, json.loads((ROOT / "11A_QB_IDENTITY.json").read_text()))
    kernel = kernel_review(scan)
    write_json(scan_path, scan)
    write_json(E / "kernel-regression-summary.json", kernel)
    print(json.dumps({"11F": scan["status"], "11G": kernel["status"], "ABI": scan["abi_assessment"],
                      "counts": scan["counts"]}, indent=2))
    need(scan["status"] == "PASS_STATIC_CHECKS" and kernel["status"] == "PASS_SCOPED_REGRESSION_CHECK",
         "One or more static checks require review")


if __name__ == "__main__":
    main()
