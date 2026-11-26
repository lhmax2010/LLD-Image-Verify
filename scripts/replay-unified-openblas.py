#!/usr/bin/env python3
"""Retry the logged OpenBLAS OpenMP shared link with the pinned libomp inputs."""
import argparse
from importlib import import_module
import json
from pathlib import Path
import shlex
import subprocess

prepare = import_module("prepare-unified-replay")
replay = import_module("replay-unified-rust")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=lambda path: Path(path).resolve(), required=True)
    parser.add_argument("--output", type=lambda path: Path(path).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    tools = args.work / "rust"
    selected = [r for r in prepare.rpm.index(prepare.BASE, "packages", tools / "repodata")
                if r["name"] in ("libomp", "libomp-devel") and r["arch"] in ("aarch64", "armv7l")]
    (args.output / "rpm-inputs.json").write_text(json.dumps(selected, indent=2) + "\n")
    for arch in ("aarch64", "armv7l"):
        root = tools / "root" / arch
        for r in selected:
            if r["arch"] == arch:
                archive = prepare.obtain(r["url"], tools / "packages" / r["rpm"], r["digest"], r["algo"])
                prepare.extract_package(archive, root)
        trial = args.work / "recipe-builds" / arch / "openblas" / "clang"
        lines = (trial / "build.log").read_text(errors="replace").splitlines()
        idx, = (i for i, line in enumerate(lines) if " -shared -o ../libopenblas_openmp_" in line)
        command = shlex.split(" ".join(line.rstrip("\\") for line in lines[idx:idx + 3]))
        box = replay.enclosure(root, trial, "/work/BUILD/openmp/exports")
        output = args.output / (arch + ".txt")
        result = replay.capture(output, [*box, *command], check=False)
        with output.open("a") as stream:
            stream.write(f"Original local log lines {idx + 1}–{idx + 3}\nExit {result.returncode}\n")
            if result.returncode == 0:
                path = trial / "BUILD" / "openmp" / Path(command[command.index("-o") + 1]).name
                stream.write(subprocess.check_output(["readelf", "-p", ".comment", "-d", path], text=True))
        print(f"{arch} OpenBLAS OpenMP link: {result.returncode}", flush=True)


if __name__ == "__main__":
    main()
