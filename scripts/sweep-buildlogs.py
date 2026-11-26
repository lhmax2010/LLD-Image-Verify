#!/usr/bin/env python3
"""Inventory and extract linker/compiler evidence from published snapshot logs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin
from urllib.request import urlopen

HOST = "https://download.tizen.org/"
BASE = HOST + "snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_"
UNIFIED = HOST + "RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_"
SNAPSHOTS = {
    "Base": [BASE + s for s in ("20261117.165617", "20261119.042539")],
    "Unified": [UNIFIED + s for s in ("20261119.012153", "20261120.082536")],
}
ARCHES = ("aarch64", "armv7l", "x86_64")
PATTERNS = {
    "root_toolchain": r"\b(?:installing|keeping|updating|preinstalling|cumulate)\s+(?:clang|llvm|libllvm|lld|binutils|gcc)(?=-|\s)|^\s*(?:clang|llvm|libllvm|lld|binutils|gcc)(?:-[\w.+]+)+\s+#+\s*$",
    "cc_cxx_export": r"\bexport\s+(?:[^;&]*?\s)?(?:CC|CXX)(?==|\s|$)",
    "cmake_compiler": r"\b(?:C|CXX|C\+\+) compiler identification is\b",
    "meson_compiler": r"\b(?:C|C\+\+) compiler for the (?:host|build) machine:",
    "meson_host_linker": r"\blinker for the host machine:",
    "linker_override": r"-fuse-ld\b|--ld-path\b|(?:^|[\s;'\"-])(?:LD|LD_FOR_TARGET|CMAKE_LINKER|CMAKE_(?:C|CXX)_COMPILER_LINKER|C_LD|CPP_LD)\s*(?:=|:)|\bexport\s+LD\b",
    "linker_probe": r"checking (?:for (?:[^\s]+-)?ld(?:\.lld|\.bfd|\.gold)?(?:\s|$)|.*linker).*?(?:/[^\s]+/ld(?:\.\w+)?\b|GNU ld|LLD)",
    "llvm_configuration": r"-DCLANG_DEFAULT_LINKER=|-DLLVM_ENABLE_PROJECTS=|(?:[\s/]|^)clang[^\s/]*\.cfg\b|/usr/bin/ld\.lld\b",
    "configure_compiler": r"checking (?:whether (?:we are using the GNU (?:C|C\+\+) compiler|the compiler is (?:GCC|Clang))|for (?:[^\s:]+-)?(?:gcc|g\+\+|clang(?:\+\+)?))\.\.\.",
    "root_start": r'started (?:["\']?build(?:ing)?\b|\S+ )|\bbuild started\b' ,
    "root_setup": r"\bpreinstalling\s+|checking build system|initializing build root",
}
MATCH = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in PATTERNS.items()), re.I)
DETAIL = {name: re.compile(pattern, re.I) for name, pattern in PATTERNS.items()}
STAMP = re.compile(r"^\[\s*(\d+)s\]\s*")
SECRET = re.compile(r"(?i)\b(?:password|passwd|secret|credential|authorization|cookie|access[_-]?token|refresh[_-]?token)\s*[=:]|https?://[^\s/@]+:[^\s/@]+@|PRIVATE KEY-----")


class Links(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.hrefs = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href")
        if tag == "a" and href and href != "../" and "/" not in href.strip("/"):
            self.hrefs.append(href)


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(url, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise


def discover(root, arch):
    url = f"{root}/builddata/buildlogs/standard/{arch}/"
    todo = [(url, "root")]
    while todo:
        directory, status = todo.pop()
        index = fetch(directory)
        yield ("index", status, directory, index)
        for href in Links(index.decode()).hrefs:
            target = urljoin(directory, href)
            if href.endswith("/"):
                todo.append((target, href.rstrip("/")))
            elif href.endswith(".buildlog.txt") or href.endswith(".buildlog.txt.gz"):
                yield ("log", status, target, None)


def scan(task, cache, retry_errors):
    repo, snapshot, arch, status, url = task
    package = unquote(url.rsplit("/", 1)[1]).split(".buildlog.txt")[0]
    receipt = cache / repo / snapshot / arch / status / (package + ".json")
    if receipt.exists():
        cached = json.loads(receipt.read_text())
        if cached[0].get("schema") == 2 and (not cached[0]["error"] or not retry_errors):
            return cached
    row = dict(repository=repo, snapshot=snapshot, arch=arch, status=status,
               package=package, url=url, bytes=0, sha256="", lines=0,
               duration_seconds="", error="", schema=2)
    evidence = {}
    try:
        raw = fetch(url)
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if url.endswith(".gz"):
            import gzip
            raw = gzip.decompress(raw)
        lines = raw.splitlines()
        row["lines"] = len(lines)
        for number, raw_line in enumerate(lines, 1):
            line = raw_line.decode(errors="replace")
            stamp = STAMP.match(line)
            if stamp:
                row["duration_seconds"] = int(stamp[1])
            if not MATCH.search(line):
                continue
            line_without_stamp = STAMP.sub("", line).strip()
            for name, pattern in DETAIL.items():
                if pattern.search(line_without_stamp):
                    entries = evidence.setdefault(name, {})
                    key = "[redacted]" if SECRET.search(line_without_stamp) else line_without_stamp
                    previous = entries.setdefault(key, [number, number, 0])
                    previous[1] = number
                    previous[2] += 1
        for name in PATTERNS:
            row[name] = sum(entry[2] for entry in evidence.get(name, {}).values())
    except (OSError, ValueError) as exc:
        row["error"] = str(exc)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps([row, evidence], ensure_ascii=False) + "\n")
    return row, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--snapshot", action="append", help="Limit to these timestamp suffixes.")
    parser.add_argument("--extra-base", action="append", default=[], help="Add an RBS Base timestamp.")
    parser.add_argument("--package-pattern", help="Limit to matching source package log names.")
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tasks, indexes = [], []
    roots_to_scan = {name: values.copy() for name, values in SNAPSHOTS.items()}
    roots_to_scan["Base"].extend(BASE.replace("snapshots/", "RBS/") + value for value in args.extra_base)
    for repo, roots in roots_to_scan.items():
        for root in roots:
            snapshot = root.split("/")[-1]
            if args.snapshot and snapshot.split("_")[1] not in args.snapshot:
                continue
            for arch in ARCHES:
                try:
                    for kind, status, url, index in discover(root, arch):
                        if kind == "log":
                            package = unquote(url.rsplit("/", 1)[1]).split(".buildlog.txt")[0]
                            if not args.package_pattern or re.search(args.package_pattern, package):
                                tasks.append((repo, snapshot, arch, status, url))
                        else:
                            indexes.append([repo, snapshot, arch, status, url,
                                            hashlib.sha256(index).hexdigest(), ""])
                except OSError as exc:
                    indexes.append([repo, snapshot, arch, "", root, "", str(exc)])
    print(f"{len(tasks)} logs from {len(indexes)} indexes", flush=True)
    with (args.output / "buildlog-indexes.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["repository", "snapshot", "arch", "status", "index_url", "sha256", "error"])
        writer.writerows(indexes)
    scanned = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(scan, task, args.cache, args.retry_errors) for task in tasks]
        for number, future in enumerate(as_completed(futures), 1):
            scanned.append(future.result())
            if number % 250 == 0:
                print(f"{number}/{len(tasks)}", flush=True)
    columns = ["repository", "snapshot", "arch", "status", "package", "url", "bytes",
               "sha256", "lines", "duration_seconds", "error"]
    with ((args.output / "buildlogs.csv").open("w", newline="") as summary,
          (args.output / "buildlog-lines.csv").open("w", newline="") as excerpts):
        writer = csv.DictWriter(summary, columns + list(PATTERNS), extrasaction="ignore")
        writer.writeheader()
        excerpts_writer = csv.writer(excerpts)
        excerpts_writer.writerow(columns[:6] + ["category", "first_line", "last_line", "occurrences", "text"])
        for row, evidence in sorted(scanned, key=lambda item: tuple(item[0][key] for key in columns[:6])):
            writer.writerow(row)
            for category, entries in evidence.items():
                for line, locations in entries.items():
                    excerpts_writer.writerow([row[key] for key in columns[:6]] + [category, *locations, line])
    print(dict(Counter((r["snapshot"], r["arch"], bool(r["error"])) for r, _ in scanned)), flush=True)


if __name__ == "__main__":
    main()
