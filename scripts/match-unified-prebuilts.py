#!/usr/bin/env python3
"""Match Unified package and image ELF SHA256s against ELF members of published SRPMs."""
import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

SNAPSHOT = "tizen-unified-toolchain_20261120.082536"


def elf_hash(stream):
    if stream.read(4) != b"\x7fELF":
        return None
    digest = hashlib.sha256(b"\x7fELF")
    while data := stream.read(1024 * 1024):
        digest.update(data)
    return digest.hexdigest()


def zip_members(stream, label):
    with zipfile.ZipFile(stream) as archive:
        for item in archive.infolist():
            with archive.open(item) as member:
                if digest := elf_hash(member):
                    yield f"{label}!/{item.filename}", digest


def tar_members(path):
    with tarfile.open(path) as archive:
        for item in archive:
            if not item.isfile():
                continue
            with archive.extractfile(item) as data:
                label = f"{path.name}!/{item.name}"
                if item.name.lower().endswith((".tpk", ".wgt", ".zip")):
                    if zipfile.is_zipfile(data):
                        data.seek(0)
                        yield from zip_members(data, label)
                elif item.name.lower().endswith(".rpm"):
                    yield from rpm_members(data, label)
                elif digest := elf_hash(data):
                    yield label, digest


def source_members(path):
    if tarfile.is_tarfile(path):
        yield from tar_members(path)
    elif path.suffix.lower() in (".tpk", ".wgt", ".zip") and zipfile.is_zipfile(path):
        yield from zip_members(path, path.name)
    else:
        with path.open("rb") as data:
            if digest := elf_hash(data):
                yield path.name, digest


def rpm_members(stream, label):
    data = subprocess.run(["rpm2cpio", "-"], input=stream.read(), capture_output=True, check=True).stdout
    offset = 0
    while offset < len(data):
        header = data[offset:offset + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError(f"Bad CPIO header in {label}")
        size, name_size = int(header[54:62], 16), int(header[94:102], 16)
        offset += 110
        name = data[offset:offset + name_size - 1].decode(errors="replace")
        if name == "TRAILER!!!":
            break
        offset = (offset + name_size + 3) & ~3
        if data[offset:offset + 4] == b"\x7fELF":
            yield f"{label}!/{name}", hashlib.sha256(memoryview(data)[offset:offset + size]).hexdigest()
        offset = (offset + size + 3) & ~3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "inputs", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    indexed = {item["rpm"]: item for item in json.loads((args.inputs / "sources.json").read_text())}
    by_hash = defaultdict(list)
    for receipt in indexed.values():
        for top in sorted((args.inputs / "sources" / receipt["package"]).iterdir()):
            if not top.is_file():
                continue
            for name, digest in source_members(top):
                by_hash[digest].append((receipt, name))
    with ((args.data / "image-instances-20261120.082536.csv").open(newline="") as images,
          gzip.open(args.data / "rpm-elf-evidence.csv.gz", "rt", newline="") as rpms,
          args.output.open("w", newline="") as output):
        columns = ("snapshot", "scope", "arch", "image", "nevra", "path", "sha256", "source_rpm",
                   "source_rpm_url", "source_rpm_sha256", "source_member")
        writer = csv.DictWriter(output, columns)
        writer.writeheader()
        records = []
        for scope, table in (("image", images), ("rpm-pass", rpms)):
            for row in csv.DictReader(table):
                if row["snapshot"] != SNAPSHOT or row.get("repository", "Unified") != "Unified":
                    continue
                for receipt, member in by_hash.get(row["sha256"], ()):
                    if scope == "rpm-pass" and row["source"] != receipt["rpm"]:
                        continue
                    record = dict(snapshot=SNAPSHOT, scope=scope, arch=row["arch"], image=row.get("image", ""),
                                  nevra=row.get("nevra", row.get("rpm_nevra")), path=row["path"], sha256=row["sha256"],
                                  source_rpm=receipt["rpm"], source_rpm_url=receipt["url"],
                                  source_rpm_sha256=receipt["sha256"], source_member=member)
                    records.append(record)
        writer.writerows(sorted(records, key=lambda row: tuple(row.values())))
        print(f"{len(records)} exact matches across {len(indexed)} published SRPMs")


if __name__ == "__main__":
    main()
