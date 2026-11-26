#!/usr/bin/env python3
"""Match image ELF bytes against published Tizen SRPM tar/TPK members."""
import argparse
from collections import defaultdict
import csv
import hashlib
import gzip
import re
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

SRPMS = {
    "stt-engine-default": "org.tizen.stt-engine-default-1.100.3-1.src.rpm",
    "vc-engine-default": "org.tizen.vc-engine-default-1.90.1-1.src.rpm",
    "homescreen-app": "org.tizen.homescreen-1.0.0-1.src.rpm",
    "linux-rpi": "rpi4-linux-kernel-6.12.80-0.src.rpm",
    "tts-engine-default": "org.tizen.tts-engine-default-1.100.1-1.src.rpm",
    "sppc": "push-0.7.6-1.src.rpm",
    "hand-drawing-engine": "pen-wave-1.4.0-2.src.rpm",
    "wakeup-engine-default": "wakeup-engine-default-0.2.5-1.src.rpm",
    "voice-control": "voice-control-1.101.6-1.src.rpm",
    "stt": "stt-1.110.1-1.src.rpm",
    "tts": "tts-1.100.10-1.src.rpm",
}
UNIFIED = "https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_"


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def rpm_members(rpm):
    return subprocess.check_output(["rpm", "-qpl", str(rpm)], text=True).splitlines()


def nested_matches(path, name, wanted):
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                if Path(member.name).name in wanted:
                    with archive.extractfile(member) as stream:
                        yield f"{name}!/{member.name}", digest(stream)
                if member.name.lower().endswith(".tpk"):
                    with archive.extractfile(member) as stream:
                        yield from zip_matches(stream, f"{name}!/{member.name}", wanted)
    elif name.lower().endswith(".tpk"):
        with path.open("rb") as stream:
            yield from zip_matches(stream, name, wanted)


def added_patch_matches(path, name, wanted):
    """Read literal added source files from the GBS patch that RPM applies in %prep."""
    header = re.compile(rb"^diff --git a/(rpi/boot/[^ ]+) b/\1\n$")
    start = re.compile(rb"^@@ -0,0 \+1,(\d+) @@")
    git_index = re.compile(rb"^index 0+\.\.([0-9a-f]+)")
    with gzip.open(path, "rb") as stream:
        source = enumerate(stream, 1)
        for number, line in source:
            target = header.match(line)
            if not target or Path(target[1].decode()).name not in wanted:
                continue
            body = bytearray()
            expected_blob = None
            for _, patch_line in source:
                index = git_index.match(patch_line)
                if index:
                    expected_blob = index[1].decode()
                hunk = start.match(patch_line)
                if hunk:
                    for _ in range(int(hunk[1])):
                        addition = next(source)[1]
                        if not addition.startswith(b"+"):
                            raise ValueError(f"{name}:{number}: invalid addition")
                        body.extend(addition[1:])
                    break
                if patch_line.startswith(b"diff --git"):
                    raise ValueError(f"{name}:{number}: missing new file hunk")
            blob = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
            if not expected_blob or not blob.startswith(expected_blob):
                # A final no-newline marker is outside the hunk's line count.
                if body.endswith(b"\n"):
                    body.pop()
                    blob = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
                if not expected_blob or not blob.startswith(expected_blob):
                    raise ValueError(f"{name}:{number}: added file differs from Git blob")
            yield f"{name}:{number}!/{target[1].decode()}", hashlib.sha256(body).hexdigest()


def zip_matches(stream, path, wanted):
    with zipfile.ZipFile(stream) as archive:
        for name in archive.namelist():
            if Path(name).name in wanted:
                with archive.open(name) as member:
                    yield f"{path}!/{name}", digest(member)


def extract_member(rpm, name, destination):
    with (destination.open("wb") as output,
          subprocess.Popen(["rpm2cpio", str(rpm)], stdout=subprocess.PIPE) as payload):
        subprocess.run(["cpio", "-i", "--quiet", "--to-stdout", name], stdin=payload.stdout,
                       stdout=output, check=True)
        if payload.wait():
            raise ValueError(f"rpm2cpio failed for {rpm}")


def matches(root, project, rows, work):
    url = root + "/repos/standard/source/" + SRPMS[project]
    with tempfile.TemporaryDirectory(dir=work) as td:
        td = Path(td)
        rpm = td / SRPMS[project]
        subprocess.run(["curl", "-fsSL", "--retry", "2", url, "-o", str(rpm)], check=True)
        with rpm.open("rb") as stream:
            checksum = digest(stream)
        vcs = subprocess.check_output(["rpm", "-qp", "--qf", "%{VCS}", str(rpm)], text=True)
        wanted = {Path(row["path"]).name for row in rows}
        candidates = defaultdict(list)
        for name in rpm_members(rpm):
            if Path(name).name not in wanted and not name.endswith((".gz", ".bz2", ".xz", ".zst", ".tpk")):
                continue
            file = td / "member"
            extract_member(rpm, name, file)
            if Path(name).name in wanted:
                with file.open("rb") as stream:
                    candidates[digest(stream)].append(name)
            if project == "linux-rpi" and name.endswith(".diff.gz"):
                entries = added_patch_matches(file, name, wanted)
            else:
                entries = nested_matches(file, name, wanted)
            for member, member_hash in entries:
                candidates[member_hash].append(member)
        for row in rows:
            members = candidates[row["sha256"]]
            if vcs.split("#")[-1] != row["source_commit"]:
                raise ValueError(f"{project} SRPM VCS mismatch for {row['path']}")
            yield dict(source=row["source"], source_commit=row["source_commit"], path=row["path"],
                       machine=row["machine"], image_sha256=row["sha256"], source_rpm_url=url,
                       source_rpm_sha256=checksum, source_member_sha256=row["sha256"] if members else "",
                       source_members=json.dumps(members), byte_match=bool(members))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--image-table", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--project", action="append")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(dict)
    with args.image_table.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            project = row["source"].rsplit("/", 1)[-1]
            if project in SRPMS and (not args.project or project in args.project) and row["classification"] in {
                "other-linker-confirmed", "unresolved", "gnu-ld-like-layout"
            }:
                groups[project][row["path"], row["sha256"]] = row
    found = []
    for project, rows in groups.items():
        results = list(matches(UNIFIED + args.snapshot, project, rows.values(), args.work))
        print(f"{args.snapshot} {project}: {sum(r['byte_match'] for r in results)}/{len(results)}", flush=True)
        found.extend(results)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, list(found[0]))
        writer.writeheader()
        writer.writerows(found)


if __name__ == "__main__":
    main()
