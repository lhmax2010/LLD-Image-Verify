#!/usr/bin/env python3
"""Export the two historical image audits and reconcile supplemental linker proofs."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROUNDS = {
    "qb1234653": ("20261119.012153", "20261117.165617"),
    "latest": ("20261120.082536", "20261119.042539"),
}
IDENTITY = ("image", "partition", "path", "sha256")


def rows(path, delimiter=","):
    if not path.exists() and Path(str(path) + ".gz").exists():
        path = Path(str(path) + ".gz")
    open_file = gzip.open if path.suffix == ".gz" else open
    with open_file(path, "rt", newline="") as stream:
        yield from csv.DictReader(stream, delimiter=delimiter)


def write_csv(path, records):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def identities(rows_to_index):
    return {tuple(r[key] for key in IDENTITY): r for r in rows_to_index}


def arch_from_image(image):
    return re.search(r"(?:^|-)(aarch64|armv7l|x86_64)(?:-|$)", image)[1]


def rpm_arch(label):
    return label.split()[0].rsplit(".", 1)[1]


def classification_refs(row, previous, supplemental, prebuilt):
    history = row["classification"]
    confirmed_identity = row["linker"]
    refs = [f"evidence/archive/statistics/{row['round']}/elf-results.tsv.gz"]
    if supplemental:
        history = supplemental["classification"]
        refs.append(supplemental["reference"])
        if history == "gnu-ld-confirmed":
            confirmed_identity = supplemental.get("replay_linker") or "GNU ld"
        if history == "dart-aot-elf-writer":
            confirmed_identity = "Dart AOT ELF writer"
    if row["debug_rpm"]:
        refs.append(f"{row['debug_rpm']} ({row['debug_path']}, debuglink CRC {row['debug_crc']})")
    if row["trace_url"]:
        refs.append(row["trace_url"] + (f" lines {row['trace_lines']}" if row["trace_lines"] else ""))
    if row["trace"].startswith("toybox-execution/"):
        refs.append("evidence/archive/evidence/2026-11-23/" + row["trace"])
    if row["classification"] == "gnu-ld-confirmed" and row["source"].endswith("/glibc"):
        location = f"{row['base_snapshot']}/builddata/buildlogs/standard/{row['arch']}/succeeded/glibc.buildlog.txt"
        refs.append("https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/" + location)
    if history == "not-lld-22.1.8":
        refs.append(f"evidence/archive/evidence/2026-11-23/{'latest-' if row['round'] == 'latest' else ''}"
                    f"base-probe/{row['arch']}/")
    disposition = history
    if prebuilt:
        disposition = "not-linked-by-our-toolchain"
        refs.append(f"evidence/prebuilt-{row['snapshot']}.csv, {row['sha256']}")
    elif history == "dart-aot-elf-writer":
        disposition = "not-linked-by-our-toolchain"
    elif history == "unresolved" and previous and previous["elf_byte_match"] == "True":
        disposition = "not-linked-by-our-toolchain"
        refs.append(f"evidence/archive/results/2026-11-23-unresolved/voice-source-provenance.tsv, {row['sha256']}")
    return history, disposition, confirmed_identity, " | ".join(refs)


def sources(path, round_name):
    proof_sets = (("2026-11-23-unresolved", f"{round_name}-follow-up.tsv"),
                  ("2026-11-23-sed-tzdata", f"{round_name}-confirmed.tsv"))
    fixes = {}
    for run, filename in proof_sets:
        for row in rows(path / "results" / run / filename, "\t"):
            if row["classification"] == "unresolved":
                continue
            row["reference"] = f"evidence/archive/results/{run}/{row['evidence_file']}"
            fixes[tuple(row[key] for key in IDENTITY)] = row
    return fixes


def verdict(counts, ambiguous):
    native = sum(counts.values())
    prebuilt = counts["not-linked-by-our-toolchain"]
    lld = counts["lld-confirmed"]
    other = counts["gnu-ld-confirmed"] + counts["other-linker-confirmed"]
    open_count = native - lld - other - prebuilt
    if lld and (other or prebuilt):
        return "mixed"
    if open_count or ambiguous:
        return "open"
    if not native:
        return "no native files"
    if lld and not other:
        return "all-LLD"
    if other:
        return "non-LLD"
    return "prebuilt-only"


def make_round(root, inputs, round_name, nevras):
    stamp, base = ROUNDS[round_name]
    source = inputs / "statistics" / round_name
    snapshot = "tizen-unified-toolchain_" + stamp
    base_snapshot = "tizen-base-toolchain_" + base
    inventory = list(rows(source / "rpm-results.tsv", "\t"))
    proof = sources(inputs, round_name)
    voice = {r["sha256"]: r for r in rows(inputs / "results/2026-11-23-unresolved/voice-source-provenance.tsv", "\t")}
    prebuilt_file = root / f"evidence/prebuilt-{stamp}.csv"
    prebuilt = {r["image_sha256"] for r in rows(prebuilt_file) if r["byte_match"] == "True"} if prebuilt_file.exists() else set()
    ownership = root / "evidence/recovered-image-rpm-owners.csv"
    recovered = identities(r for r in rows(ownership) if r["snapshot"] == snapshot) if ownership.exists() else {}
    rows_out, packages_out = [], []
    by_rpm = defaultdict(list)
    ambiguous = Counter()
    results = Counter()
    for row in rows(source / "elf-results.tsv", "\t"):
        row.update(snapshot=stamp, base_snapshot=base_snapshot, round=round_name, arch=arch_from_image(row["image"]))
        key = tuple(row[k] for k in IDENTITY)
        history, final, linker, refs = classification_refs(row, voice.get(row["sha256"]),
                                                               proof.get(key), row["sha256"] in prebuilt)
        repo = {"base": "Base", "unified": "Unified", "": "Unattributed"}[row["repository"]]
        historical_repo = repo
        if provenance := recovered.get(key):
            assert repo == "Unattributed" and final == "lld-confirmed"
            repo = "Unified"
            row.update(rpm=provenance["rpm_label"], source=provenance["source"],
                       source_commit=provenance["source_commit"], runtime_rpm_url=provenance["rpm_url"],
                       rpm_match="exact payload SHA256 after profile rename",
                       runtime_rpm_sha256=provenance["rpm_payload_sha256"])
            refs += " | evidence/recovered-image-rpm-owners.csv"
        package_snap = base_snapshot if repo == "Base" else snapshot if repo == "Unified" else ""
        labels = row["rpm"].split("|") if row["rpm"] else []
        selected = labels[0] if len(labels) == 1 else ""
        available = nevras.get((package_snap, selected), set())
        row_out = dict(snapshot=snapshot, base_snapshot=base_snapshot,
                       image=row["image"], arch=row["arch"], partition=row["partition"], path=row["path"],
                       sha256=row["sha256"], build_id=row["build_id"], rpm_nevra=next(iter(available)) if len(available) == 1 else "",
                       rpm_label=selected, rpm_owner_candidates=row["rpm"] if len(labels) > 1 else "",
                       repository=repo, historical_repository=historical_repo, evidence_class=final, historical_class=history,
                       evidence_reference=refs, kind=row["kind"], elf_machine=row["machine"],
                       source=row["source"], source_commit=row["source_commit"], linker=linker,
                       runtime_rpm_url=row["runtime_rpm_url"], verified_runtime_elf_sha256=row["runtime_rpm_sha256"],
                       rpm_match=row["rpm_match"], comments=row["comments"], debug_matched=row["debug_matched"],
                       debug_rpm_url=row["debug_rpm"], debug_path=row["debug_path"], debug_comments=row["debug_comments"],
                       debuglink=row["debuglink"], debuglink_crc=row["debug_crc"], archive_evidence=row["evidence"], module_log=row["module_log"],
                       trace_lines=row["trace_lines"], remaining_reason=row["remaining_reason"])
        rows_out.append(row_out)
        if row["classification"] != "static-archive":
            results[history] += 1
        if selected:
            by_rpm[selected, row["source"], row["source_commit"]].append(row_out)
        elif len(labels) > 1:
            ambiguous.update(labels)
    assert len(rows_out) == 10887 and sum(results.values()) == 10875, (snapshot, len(rows_out), results)
    assert results["gnu-ld-confirmed"] == 140 and results["lld-confirmed"] == 6892, results
    for item in inventory:
        key = tuple(item[k] for k in ("rpm", "source", "source_commit"))
        entries = by_rpm[key]
        native = [r for r in entries if r["evidence_class"] != "static-archive"]
        counts = Counter(r["evidence_class"] for r in native)
        options = {n for release in (base_snapshot, snapshot) for n in nevras.get((release, item["rpm"]), set())}
        packages_out.append(dict(snapshot=snapshot, arch=rpm_arch(item["rpm"]), rpm_label=item["rpm"],
                                 rpm_nevra=next(iter(options)) if len(options) == 1 else "", source=item["source"],
                                 source_commit=item["source_commit"], verdict=verdict(counts, ambiguous[item["rpm"]]),
                                 native_instances=len(native), distinct_native_sha256=len({r["sha256"] for r in native}),
                                 static_archives=len(entries) - len(native),
                                 ambiguous_owner_instances=ambiguous[item["rpm"]],
                                 evidence_counts=json.dumps(counts, sort_keys=True)))
    assert len(packages_out) == 2556
    return rows_out, packages_out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--repodata-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from importlib import import_module
    rpms = import_module("sweep-rpms")
    nevras = defaultdict(set)
    for roots in rpms.logs.SNAPSHOTS.values():
        for url in roots:
            for rpm in rpms.index(url, "packages", args.repodata_cache):
                nevras[(rpm["snapshot"], rpm["image_key"])].add(rpm["nevra"])
    all_instances, all_rpms, unified, unowned = [], [], [], []
    for label in ROUNDS:
        instances, rpm_rows = make_round(args.repo, args.archive, label, nevras)
        all_instances += instances
        all_rpms += rpm_rows
        exceptional = [r for r in instances if r["repository"] == "Unified" and r["historical_class"]
                       not in ("lld-confirmed", "static-archive")]
        assert len(exceptional) == 179
        assert Counter(r["historical_class"] for r in exceptional) == {
            "gnu-ld-confirmed": 14, "gnu-ld-like-layout": 96, "lld-layout": 24,
            "unresolved": 35, "other-linker-confirmed": 8, "dart-aot-elf-writer": 2
        }
        unified += exceptional
        orphan = [r for r in instances if r["historical_repository"] == "Unattributed" and r["evidence_class"] == "lld-confirmed"]
        assert len(orphan) == 16
        unowned += orphan
        write_csv(args.output / f"image-instances-{ROUNDS[label][0]}.csv", instances)
    write_csv(args.output / "image-rpm-verdicts.csv", all_rpms)
    write_csv(args.output / "unified-exception-instances.csv", unified)
    write_csv(args.output / "unattributed-lld-instances.csv", unowned)
    write_csv(args.output / "image-rpm-membership.csv", [
        {"snapshot": prefix + timestamp, "rpm": r["rpm_label"], "source_commit": r["source_commit"]}
        for r in all_rpms for prefix, timestamp in (
            ("tizen-unified-toolchain_", r["snapshot"].split("_")[1]),
            ("tizen-base-toolchain_", {pair[0]: pair[1] for pair in ROUNDS.values()}[r["snapshot"].split("_")[1]]))
    ])
    summaries = []
    for snapshot in sorted({r["snapshot"] for r in all_instances}):
        cohort = [r for r in all_instances if r["snapshot"] == snapshot]
        for dimension in ("overall", "repository", "historical_repository", "arch", "image"):
            groups = defaultdict(list)
            for instance in cohort:
                if instance["evidence_class"] != "static-archive":
                    groups[instance.get(dimension, "all")].append(instance)
            for group, entries in sorted(groups.items()):
                for evidence, count in sorted(Counter(r["evidence_class"] for r in entries).items()):
                    summaries.append(dict(snapshot=snapshot, dimension=dimension, group=group,
                                          evidence_class=evidence, instances=count, denominator=len(entries),
                                          distinct_sha256=len({r["sha256"] for r in entries if r["evidence_class"] == evidence})))
    write_csv(args.output / "image-class-denominators.csv", summaries)


if __name__ == "__main__":
    main()
