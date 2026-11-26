#!/usr/bin/env python3
"""Scan published RPM payloads, pairing debug files by CRC or Build ID and architecture."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "share" / "tizen-lld-verify"))
from scan_images import handle_file, scan_elf
from importlib import import_module
logs = import_module("sweep-buildlogs")
ARCHES = {*logs.ARCHES, "noarch"}
COLUMNS = ("path", "kind", "machine", "linker", "evidence", "comments", "build_id",
           "sha256", "debuglink", "debug_crc", "load_flags", "relro_delta", "version_parent")
COMPILER = re.compile(r"(?:^| \| )(?:clang version\b|(?:Tizen |Apple )?clang version\b|GCC:|GNU C\b|Intel\(R\))", re.I)


def csv_rows(path):
    with path.open(newline="") as stream:
        yield from csv.DictReader(stream)


def index(root, kind, cache):
    repo = f"{root}/repos/standard/{kind}/"
    key = root.rsplit("/", 1)[1]
    path = cache / f"{key}-{kind}-primary.xml.gz"
    if not path.exists():
        repomd = ET.fromstring(logs.fetch(urljoin(repo, "repodata/repomd.xml")))
        data = repomd.find('{*}data[@type="primary"]')
        content = logs.fetch(urljoin(repo, data.find("{*}location").get("href")))
        checksum = data.find("{*}checksum")
        if hashlib.new(checksum.get("type"), content).hexdigest() != checksum.text:
            raise ValueError(f"{repo} primary checksum mismatch")
        path.write_bytes(content)
    with gzip.open(path) as stream:
        packages = ET.parse(stream).getroot()
    for element in packages:
        arch = element.findtext("{*}arch")
        if arch not in ARCHES:
            continue
        href = element.find("{*}location").get("href")
        version = element.find("{*}version")
        name = element.findtext("{*}name")
        checksum = element.find("{*}checksum")
        yield dict(snapshot=key, arch=arch, kind=kind, name=name, url=urljoin(repo, href),
                   rpm=href.rsplit("/", 1)[-1], algo=checksum.get("type"), digest=checksum.text,
                   nevra=f'{name}-{version.get("epoch", "0")}:{version.get("ver")}-{version.get("rel")}.{arch}',
                   image_key=f'{name}.{arch} {version.get("ver")}-{version.get("rel")}',
                   source=element.findtext("{*}format/{*}sourcerpm") or "",
                   vcs=version.get("vcs", ""),
                   bytes=int(element.find("{*}size").get("package")))


def take(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise EOFError("Truncated cpio payload")
    return data


def discard(stream, count):
    while count:
        block = min(count, 1024 * 1024)
        take(stream, block)
        count -= block


def payload(rpm, work, debug):
    files, errors = [], []
    with subprocess.Popen(["rpm2cpio", str(rpm)], stdout=subprocess.PIPE) as process:
        stream = process.stdout
        try:
            while True:
                header = take(stream, 110)
                if header[:6] not in (b"070701", b"070702"):
                    raise ValueError("Invalid cpio header")
                mode = int(header[14:22], 16)
                size = int(header[54:62], 16)
                length = int(header[94:102], 16)
                name = take(stream, length)[:-1].decode(errors="replace")
                discard(stream, -(110 + length) % 4)
                if name == "TRAILER!!!":
                    stream.read()
                    break
                name = "/" + name.removeprefix("./").lstrip("/")
                prefix = take(stream, min(size, 8))
                relative = Path(name)
                archive = prefix in (b"!<arch>\n", b"!<thin>\n")
                zipped = prefix.startswith(b"PK") and relative.suffix.lower() in (".zip", ".tpk", ".wgt", ".jar", ".apk")
                inspect = (mode & 0o170000 == 0o100000 and
                           (prefix.startswith(b"\x7fELF") or (not debug and (archive or zipped))))
                if not inspect:
                    discard(stream, size - len(prefix))
                    discard(stream, -size % 4)
                    continue
                with tempfile.SpooledTemporaryFile(max_size=4*1024*1024, dir=work) as file:
                    file.write(prefix)
                    crc = zlib.crc32(prefix)
                    remaining = size - len(prefix)
                    while remaining:
                        block = take(stream, min(remaining, 1024 * 1024))
                        file.write(block)
                        if debug:
                            crc = zlib.crc32(block, crc)
                        remaining -= len(block)
                    file.seek(0)
                    metadata = {"gold_note": False}
                    try:
                        if prefix.startswith(b"\x7fELF"):
                            parsed = [(name, scan_elf(file, metadata))]
                        else:
                            parsed = handle_file(name, file)
                        for file_path, row in parsed:
                            item = dict(zip(COLUMNS, (file_path, *row)))
                            item.update(metadata)
                            if debug:
                                item["file_crc"] = f"{crc:08x}"
                            elif item["kind"] == "archive":
                                file.seek(0)
                                item["sha256"] = hashlib.file_digest(file, "sha256").hexdigest()
                            files.append(item)
                    except (ValueError, OSError, struct.error, EOFError, RuntimeError, zipfile.BadZipFile) as exc:
                        errors.append({"path": name, "error": str(exc)})
                discard(stream, -size % 4)
        except BaseException:
            process.kill()
            raise
        if process.wait():
            raise ValueError("rpm2cpio failed")
    return files, errors


def scan(package, work, local_cache, retry_errors, mirror):
    digest = package["digest"]
    folder = work / "receipts" / digest[:2]
    receipt = folder / (digest + ".json")
    if receipt.exists():
        cached = json.loads(receipt.read_text())
        if not cached["error"] or not retry_errors:
            return cached
    folder.mkdir(parents=True, exist_ok=True)
    cached = {"files": [], "errors": [], "error": ""}
    try:
        candidates = local_cache.get(package["rpm"], [])
        def digest_of(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, package["algo"]).hexdigest()
        rpm = next((path for path in candidates if digest_of(path) == digest), None)
        own_download = rpm is None
        if own_download:
            partial = work / "downloads" / digest[:2]
            partial.mkdir(parents=True, exist_ok=True)
            rpm = partial / (digest + ".rpm")
            url = package["url"]
            if mirror:
                parts = urlsplit(url)
                url = urlunsplit(parts._replace(netloc=mirror))
            if not rpm.exists() or rpm.stat().st_size != package["bytes"]:
                subprocess.run(["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "1800",
                                "--speed-time", "80", "--speed-limit", "2048", "--continue-at", "-",
                                "--retry", "2", url, "-o", str(rpm)], check=True, stderr=subprocess.PIPE)
            if digest_of(rpm) != digest:
                rpm.unlink()
                raise ValueError("RPM repodata checksum mismatch")
        cached["files"], cached["errors"] = payload(rpm, work, package["kind"] == "debug")
        if own_download:
            rpm.unlink()
    except (OSError, ValueError, EOFError, subprocess.CalledProcessError) as exc:
        cached["error"] = str(exc.stderr.decode(errors="replace").strip() if isinstance(exc, subprocess.CalledProcessError) else exc)
    with tempfile.NamedTemporaryFile(dir=folder, mode="w", delete=False) as stream:
        stream.write(json.dumps(cached) + "\n")
    Path(stream.name).replace(receipt)
    return cached


def debug_indexes(results):
    by_id, by_crc = defaultdict(list), defaultdict(list)
    for package, result in results:
        scope = package["snapshot"], package["arch"]
        for file in result["files"]:
            if file["build_id"]:
                by_id[*scope, file["machine"], file["build_id"]].append((package, file))
            by_crc[*scope, file["machine"], file["file_crc"]].append((package, file))
    return by_id, by_crc


def paired(package, file, indexes):
    scope = package["snapshot"], package["arch"], file["machine"]
    by_id, by_crc = indexes
    if file["debug_crc"]:
        candidates = by_crc.get((*scope, file["debug_crc"]), [])
    elif file["build_id"]:
        candidates = by_id.get((*scope, file["build_id"]), [])
    else:
        return None, None
    expected = "/usr/lib/debug" + file["path"].rsplit("/", 1)[0] + "/" + file["debuglink"]
    valid = {}
    for debug, member in candidates:
        if file["build_id"] and file["build_id"] != member["build_id"]:
            continue
        if not file["build_id"] and member["path"] != expected and debug["source"] != package["source"]:
            continue
        valid[member["sha256"]] = debug, member
    return next(iter(valid.values())) if len(valid) == 1 else (None, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True, help="Image RPM CSV with snapshot and rpm label")
    parser.add_argument("--local-cache", type=Path, action="append", default=[])
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--largest-first", action="store_true",
                        help="Start large RPM transfers early to shorten the final download tail.")
    parser.add_argument("--snapshot", action="append")
    parser.add_argument("--extra-base", action="append", default=[])
    parser.add_argument("--package-pattern", help="Regular expression on binary package names.")
    parser.add_argument("--include-observed", action="store_true")
    parser.add_argument("--summarize-only", action="store_true",
                        help="Use existing cache receipts and mark remaining payloads pending.")
    parser.add_argument("--debug-url-file", type=Path, help="Scan these debuginfo URLs, one per line.")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--mirror", help="Optional download mirror hostname. Repodata digests are still verified.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    installed = defaultdict(set)
    for row in csv_rows(args.inventory):
        installed[row["snapshot"]].add((row["rpm"], row.get("source_commit", "")))
    targets = []
    base_rbs = logs.BASE.replace("snapshots/", "RBS/")
    roots_to_scan = [*logs.SNAPSHOTS.values(), [base_rbs + snap for snap in args.extra_base]]
    debug_urls = set(args.debug_url_file.read_text().splitlines()) if args.debug_url_file else set()
    for roots in roots_to_scan:
        for root in roots:
            key = root.rsplit("_", 1)[1]
            if args.snapshot and key not in args.snapshot:
                continue
            targets.extend((key, root, kind) for kind in ("packages", "debug"))
    with ThreadPoolExecutor(args.workers) as pool:
        indexes = list(pool.map(lambda target: (target[0], list(index(target[1], target[2], args.cache))), targets))
    packages, debuginfo = [], []
    for key, index_rows in indexes:
        for package in index_rows:
            if debug_urls and package["url"] not in debug_urls:
                continue
            if args.package_pattern and not re.search(args.package_pattern, package["name"]):
                continue
            if package["kind"] == "packages":
                if not args.include_observed and (
                    (package["image_key"], package["vcs"].rpartition("#")[2]) in installed[key]
                    or (package["image_key"], "") in installed[key]
                ):
                    continue
                packages.append(package)
            elif package["name"].endswith("-debuginfo"):
                debuginfo.append(package)
    # Debug packages can contain members shared by several runtime subpackages.
    # Scan all debuginfo to recover debuglink-only matches and image-rule note state.
    planned = packages + debuginfo
    if not planned:
        raise ValueError("No matching published RPMs")
    with (args.output / "rpm-inventory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, list(planned[0]))
        writer.writeheader()
        writer.writerows(sorted(planned, key=lambda q: q["url"]))
    print(f"{len(packages)} runtime RPMs and {len(debuginfo)} debuginfo RPMs; "
          f"{sum(p['bytes'] for p in planned)/10**9:.2f} GB before deduplication", flush=True)
    by_digest = defaultdict(list)
    for package in planned:
        by_digest[package["digest"]].append(package)
    results = {}
    if args.summarize_only:
        for digest in by_digest:
            file = args.cache / "receipts" / digest[:2] / (digest + ".json")
            results[digest] = (json.loads(file.read_text()) if file.exists()
                               else {"files": [], "errors": [], "error": "pending"})
    else:
        local = defaultdict(list)
        for root in args.local_cache:
            for path in root.rglob("*.rpm"):
                local[path.name].append(path)
        with ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(scan, entries[0], args.cache, local, args.retry_errors, args.mirror): digest
                       for digest, entries in sorted(by_digest.items(), key=lambda item: item[1][0]["bytes"],
                                                     reverse=args.largest_first)}
            for number, future in enumerate(as_completed(futures), 1):
                results[futures[future]] = future.result()
                if number % 250 == 0:
                    print(f"{number}/{len(futures)} distinct RPM payloads", flush=True)
    debug_results = [(p, results[p["digest"]]) for p in debuginfo]
    indexes = debug_indexes(debug_results)
    with ((args.output / "rpm-pass.csv").open("w", newline="") as summary,
          gzip.open(args.output / "rpm-elf-evidence.csv.gz", "wt", newline="") as detail,
          gzip.open(args.output / "debuginfo-evidence.csv.gz", "wt", newline="") as debugout):
        fields = ["snapshot", "arch", "kind", "nevra", "url", "digest", "source"]
        writer = csv.writer(summary)
        writer.writerow(fields + ["native_files", "static_archives", "paired", "lld_confirmed",
                                  "other_linker_confirmed", "open", "verdict", "error", "file_errors"])
        elves = csv.writer(detail)
        elves.writerow(fields + [*COLUMNS, "gold_note", "debug_url", "debug_path", "debug_sha256",
                                  "debug_build_id", "debug_file_crc", "debug_comments", "debug_gold_note",
                                  "evidence_class"])
        dbg = csv.writer(debugout)
        dbg.writerow(fields + [*COLUMNS, "gold_note", "file_crc"])
        for package in sorted(planned, key=lambda p: p["url"]):
            result = results[package["digest"]]
            identity = [package[key] for key in fields]
            counts = Counter()
            for file in result["files"]:
                if package["kind"] == "debug":
                    dbg.writerow(identity + [file.get(key, "") for key in (*COLUMNS, "gold_note", "file_crc")])
                    counts["debug"] += 1
                    continue
                if file["kind"] == "archive":
                    counts["archive"] += 1
                    continue
                debug_package, debug = paired(package, file, indexes)
                markers = {entry["linker"] for entry in (file, debug) if entry and entry["linker"] != "unknown"}
                classification = ("lld-confirmed" if markers == {"LLD"} else
                                  "other-linker-confirmed" if len(markers) == 1 and "conflicting" not in markers
                                  else "insufficient-evidence")
                counts[classification] += 1
                counts["paired"] += debug is not None
                debug_fields = [debug_package["url"], *[debug[key] for key in
                    ("path", "sha256", "build_id", "file_crc", "comments", "gold_note")]] if debug else [""]*7
                elves.writerow(identity + [file.get(key, "") for key in (*COLUMNS, "gold_note")] +
                                debug_fields + [classification])
            lld, other, open_count = (counts[key] for key in
                                      ("lld-confirmed", "other-linker-confirmed", "insufficient-evidence"))
            if result["error"] or result["errors"]:
                verdict = "incomplete"
            elif package["kind"] == "debug":
                verdict = "debug-evidence"
            elif lld and other:
                verdict = "mixed"
            elif open_count:
                verdict = "open"
            elif lld:
                verdict = "all-LLD"
            elif other:
                verdict = "non-LLD"
            else:
                verdict = "no native files"
            writer.writerow(identity + [lld + other + open_count + counts["debug"], counts["archive"],
                counts["paired"], lld, other, open_count, verdict, result["error"],
                json.dumps(result["errors"]) if result["errors"] else ""])
    print(f"{len(results)} distinct RPMs, {sum(bool(x['error']) for x in results.values())} payload failures",
          flush=True)


if __name__ == "__main__":
    main()
