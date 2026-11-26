#!/usr/bin/env python3
"""Report coverage by snapshot and architecture for a published RPM pass."""
import argparse
from collections import Counter, defaultdict
from importlib import import_module
from pathlib import Path

csvio = import_module("export-image-evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = {p["url"] for p in csvio.rows(args.scan / "rpm-inventory.csv")}
    summary = defaultdict(Counter)
    observed = set()
    for row in csvio.rows(args.scan / "rpm-pass.csv"):
        assert row["url"] not in observed
        observed.add(row["url"])
        key = row["snapshot"], row["arch"], row["kind"]
        counts = summary[key]
        counts["listed"] += 1
        if row["error"] == "pending":
            counts["pending"] += 1
            continue
        if row["error"] or row["file_errors"]:
            counts["failed"] += 1
            continue
        counts["scanned"] += 1
        counts[row["verdict"]] += 1
        for field in ("native_files", "static_archives", "paired", "lld_confirmed", "other_linker_confirmed", "open"):
            counts["file_" + field] += int(row[field])
    assert observed == inventory, (len(inventory), len(observed))
    measures = ("listed", "scanned", "pending", "failed", "all-LLD", "mixed", "non-LLD",
                "open", "no native files", "debug-evidence", "file_native_files", "file_static_archives",
                "file_paired", "file_lld_confirmed", "file_other_linker_confirmed", "file_open")
    csvio.write_csv(args.output, [
        dict(snapshot=snapshot, arch=arch, kind=kind, **{k: row[k] for k in measures})
        for (snapshot, arch, kind), row in sorted(summary.items())
    ])
    total = sum(summary.values(), Counter())
    assert total["listed"] == total["scanned"] + total["pending"] + total["failed"]
    print(f"{total['scanned']} / {total['listed']} RPM records checked, "
          f"{total['pending']} pending, {total['failed']} with acquisition or parsing errors.")


if __name__ == "__main__":
    main()
