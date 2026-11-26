#!/usr/bin/env python3
"""Record toolchain selections from the source RPM packaging recipes."""
import argparse
import hashlib
from importlib import import_module
from pathlib import Path
import re
import subprocess
import tempfile

prebuilt = import_module("check-prebuilt-members")
csvio = import_module("export-image-evidence")
SELECT = re.compile(r"_toolchain.*gcc|\b(gfortran|CMAKE_(?:C|CXX)_COMPILER|CC=|CXX=|FC=)|^(Build)?Requires:.*\bgcc\b", re.I)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--srpm", type=Path, required=True, nargs="+")
parser.add_argument("--snapshot", required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--work", type=Path, required=True)
args = parser.parse_args()
args.work.mkdir(parents=True, exist_ok=True)
evidence = []
for rpm in args.srpm:
    subprocess.run(["rpm", "-K", rpm], check=True, capture_output=True)
    specs = [name for name in prebuilt.rpm_members(rpm) if name.endswith(".spec")]
    vcs = subprocess.check_output(["rpm", "-qp", "--qf", "%{VCS}", rpm], text=True)
    with rpm.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(dir=args.work) as folder:
        extracted = Path(folder) / "recipe"
        for spec in specs:
            prebuilt.extract_member(rpm, spec, extracted)
            for line, text in enumerate(extracted.read_text().splitlines(), 1):
                if SELECT.search(text):
                    evidence.append(dict(snapshot=args.snapshot,
                        source_rpm_url=f"{prebuilt.UNIFIED}{args.snapshot}/repos/standard/source/{rpm.name}",
                        source_rpm_sha256=sha256, source_vcs=vcs, spec=spec, line=line, text=text.rstrip()))
csvio.write_csv(args.out, evidence)
