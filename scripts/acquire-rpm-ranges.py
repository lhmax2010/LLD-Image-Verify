#!/usr/bin/env python3
"""Finish large pending published RPMs with resumable HTTP ranges and payload verification."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from importlib import import_module
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit, urlunsplit

rpm = import_module("sweep-rpms")
CHUNK_SIZE = 32 * 1024 * 1024
CONTENT_RANGE = re.compile(rb"^content-range: bytes (\d+)-(\d+)/(\d+)\r?$", re.I | re.M)


def fetch_range(package, work, start, stop):
    digest, total = package["digest"], int(package["bytes"])
    part_dir = work / "ranges" / digest
    part_dir.mkdir(parents=True, exist_ok=True)
    part = part_dir / f"{start}-{stop}.part"
    header = part.with_suffix(".head")
    size = stop - start
    for attempt in range(4):
        initial = part.stat().st_size if part.exists() else 0
        if initial == size:
            return part
        target = start + initial
        url = urlsplit(package["url"])
        if attempt % 2 == 0:
            url = url._replace(netloc="cdn.download.tizen.org")
        header.unlink(missing_ok=True)
        with part.open("ab") as sink:
            transfer = subprocess.run(
                ["curl", "-fsSL", "--connect-timeout", "12", "--max-time", "900",
                 "--speed-time", "100", "--speed-limit", "4096", "--max-filesize", str(size-initial),
                 "--range", f"{target}-{stop-1}", "--dump-header", str(header), urlunsplit(url)],
                stdout=sink, stderr=subprocess.PIPE, check=False,
            )
        reported = CONTENT_RANGE.findall(header.read_bytes() if header.exists() else b"")
        if not reported or tuple(map(int, reported[-1])) != (target, stop-1, total):
            with part.open("r+b") as sink:
                sink.truncate(initial)
        if part.stat().st_size == size:
            header.unlink(missing_ok=True)
            return part
    raise OSError(f"Range {start}-{stop-1} incomplete for {package['rpm']} after retries: "
                  + transfer.stderr.decode(errors="replace").strip())


def receipt_path(work, digest):
    return work / "receipts" / digest[:2] / (digest + ".json")


def part_ranges(work, package):
    digest, size = package["digest"], int(package["bytes"])
    archive_dir = work / "downloads" / digest[:2]
    archive_dir.mkdir(parents=True, exist_ok=True)
    prefix_rpm = archive_dir / (digest + ".rpm")
    state_dir = work / "ranges" / digest
    state_dir.mkdir(parents=True, exist_ok=True)
    state = state_dir / "prefix.json"
    if state.exists():
        prefix = json.loads(state.read_text())["prefix"]
        if (prefix_rpm.stat().st_size if prefix_rpm.exists() else 0) != prefix:
            raise ValueError(f"RPM prefix changed on disk: {package['rpm']}")
    else:
        prefix = prefix_rpm.stat().st_size if prefix_rpm.exists() else 0
        state.write_text(json.dumps({"prefix": prefix}) + "\n")
    ranges = [(start, min(start + CHUNK_SIZE, size)) for start in range(prefix, size, CHUNK_SIZE)]
    return prefix_rpm, ranges


def assemble(package, work, archive, ranges):
    paths = sorted(ranges, key=lambda path: int(path.stem.split("-", 1)[0]))
    if paths:
        pending = archive.with_suffix(".assembled")
        with pending.open("wb") as sink:
            parts = ([archive] if archive.exists() else []) + paths
            for file in parts:
                with file.open("rb") as source:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
        if pending.stat().st_size != int(package["bytes"]):
            raise ValueError(f"Range assembly changed size: {package['rpm']}")
        pending.replace(archive)
    result = rpm.scan(package, work, {}, True, None)
    if not result["error"]:
        shutil.rmtree(work / "ranges" / package["digest"])
    return result["error"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=72)
    args = parser.parse_args()
    work = args.cache
    unique = {}
    with args.inventory.open(newline="") as f:
        for row in csv.DictReader(f):
            digest = row["digest"]
            if digest in unique:
                continue
            receipt = receipt_path(work, digest)
            if not receipt.exists() or json.loads(receipt.read_text())["error"]:
                row["bytes"] = int(row["bytes"])
                unique[digest] = row
    archives, remaining, received, failures = {}, {}, {}, Counter()
    packages = sorted(unique.values(), key=lambda item: item["bytes"], reverse=True)
    print(f"{len(packages)} RPMs, {sum(p['bytes'] for p in packages)/10**9:.2f} GB before partial data", flush=True)
    with (ThreadPoolExecutor(args.workers) as downloads, ThreadPoolExecutor(6) as scans):
        chunks, final = {}, {}
        for package in packages:
            digest = package["digest"]
            archive, ranges = part_ranges(work, package)
            archives[digest], remaining[digest], received[digest] = archive, len(ranges), []
            if not ranges:
                final[scans.submit(assemble, package, work, archive, [])] = package
            for start, stop in ranges:
                chunks[downloads.submit(fetch_range, package, work, start, stop)] = package
        for number, future in enumerate(as_completed(chunks), 1):
            package = chunks[future]
            digest = package["digest"]
            remaining[digest] -= 1
            try:
                received[digest].append(future.result())
            except OSError as exc:
                failures[digest] += 1
                print(exc, flush=True)
            if not remaining[digest] and not failures[digest]:
                final[scans.submit(assemble, package, work, archives[digest], received[digest])] = package
            if number % 25 == 0:
                print(f"{number}/{len(chunks)} HTTP ranges checked", flush=True)
        for future in as_completed(final):
            if error := future.result():
                failures[final[future]["digest"]] += 1
                print(error, flush=True)
    print(f"{len(packages)-len(failures)} / {len(packages)} RPM archives independently verified.", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
