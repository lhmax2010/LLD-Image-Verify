#!/usr/bin/env python3
"""Record published Base compiler and linker RPM identities for the compared snapshots."""
import argparse
from importlib import import_module
from pathlib import Path

rpm = import_module("sweep-rpms")
csvio = import_module("export-image-evidence")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cache", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
args.cache.mkdir(parents=True, exist_ok=True)
roots = [rpm.logs.BASE + stamp for stamp in ("20261030.061318", "20261117.165617", "20261119.042539")]
roots.extend(rpm.logs.BASE.replace("snapshots/", "RBS/") + stamp for stamp in ("20261120.145751", "20261125.143635"))
identities = []
for root in roots:
    for package in rpm.index(root, "packages", args.cache):
        if package["name"] in {"clang", "llvm", "libllvm", "binutils", "binutils-libs"} or package["name"].startswith("clang-accel-x86_64-"):
            identities.append({k: package[k] for k in ("snapshot", "arch", "name", "nevra", "vcs", "url", "digest", "bytes")})
csvio.write_csv(args.out, identities)
