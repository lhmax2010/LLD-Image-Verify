#!/usr/bin/env python3
"""Compile published Unified specs with an isolated RPM payload root and trial options."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import json
from pathlib import Path
import re
import subprocess

prepare = import_module("prepare-unified-replay")
replay = import_module("replay-unified-rust")
PACKAGES = ("yaca", "nntrainer", "onnxruntime", "hdf5", "openblas", "lapack", "angle",
            "augeas", "nnfw", "mtp-initiator", "security-config", "u-boot", "u-boot-rpi4")


def profile_macros(path, arch):
    # Keep the policy common to these build recipes. Arch macros for the exact
    # target still come from the Tizen rpm package.
    result = []
    for block in re.findall(r"^Macros:\n(.*?)^:Macros\b", path.read_text(), re.M | re.S):
        if any(entry in block for entry in ("%tizen_version_major ", "%__cc_clang ", "%optflags ", "%_vendor ")):
            result.append(block)
    result.append(f"%_host {replay.ARCHES[arch][0]}\n")
    result.append("%_smp_mflags -j3\n")
    return "".join(result)


def patched(contents, package, variant, arch):
    if variant == "published-verbose":
        return re.sub(r"(?m)^make (.*)", r"make V=1 \1", contents)
    if variant.startswith("clang"):
        contents = re.sub(r"^%define\s+_toolchain_override\s+gcc\s*$", "%define _toolchain_override clang", contents, flags=re.M)
        if package == "angle":
            options = 'is_clang=true use_lld=true clang_base_path="/usr" clang_use_chrome_plugins=false'
            if variant == "clang-fixed":
                options += " angle_enable_abseil=false"
            contents = contents.replace("is_clang=false", options)
    if variant == "clang-fixed" and package == "nntrainer":
        return contents.replace("mkdir -p build", 'export CXXFLAGS+=" -Wno-error=unqualified-std-cast-call"\nmkdir -p build')
    if variant == "clang-fixed" and package == "yaca":
        return contents.replace("%cmake .", 'export CFLAGS+=" -Wno-error=c2y-extensions"\n'
                                'export CXXFLAGS+=" -Wno-error=c2y-extensions"\n%cmake .')
    if variant == "clang-fixed" and package == "angle" and arch == "aarch64":
        return contents.replace("./gn gen", "sed -i 's/--target=aarch64-linux-gnu/--target=aarch64-tizen-linux-gnu/g' build/config/compiler/BUILD.gn\n./gn gen")
    if variant != "gcc-lld":
        return contents
    flags = "-fuse-ld=lld" + (" -L/usr/lib -L/lib" if arch == "armv7l" else "")
    lines = f'export LDFLAGS="${{LDFLAGS:-}} {flags}"\n'
    if package in ("openblas", "lapack", "hdf5"):
        lines += f'export FCFLAGS="${{FCFLAGS:-}} {flags}"\nexport FFLAGS="${{FFLAGS:-}} {flags}"\n'
    return re.sub(r"(?m)^%build\s*\n", lambda match: "%build\n" + lines, contents, count=1)


def build(arch, package, variant, args):
    src = args.inputs / "sources" / package
    candidates = sorted(src.glob("*.spec"))
    work = args.output / arch / package / variant
    work.mkdir(parents=True, exist_ok=True)
    record = dict(arch=arch, package=package, variant=variant, output=str(work.relative_to(args.output)))
    if not candidates:
        return record | {"state": "source-unavailable"}
    for dirname in ("BUILD", "SOURCES", "SPECS", "RPMS", "SRPMS", "tmp", "tools"):
        (work / dirname).mkdir(exist_ok=True)
    tar = work / "tools" / "tar"
    tar.write_text('#!/bin/sh\nexec /bin/tar --no-same-owner "$@"\n')
    tar.chmod(0o755)
    (work / "profile.macros").write_text(profile_macros(args.profile, arch))
    spec = work / "SPECS" / candidates[0].name
    spec.write_text(patched(candidates[0].read_text(), package, variant, arch))
    root = args.roots / arch
    for _, guest in replay.qemu_mounts(root):
        if not (root / "usr/bin" / guest).exists():
            raise FileNotFoundError(f"QEMU mount point needs setup at {root}/usr/bin/{guest}")
    box = replay.enclosure(root, work, "/work", accelerate_clang=args.accelerate_clang) + ["--ro-bind", str(src), "/work/SOURCES",
                                                   "--setenv", "PATH", "/work/tools:/usr/bin:/bin",
                                                   "--setenv", "LD_LIBRARY_PATH", "/usr/lib64:/usr/lib"]
    macro_path = (f"/usr/lib/rpm/macros:/usr/lib/rpm/platform/{arch}-linux/macros:"
                  "/usr/lib/rpm/macros.*:/etc/rpm/macros.*:/work/profile.macros")
    command = box + ["/usr/bin/rpmbuild", "-bc", "--nodeps", "--noclean", "--target", f"{arch}-tizen-linux",
                     "--macros", macro_path, "--define", "_topdir /work",
                     "--define", "_tmppath /work/tmp", "--define", "__tar /work/tools/tar",
                     f"/work/SPECS/{spec.name}"]
    log = work / "build.log"
    with log.open("w") as stream:
        print(subprocess.list2cmdline(command), file=stream, flush=True)
        try:
            status = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=args.timeout).returncode
        except subprocess.TimeoutExpired:
            status = 124
    print(f"{arch}/{package}/{variant}: exit {status}", flush=True)
    return record | {"exit": status, "state": "built" if status == 0 else "failed",
                     "log": str(log.relative_to(args.output))}


def populate(args, arches, packages):
    # Add exact packages from the published logs to the pre-existing replay root.
    for arch in arches:
        root = args.roots / arch
        if not root.exists():
            raise FileNotFoundError(root)
        meta = args.cache.parent / f"inputs-{arch}.json"
        done = {item["rpm"] for item in json.loads(meta.read_text())}
        for package in packages:
            index = args.inputs / "logs" / arch / f"{package}.inputs.json"
            if not index.exists():
                continue
            for item in json.loads(index.read_text())["pinned"]:
                if item["rpm"] not in done:
                    archive = args.cache / item["rpm"]
                    prepare.obtain(item["url"], archive, item["digest"], item["algo"])
                    prepare.extract_package(archive, root)
                    done.add(item["rpm"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "roots", "cache", "output", "profile"):
        parser.add_argument(f"--{name}", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--arch", choices=prepare.ARCHES, action="append")
    parser.add_argument("--package", choices=PACKAGES, action="append")
    parser.add_argument("--variant", choices=("clang", "clang-fixed", "gcc-lld", "published-verbose"), action="append")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=480)
    parser.add_argument("--use-prepared-root", action="store_true")
    parser.add_argument("--accelerate-clang", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    arches = args.arch or ("aarch64", "armv7l")
    packages = args.package or PACKAGES
    if not args.use_prepared_root:
        populate(args, arches, packages)
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = [pool.submit(build, arch, package, variant, args)
                for package in packages for arch in arches for variant in args.variant or ("clang",)]
        results = [job.result() for job in jobs]
    columns = ("arch", "package", "variant", "state", "exit", "log", "output")
    with (args.output / "builds.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
