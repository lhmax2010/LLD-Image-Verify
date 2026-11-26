#!/usr/bin/env python3
"""Retrieve exact Unified SRPM inputs and published build-root package versions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
from importlib import import_module
import json
from pathlib import Path
import subprocess

prepare = import_module("prepare-unified-replay")


def srpm_sources(data, names):
    sources = {name: set() for name in names}
    with gzip.open(data / "rpm-inventory.csv.gz", "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["snapshot"] != prepare.UNIFIED.rsplit("/", 1)[-1]:
                continue
            source = row["source"]
            name = source.removesuffix(".src.rpm").rsplit("-", 2)[0]
            if name in sources:
                sources[name].add(source)
    return {name: values.pop() for name, values in sources.items() if len(values) == 1}


def unpack(name, filename, output):
    url = f"{prepare.UNIFIED}/repos/standard/source/{filename}"
    archive = prepare.obtain(url, output / "srpm" / filename)
    uri = output / "sources" / name
    uri.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen(["rpm2cpio", archive], stdout=subprocess.PIPE) as payload:
        subprocess.run(["cpio", "-idmu", "--quiet", "--no-absolute-filenames"],
                       cwd=uri, stdin=payload.stdout, check=True)
        if payload.wait():
            raise ValueError(filename)
    result = subprocess.check_output(["rpm", "-qp", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VCS}\n",
                                      archive], text=True).strip().split("\t")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(package=name, url=url, rpm=filename, evr=result[1], vcs=result[2], sha256=digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", action="append", required=True)
    parser.add_argument("--arch", choices=prepare.ARCHES, action="append")
    parser.add_argument("--workspace-inputs", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = args.workspace_inputs.resolve()
    output.mkdir(parents=True, exist_ok=True)
    names = srpm_sources(args.data, args.package)
    if missing := set(args.package) - names.keys():
        print("No unambiguous SRPM: " + ", ".join(sorted(missing)), flush=True)
    with ThreadPoolExecutor(10) as pool:
        tasks = {pool.submit(unpack, name, filename, output): name for name, filename in names.items()}
        receipts = []
        for task, name in tasks.items():
            try:
                receipts.append(task.result())
                print(f"{name}: source pinned", flush=True)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                print(f"{name}: {error}", flush=True)
        (output / "sources.json").write_text(json.dumps(receipts, indent=2) + "\n")
        if not args.arch:
            return
        # Reuse checksum-pinned RPMs across trial build roots. Keep version matching explicit.
        available = {}
        for repo in (prepare.BASE, prepare.UNIFIED):
            for item in prepare.rpm.index(repo, "packages", work / "repodata"):
                evr = item["image_key"].split(" ", 1)[1]
                available[item["arch"], item["name"], evr] = item
        with (args.data / "buildlogs.csv").open(newline="") as stream:
            logs = [row for row in csv.DictReader(stream) if row["snapshot"] == prepare.UNIFIED.rsplit("/", 1)[-1]
                    and row["package"] in names and row["arch"] in args.arch and row["status"] == "succeeded"]
        downloads = {}
        for row in logs:
            name, arch = row["package"], row["arch"]
            local = output / "logs" / arch / f"{name}.txt"
            prepare.obtain(row["url"], local, row["sha256"])
            deps = prepare.build_dependencies(local.read_text(errors="replace"))
            known, missing = [], {}
            for binary, evr in deps.items():
                item = available.get((arch, binary, evr)) or available.get(("noarch", binary, evr))
                if not item:
                    missing[binary] = evr
                    continue
                known.append(item)
                archive = work / "packages" / item["rpm"]
                if archive not in downloads:
                    downloads[archive] = pool.submit(prepare.obtain, item["url"], archive, item["digest"], item["algo"])
            result = dict(log=row["url"], arch=arch, package=name, pinned=known, missing=missing)
            (local.parent / f"{name}.inputs.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"{arch}/{name}: {len(known)}/{len(deps)} exact root packages", flush=True)
        for job in downloads:
            downloads[job].result()


if __name__ == "__main__":
    main()
