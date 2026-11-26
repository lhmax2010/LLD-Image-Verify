#!/usr/bin/env python3
"""Evaluate the proposed rule on image controls and score the open cohorts."""
import argparse
from collections import Counter, defaultdict
from importlib import import_module
from pathlib import Path
import re

image = import_module("export-image-evidence")
COMPILER = re.compile(r"(?:^| \| )(?:GCC:|(?:Apple |Tizen )?clang version\b|GNU C\b|rustc version\b|Intel\(R\))", re.I)
LLD = re.compile(r"(?:^| \| )Linker: LLD\b")


def receipt(index, row):
    if not row["debug_rpm_url"] or not row["debug_path"]:
        return None
    entries = index.get((row["debug_rpm_url"], row["debug_path"]), [])
    # Require the same debuglink CRC and/or Build ID used for the image pairing.
    matches = []
    for entry in entries:
        if entry["machine"] != row["elf_machine"]:
            continue
        if row["debuglink_crc"] and row["debuglink_crc"] != entry["file_crc"]:
            continue
        if row["build_id"] and row["build_id"] != entry["build_id"]:
            continue
        if row["debuglink_crc"] or row["build_id"]:
            matches.append(entry)
    return matches[0] if len({entry["sha256"] for entry in matches}) == 1 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--debuginfo", type=Path, required=True)
    args = parser.parse_args()
    index = defaultdict(list)
    for row in image.rows(args.debuginfo):
        index[row["url"], row["path"]].append(row)
    details, stats = [], defaultdict(Counter)
    for unified, _ in image.ROUNDS.values():
        for row in image.rows(args.data / f"image-instances-{unified}.csv"):
            control = row["historical_class"] in ("lld-confirmed", "gnu-ld-confirmed")
            selected = control or row["historical_class"] in (
                "gnu-ld-like-layout", "lld-layout", "unresolved", "not-lld-22.1.8"
            )
            if not selected:
                continue
            debug = receipt(index, row)
            compiler, marker, gold = "", "", ""
            outcome = "unpaired"
            if debug:
                compiler = bool(COMPILER.search(debug["comments"]))
                marker = bool(LLD.search(debug["comments"]))
                gold = debug["gold_note"] == "True"
                outcome = ("predict-non-LLD" if compiler and not marker and not gold else "does-not-fire")
            independent = (row["historical_class"] == "gnu-ld-confirmed" or
                           bool(LLD.search(row["comments"])) or
                           (row["historical_class"] == "lld-confirmed" and
                            ("kernel" in row["archive_evidence"] or bool(row["module_log"]) or
                             "Kbuild" in row["evidence_reference"] or bool(row["trace_lines"]))))
            details.append(dict(snapshot=row["snapshot"], arch=row["arch"], repository=row["repository"],
                                image=row["image"], partition=row["partition"], path=row["path"], sha256=row["sha256"],
                                historical_class=row["historical_class"], evidence_class=row["evidence_class"],
                                paired=bool(debug), compiler_strings=compiler, lld_marker=marker, gold_note=gold,
                                independent_control=independent if control else "",
                                rule_outcome=outcome, debug_url=row["debug_rpm_url"],
                                debug_path=row["debug_path"], debug_sha256=debug["sha256"] if debug else ""))
            cohorts = ["all-controls"] + (["independent-controls"] if independent else []) if control else ["application"]
            for sample in cohorts:
                counts = stats[(row["snapshot"], row["arch"], sample, row["historical_class"])]
                counts["instances"] += 1
                counts[outcome] += 1
                if control and debug:
                    actual_other = row["historical_class"] == "gnu-ld-confirmed"
                    counts["agreement"] += actual_other == (outcome == "predict-non-LLD")
    data = []
    for (snapshot, arch, cohort, evidence), counts in sorted(stats.items()):
        evaluated = counts["instances"] - counts["unpaired"]
        data.append(dict(snapshot=snapshot, arch=arch, cohort=cohort, evidence_class=evidence,
                         all_instances=counts["instances"], evaluated=evaluated,
                         unpaired=counts["unpaired"], rule_fires=counts["predict-non-LLD"],
                         rule_does_not_fire=counts["does-not-fire"],
                         agreements=counts["agreement"] if cohort.endswith("controls") else "",
                         agreement_rate=(f"{counts['agreement'] / evaluated:.6f}"
                                         if evaluated and cohort.endswith("controls") else "")))
    image.write_csv(args.data / "debuginfo-rule-summary.csv", data)
    image.write_csv(args.data / "debuginfo-rule-instances.csv", details)


if __name__ == "__main__":
    main()
