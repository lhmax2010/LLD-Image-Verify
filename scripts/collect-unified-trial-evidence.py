#!/usr/bin/env python3
"""Archive reproducible trial commands, selected numbered diagnostics, and output markers."""
import argparse
import csv
import hashlib
from importlib import import_module
from pathlib import Path
import re
import shutil
import subprocess

RELEVANT = re.compile(
    r"exited|\bfatal error:|\berror:|^ERROR |^CMake Error|FAILED:|illegal instruction|"
    r"linker for the host machine|compiler identification|\bgfortran\b.*(?: -shared | -o (?:[^ ]*\.so|conftest))|"
    r"(?:(?:libyaca|libnntrainer|libonnxruntime|libopenblas|liblapack|libblas|libhdf5|libGLES|libEGL|libonert|augeas|mtp-initiator)[^ ]*)"
    r".*(?:-fuse-ld|\s-shared)|Linking (?:C|CXX|Fortran) (?:shared|executable)",
    re.I,
)
TARGET_FILE = re.compile(
    r"^(?:lib(?:yaca|nntrainer|onnxruntime|openblas|lapack|blas|hdf5|GLES|EGL|onert|augeas|fa)|"
    r"augeas|augtool|augparse|fadot|mtp-initiator|security-config|dtc$|fw_printenv$)"
)
ANGLE_TARGETS = ("libGLESv2_angle.so", "libGLESv1_CM_angle.so", "libEGL_angle.so", "libfeature_support_angle.so")
replay = import_module("replay-unified-rust")


def summarize(work, output):
    evidence = output / "trials"
    evidence.mkdir(parents=True, exist_ok=True)
    trials, files = [], []
    for batch in sorted(work.glob("*builds*")):
        if not batch.is_dir():
            continue
        status_file = batch / "builds.csv"
        states = {}
        if status_file.exists():
            with status_file.open(newline="") as stream:
                states = {(r["arch"], r["package"], r["variant"]): r["exit"] for r in csv.DictReader(stream)}
        elif (batch_log := work / f"{batch.name}.log").exists():
            for line in batch_log.read_text().splitlines():
                if match := re.fullmatch(r"([^/]+)/([^/]+)/([^:]+): exit (\d+)", line):
                    states[match[1], match[2], match[3]] = match[4]
        for log in sorted(batch.glob("*/*/*/build.log")):
            arch, package, variant, _ = log.relative_to(batch).parts
            name = f"{batch.name}-{arch}-{package}-{variant}"
            target = evidence / (name + ".txt")
            with log.open(errors="replace") as stream:
                first = next(stream, "").rstrip()
                picks = []
                for i, line in enumerate(stream, 2):
                    if len(picks) == 50:
                        break
                    if RELEVANT.search(line) and not line.startswith(("x -", "  inflating:")):
                        picks.append(f"{i}\t{line.rstrip()}\n")
            digest = hashlib.sha256()
            with log.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            status = states.get((arch, package, variant), "")
            target.write_text(f"Command\n{first}\nFull local trial log SHA256 {digest}\nExit {status or 'pending'}\n\n" +
                              "".join(picks))
            variant_dir = log.parent
            specs = sorted((variant_dir / "SPECS").glob("*.spec"))
            if specs:
                with specs[0].open("rb") as stream:
                    spec_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            else:
                spec_hash = ""
            trials.append(dict(arch=arch, package=package, variant=variant, batch=batch.name,
                               exit=status, local_full_log=str(log.relative_to(work)),
                               evidence=str(target.relative_to(output)), spec_sha256=spec_hash))
            if package == "angle":
                builddir = variant_dir / "BUILD" / "angle-2.1" / "out" / "Debug"
                commands = []
                if (builddir / "build.ninja").exists():
                    if ninja := shutil.which("ninja"):
                        prefix = [ninja, "-C", str(builddir)]
                    else:
                        root = work.resolve() / "rust" / "root" / "x86_64"
                        prefix = replay.enclosure(root, builddir.resolve(), "/work") + ["/usr/bin/ninja"]
                    for target_name in ANGLE_TARGETS:
                        command = [*prefix, "-t", "commands", target_name]
                        probe = subprocess.run(command, capture_output=True, text=True)
                        if probe.returncode == 0 and probe.stdout.strip():
                            commands.append(f"{target_name}\t{probe.stdout.splitlines()[-1]}\n")
                if commands:
                    (evidence / (name + "-generated-links.tsv")).write_text("".join(commands))
            for member in sorted((variant_dir / "BUILD").rglob("*")):
                if (member.is_symlink() or not member.is_file() or not TARGET_FILE.match(member.name)
                        or any(member.name.endswith(ext) for ext in (".o", ".a", ".c", ".cc", ".cpp"))):
                    continue
                with member.open("rb") as stream:
                    if stream.read(4) != b"\x7fELF":
                        continue
                    stream.seek(0)
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                elf = subprocess.run(["readelf", "-p", ".comment", member], capture_output=True, text=True)
                marker = next((line.strip() for line in elf.stdout.splitlines() if "Linker:" in line), "")
                files.append(dict(arch=arch, package=package, variant=variant, batch=batch.name,
                                  path=str(member.relative_to(variant_dir / "BUILD")), sha256=digest, marker=marker))
    for entries, filename, columns in (
        (trials, "trial-builds.csv", ("arch", "package", "variant", "batch", "exit", "local_full_log", "evidence", "spec_sha256")),
        (files, "trial-elf-markers.csv", ("arch", "package", "variant", "batch", "path", "sha256", "marker")),
    ):
        with (output / filename).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, columns)
            writer.writeheader()
            writer.writerows(entries)
    print(f"{len(trials)} trial logs and {len(files)} native trial outputs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summarize(args.work, args.output)


if __name__ == "__main__":
    main()
