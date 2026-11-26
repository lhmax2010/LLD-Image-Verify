#!/usr/bin/env python3
"""Archive reproducible trial commands, selected numbered diagnostics, and output markers."""
import argparse
import csv
import hashlib
from pathlib import Path
import re
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
ANGLE_TARGETS = ("libGLESv2", "libGLESv1_CM", "libEGL", "libfeature_support")
OUTPUT_PATHS = {
    "angle": ("angle-*/out/Debug/*.so",),
    "augeas": ("augeas-*/src/.libs/*",),
    "hdf5": ("hdf5-*/build/*/.libs/*", "hdf5-*/build/*/*/.libs/*"),
    "lapack": ("lapack-*/build/lib/*",),
    "mtp-initiator": ("mtp-initiator-*/haltest/mtp-initiator-haltests", "mtp-initiator-*/src/daemon/mtp-initiator"),
    "nnfw": ("nnfw-*/build/lib/*", "nnfw-*/build/bin/*"),
    "nntrainer": ("nntrainer-*/build/nntrainer/*.so*",),
    "onnxruntime": ("onnxruntime-*/build/libonnxruntime.so*",),
    "openblas": ("*/libopenblas*.so*",),
    "security-config": ("security-config-*/security-config",),
    "u-boot": ("u-boot-*/scripts/dtc/dtc", "u-boot-*/tools/env/fw_printenv"),
    "u-boot-rpi4": ("u-boot-*/scripts/dtc/dtc", "u-boot-*/tools/env/fw_printenv"),
    "yaca": ("yaca-*/src/libyaca.so*",),
}


def angle_link_settings(directory):
    toolchain = directory / "toolchain.ninja"
    if not toolchain.exists():
        return []
    lines = toolchain.read_text().splitlines()
    settings = [f"toolchain.ninja:{i + 2}\t{lines[i + 1].strip()}\n"
                for i, line in enumerate(lines) if line == "rule solink"]
    for name in ANGLE_TARGETS:
        fragment = directory / "obj" / f"{name}.ninja"
        if fragment.exists():
            settings.extend(f"obj/{name}.ninja:{number}\t{line.strip()}\n"
                            for number, line in enumerate(fragment.read_text().splitlines(), 1)
                            if line.startswith(("  ldflags =", "  target_output_name =", "  output_extension =")))
    return settings


def summarize(work, output, interrupted):
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
            state = {"0": "completed", "124": "timed-out"}.get(status, "failed" if status else ("interrupted" if interrupted else "pending"))
            target.write_text(f"Command\n{first}\nFull local trial log SHA256 {digest}\nState {state}, exit {status or 'unavailable'}\n\n" +
                              "".join(picks))
            variant_dir = log.parent
            specs = sorted((variant_dir / "SPECS").glob("*.spec"))
            if specs:
                with specs[0].open("rb") as stream:
                    spec_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            else:
                spec_hash = ""
            trials.append(dict(arch=arch, package=package, variant=variant, batch=batch.name,
                               exit=status, state=state, local_full_log=str(log.relative_to(work)),
                               evidence=str(target.relative_to(output)), spec_sha256=spec_hash))
            if package == "angle":
                builddir = variant_dir / "BUILD" / "angle-2.1" / "out" / "Debug"
                commands = angle_link_settings(builddir)
                if commands:
                    (evidence / (name + "-generated-link-settings.tsv")).write_text("".join(commands))
            build = variant_dir / "BUILD"
            for member in sorted({file for pattern in OUTPUT_PATHS.get(package, ()) for file in build.glob(pattern)}):
                if (not TARGET_FILE.match(member.name)
                        or any(member.name.endswith(ext) for ext in (".o", ".a", ".c", ".cc", ".cpp"))
                        or member.is_symlink() or not member.is_file()):
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
        (trials, "trial-builds.csv", ("arch", "package", "variant", "batch", "state", "exit", "local_full_log", "evidence", "spec_sha256")),
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
    parser.add_argument("--interrupted", action="store_true", help="Label logs missing an exit status as interrupted.")
    args = parser.parse_args()
    summarize(args.work, args.output, args.interrupted)


if __name__ == "__main__":
    main()
