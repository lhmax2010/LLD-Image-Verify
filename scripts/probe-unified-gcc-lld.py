#!/usr/bin/env python3
"""Exercise the GCC and gfortran linker drivers in the native Unified package root."""
import argparse
from importlib import import_module
from pathlib import Path
import re
import subprocess

replay = import_module("replay-unified-rust")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.work.resolve() / "root"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for arch in ("aarch64", "armv7l"):
        scratch = args.work.resolve() / "runs" / arch
        c = scratch / "gcc-smoke.c"
        c.write_text("int c_link_probe(void) { return 42; }\n")
        fortran = scratch / "gfortran-smoke.f90"
        fortran.write_text("integer function fortran_link_probe()\n  fortran_link_probe = 42\nend function\n")
        box = replay.enclosure(root / arch, scratch, "/work")
        gcc_lib = f"/usr/{replay.ARCHES[arch][1]}"
        for driver, source in (("gcc", c), ("gfortran", fortran)):
            for linker, flags in (("default", []), ("lld", ["-fuse-ld=lld", f"-L{gcc_lib}", "-L/lib"])):
                result = output / f"{arch}-{driver}-{linker}.txt"
                filename = f"{driver}-{linker}-probe.so"
                trace = scratch / f"{filename}.strace"
                status = replay.capture(result, ["strace", "-f", "-s", "300", "-e", "execve", "-o", str(trace),
                     *box, f"/usr/bin/{driver}", "-shared", "-fPIC", "-o", f"/work/{filename}", f"/work/{source.name}",
                     *flags], check=False)
                with result.open("a") as evidence:
                    evidence.write(f"Exit {status.returncode}\n")
                    for line in trace.read_text().splitlines():
                        if re.search(r'execve\(".*(?:ld(?:\.bfd|\.lld)?|lld)"', line) and line.endswith(" = 0"):
                            evidence.write(line + "\n")
                    if status.returncode == 0:
                        evidence.write(subprocess.check_output(["readelf", "-p", ".comment", scratch / filename], text=True))
                print(arch, driver, linker, status.returncode, flush=True)


if __name__ == "__main__":
    main()
