#!/usr/bin/env python3
"""Collect checksum-verified published inputs and a workspace-local Tizen replay root."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit

rpm = import_module("sweep-rpms")
UNIFIED = rpm.logs.UNIFIED + "20261120.082536"
BASE = rpm.logs.BASE + "20261119.042539"
ARCHES = ("aarch64", "armv7l", "x86_64")
SYSTEM = """filesystem bash dash coreutils toybox findutils grep grep-devel diffutils sed gawk make pkg-config
glibc glibc-devel linux-glibc-devel binutils binutils-libs gcc gcc-c++ cpp gcc-gfortran libgfortran libgcc
libstdc++ libstdc++-devel libatomic libgomp libquadmath libitm libssp libmpc libmpfr libgmp gmp
clang llvm libllvm clang-devel zlib zlib-devel libzstd1 libxml2 liblzma libopenssl3
libncurses libreadline libacl libattr libcap libxcrypt libpcre2 libpcre2-8-0 libbz2 libffi
cmake ninja meson python3 python3-base libpython3 zip tar gzip bzip2 xz m4 patch perl
autoconf automake libtool libltdl gettext-tools gettext-runtime openssl3 openssl3-devel compiler-rt
rust rust-devel rust-std-shared rust-std-static rustfmt cargo rust-packaging rust-macros rpm-rust-macros tidl rpm rpm-build""".split()
SOURCE = {"rust-regex": "rust-regex-1.7.1-1.src.rpm", "pkgmgr-server": "pkgmgr-server-1.1.4-1.src.rpm"}
BUILDS = ("rust", "rust-regex", "pkgmgr-server")


def obtain(url, path, checksum="", algorithm="sha256"):
    if path.is_file() and checksum:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, algorithm).hexdigest() == checksum:
                return path
    elif path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    for source in (url, urlunsplit(urlsplit(url)._replace(netloc="cdn.download.tizen.org"))):
        response = subprocess.run(["curl", "-fsSL", "--retry", "2", "--continue-at", "-",
                                   "--connect-timeout", "10", "--max-time", "1200", source, "-o", partial])
        if response.returncode:
            continue
        if checksum:
            with partial.open("rb") as stream:
                if hashlib.file_digest(stream, algorithm).hexdigest() != checksum:
                    partial.unlink()
                    continue
        partial.replace(path)
        break
    else:
        raise ValueError(f"No downloaded copy verified for {url}")
    return path


def extract_package(archive, root):
    with subprocess.Popen(["rpm2cpio", archive], stdout=subprocess.PIPE) as payload:
        subprocess.run(["bwrap", "--unshare-user", "--uid", "0", "--gid", "0",
                        "--cap-add", "CAP_DAC_OVERRIDE", "--ro-bind", "/", "/", "--bind", str(root), "/mnt", "--chdir", "/mnt",
                        "/usr/bin/cpio", "-idmu", "--quiet", "--no-absolute-filenames", "--no-preserve-owner"],
                       stdin=payload.stdout, check=True)
        if payload.wait():
            raise ValueError(f"RPM extraction failed {archive}")


def build_dependencies(text):
    return {match[1]: match[2] for match in re.finditer(
        r"\b(?:keeping|cumulate|installing) ([\w+.-]+)-([^\s-]+-[^\s-]+)\s*$", text, re.M)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--architecture", choices=ARCHES, action="append")
    parser.add_argument("--workers", type=int, default=18)
    args = parser.parse_args()
    work = args.work.resolve()
    cache = work / "repodata"
    cache.mkdir(parents=True, exist_ok=True)
    arches = args.architecture or ARCHES
    available = {}
    for repo in (BASE, UNIFIED):
        for entry in rpm.index(repo, "packages", cache):
            available[entry["arch"], entry["name"]] = entry
    # Pull the Rust dylib dependency closure used by the two published build commands.
    with ThreadPoolExecutor(args.workers) as pool:
        inputs = defaultdict(list)
        tasks = []
        for arch in arches:
            for name in BUILDS:
                url = f"{UNIFIED}/builddata/buildlogs/standard/{arch}/succeeded/{name}.buildlog.txt"
                tasks.append(pool.submit(obtain, url, work / "logs" / arch / f"{name}.txt"))
        for filename in SOURCE.values():
            tasks.append(pool.submit(obtain, f"{UNIFIED}/repos/standard/source/{filename}", work / "source" / filename))
        for task in tasks:
            task.result()
        downloads = {}
        for arch in arches:
            names = set(SYSTEM) | {"rust-regex", "pkgmgr-server"}
            build = (work / "logs" / arch / "pkgmgr-server.txt").read_text(errors="replace")
            build += (work / "logs" / arch / "rust-regex.txt").read_text(errors="replace")
            names.update(build_dependencies(build))
            for name in sorted(names):
                entry = available.get((arch, name)) or available.get(("noarch", name))
                if not entry:
                    continue
                archive = work / "packages" / entry["rpm"]
                if archive not in downloads:
                    downloads[archive] = pool.submit(obtain, entry["url"], archive, entry["digest"], entry["algo"])
                inputs[arch].append((entry, downloads[archive]))
        for arch, packages in inputs.items():
            root = work / "root" / arch
            root.mkdir(parents=True, exist_ok=True)
            for entry, task in sorted(packages, key=lambda item: (item[0]["name"] != "filesystem", item[0]["name"])):
                archive = task.result()
                extract_package(archive, root)
            (work / f"inputs-{arch}.json").write_text(json.dumps([entry for entry, _ in packages], indent=2) + "\n")
            print(f"{arch}: extracted {len(packages)} verified packages", flush=True)


if __name__ == "__main__":
    main()
