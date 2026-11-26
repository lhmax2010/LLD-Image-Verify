#!/usr/bin/env python3
"""Replay the published rustc commands with their default and the Tizen Clang driver."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
from importlib import import_module
import json
from pathlib import Path
import re
import shlex
import subprocess

prepare = import_module("prepare-unified-replay")
ARCHES = {
    "aarch64": ("aarch64-tizen-linux-gnu", "lib64"),
    "armv7l": ("armv7l-tizen-linux-gnueabi", "lib"),
    "x86_64": ("x86_64-tizen-linux-gnu", "lib64"),
}


def qemu_mounts(root):
    mounts = {
        "aarch64": (("qemu-arm64-binfmt", "qemu-aarch64-binfmt"), ("qemu-arm64-static", "qemu-aarch64")),
        "armv7l": (("qemu-arm-binfmt", "qemu-arm-binfmt"), ("qemu-arm-static", "qemu-arm")),
    }
    return mounts.get(root.name, ())


def enclosure(root, work, cwd, accelerate_clang=False):
    # Prefer the QEMU executables shipped with the pinned build root when present.
    emulation = [value for host, guest in qemu_mounts(root)
                 if not (root / "usr/bin" / guest).stat().st_size
                 for value in ("--ro-bind", f"/usr/bin/{host}", f"/usr/bin/{guest}")]
    # Run the target-native tools through QEMU. The optional x86 accelerator's
    # /emul ld cannot load the target architecture's GCC LTO plugin.
    accelerator = ["--tmpfs", "/emul"] if (root / "emul").is_dir() else []
    if accelerator and accelerate_clang:
        mirror = root / "emul"
        # Expose only the verified Clang/LLVM accelerator. GCC stays native to
        # the guest so its GNU linker can load the matching GCC LTO plugin.
        paths = [*mirror.glob("usr/bin/*clang*"), *mirror.glob("usr/bin/llvm-*"),
                 *(mirror / name for name in ("usr/bin/lld", "usr/bin/ld.lld", "lib64", "usr/lib64", "usr/lib"))]
        for path in paths:
            if path.exists():
                accelerator.extend(("--ro-bind", str(path), f"/emul/{path.relative_to(mirror)}"))
    return ["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--unshare-pid",
            "--ro-bind", str(root), "/", "--dev", "/dev", "--proc", "/proc", *emulation,
            *accelerator,
            "--bind", str(work), "/work", "--chdir", cwd, "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/work",
            "--setenv", "TMPDIR", "/work/tmp", "--setenv", "LC_ALL", "C"]


def capture(path, command, check=True):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    path.write_text(shlex.join(map(str, command)) + "\n" + process.stdout)
    if check and process.returncode:
        raise RuntimeError(f"exit {process.returncode}: {path}")
    return process


def original_invocation(log, crate):
    lines = log.read_text(errors="replace").split("\n")
    command = [(i, shlex.split(re.sub(r"^\[\s*\d+s\]\s*\+ ", "", line)))
               for i, line in enumerate(lines, 1) if "+ /usr/bin/rustc " in line
               and f"--crate-name={crate} " in line and " --test " not in line]
    if len(command) != 1:
        raise ValueError(f"{log}: expected one command for {crate}")
    return command[0]


def sources(work, directory, package):
    source = work / "source" / prepare.SOURCE[package]
    unpacked = directory / f"{package}-srpm"
    unpacked.mkdir(exist_ok=True)
    with subprocess.Popen(["rpm2cpio", source], stdout=subprocess.PIPE) as payload:
        subprocess.run(["cpio", "-idmu", "--quiet", "--no-absolute-filenames"],
                       stdin=payload.stdout, cwd=unpacked, check=True)
        if payload.wait():
            raise ValueError(f"Cannot extract {source}")
    tarball, = unpacked.glob("*.tar.gz")
    subprocess.run(["tar", "-xzf", tarball, "-C", directory], check=True)
    if package == "rust-regex":
        tree = directory / "rust-regex-1.7.1"
        (tree / "rust-regex.manifest").write_bytes((unpacked / "rust-regex.manifest").read_bytes())
        check = subprocess.run(["patch", "-p1", "--dry-run", "--forward", "-i", unpacked / "extern.patch"],
                               cwd=tree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if check.returncode == 0:
            subprocess.run(["patch", "-p1", "--forward", "-s", "-i", unpacked / "extern.patch"], cwd=tree, check=True)
        else:
            subprocess.run(["patch", "-p1", "--dry-run", "--reverse", "-s", "-i", unpacked / "extern.patch"], cwd=tree, check=True)
        return tree
    return directory / "pkgmgr-server-1.1.4"


def exported_symbols(path):
    output = subprocess.check_output(["readelf", "--dyn-syms", "--wide", path], text=True)
    names = Counter()
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=7)
        if len(fields) == 8 and fields[0].endswith(":") and fields[6] not in ("UND", "UNDEF"):
            if fields[4] in ("GLOBAL", "WEAK", "UNIQUE") and fields[5] in ("DEFAULT", "PROTECTED"):
                names[fields[3], fields[4], fields[5], fields[7]] += 1
    return names


def ensure_cc(root):
    # The GCC RPM installs gcc. Its post-install alternatives normally supply cc.
    if (root / "usr/bin/cc").exists():
        return
    subprocess.run(["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--cap-add", "CAP_DAC_OVERRIDE",
                    "--ro-bind", "/", "/", "--bind", str(root), "/mnt",
                    "/usr/bin/ln", "-s", "gcc", "/mnt/usr/bin/cc"], check=True)


def run_arch(arch, work, destination, packages):
    target, lib = ARCHES[arch]
    root = work / "root" / arch
    scratch = work / "runs" / arch
    evidence = destination / arch
    for path in (scratch / "tmp", evidence):
        path.mkdir(parents=True, exist_ok=True)
    for mount in ("dev", "proc", "work"):
        (root / mount).mkdir(exist_ok=True)
    for _, guest in qemu_mounts(root):
        if not (root / "usr/bin" / guest).exists():
            subprocess.run(["bwrap", "--unshare-user", "--uid", "0", "--gid", "0", "--cap-add", "CAP_DAC_OVERRIDE",
                            "--ro-bind", "/", "/", "--bind", str(root), "/mnt",
                            "/usr/bin/touch", f"/mnt/usr/bin/{guest}"], check=True)
    setup = enclosure(root, scratch, "/work")
    ensure_cc(root)
    capture(evidence / "rustc-version.txt", setup + ["/usr/bin/rustc", "-Vv"])
    capture(evidence / "rust-target-spec.txt",
            setup + ["--setenv", "RUSTC_BOOTSTRAP", "1", "/usr/bin/rustc", "-Z", "unstable-options",
                     "--print", "target-spec-json"])
    capture(evidence / "linker-versions.txt", setup +
            ["/bin/bash", "-c", "readlink -f /usr/bin/cc; cc -print-prog-name=ld; ld --version | head -1; "
             "ld.lld --version; find /usr -path '*/bin/rust-lld' -exec {} -flavor gnu --version \\;"])
    macros = sorted([*root.glob("usr/lib*/rpm/**/macros*rust*"), *root.glob("etc/rpm/macros*rust*")])
    for i, path in enumerate(macros, 1):
        (evidence / f"rust-macros-{i}.txt").write_text(
            str(path.relative_to(root)) + "\n" + path.read_text(errors="replace"))
    results = []
    for package, crate in (("rust-regex", "regex"), ("pkgmgr-server", "rust_pkgmgr_server")):
        if package not in packages:
            continue
        tree = sources(work, scratch, package)
        line, command = original_invocation(work / "logs" / arch / f"{package}.txt", crate)
        box = enclosure(root, scratch, "/work/" + tree.name)
        if package == "pkgmgr-server":
            # The spec exports these paths before loading the proc-macro DSOs.
            box += ["--setenv", "LD_LIBRARY_PATH", f":/usr/{lib}/rustlib:/usr/{lib}/rustlib/dylib"]
            # Use exactly the companion C DSOs from the published runtime RPM.
            for name in ("tidl_pkgmgr_server", "util_pkgmgr_server"):
                filename = f"lib{name}.so"
                candidate = root / "usr" / lib / filename
                if not candidate.exists():
                    raise FileNotFoundError(candidate)
                local = tree / name / filename
                if not local.is_symlink():
                    local.symlink_to(f"/usr/{lib}/{filename}")
        flags = ["-C", f"linker=/usr/bin/{target}-clang", "-C", "link-arg=--ld-path=/usr/bin/ld.lld"]
        if arch == "x86_64":
            flags += ["-C", "link-self-contained=-linker"]
        variants = (("control", []), ("tizen-lld", flags))
        artifacts = {}
        for name, options in variants:
            out = f"{package}-{name}.elf"
            trace = scratch / f"{package}-{name}.strace"
            proc = capture(evidence / f"{package}-{name}.log",
                           ["strace", "-f", "-e", "trace=execve,execveat", "-s", "300", "-o", str(trace),
                            *box, *command, *options, "--print", "link-args", "-o", f"/work/{out}"],
                           check=False)
            if proc.returncode:
                raise RuntimeError(f"{arch} {package} {name} exited {proc.returncode}. See {evidence}")
            prefix = re.compile(r'execve(?:at)?\([^\n]*(?:/cc"|/gcc"|/[^/" ]+-clang"|/clang[^/" ]*"|/collect2"|/ld(?:\.lld|\.bfd)?"|/rust-lld")')
            (evidence / f"{package}-{name}-exec.txt").write_text(
                "".join(line for line in trace.read_text(errors="replace").splitlines(keepends=True) if prefix.search(line)))
            artifact = scratch / out
            artifacts[name] = artifact
            capture(evidence / f"{package}-{name}-elf.txt", ["readelf", "-W", "-p", ".comment", "-d", artifact])
        original = root / ("usr/bin/pkgmgr-server" if package == "pkgmgr-server" else f"usr/{lib}/rustlib/dylib/libregex.so")
        symbols = {n: exported_symbols(p) for n, p in artifacts.items()}
        symbols["published"] = exported_symbols(original)
        facts = {
            "arch": arch, "package": package, "published_command_line": line,
            "published_log_url": f"{prepare.UNIFIED}/builddata/buildlogs/standard/{arch}/succeeded/{package}.buildlog.txt",
            "tizen_lld_marker": "Linker: LLD 22.1.8" in (evidence / f"{package}-tizen-lld-elf.txt").read_text(),
            "exports_equal_control": symbols["control"] == symbols["tizen-lld"],
            "exports_equal_published": symbols["published"] == symbols["tizen-lld"],
            "exports": {n: sum(s.values()) for n, s in symbols.items()},
            "export_delta": {n: {"added": sorted((symbols["tizen-lld"] - symbols[n]).elements()),
                                  "removed": sorted((symbols[n] - symbols["tizen-lld"]).elements())}
                             for n in ("published", "control")},
            "sha256": {n: hashlib.sha256(f.read_bytes()).hexdigest() for n, f in (artifacts | {"published": original}).items()},
        }
        (evidence / f"{package}.json").write_text(json.dumps(facts, indent=2) + "\n")
        print(f"{arch} {package}: marker={facts['tizen_lld_marker']}, exports={facts['exports_equal_control']}/{facts['exports_equal_published']}", flush=True)
        results.append(facts)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arch", action="append", choices=tuple(ARCHES))
    parser.add_argument("--package", action="append", choices=tuple(prepare.SOURCE))
    args = parser.parse_args()
    ok = True
    arches = args.arch or ARCHES
    packages = args.package or prepare.SOURCE
    with ThreadPoolExecutor(len(arches)) as pool:
        jobs = {arch: pool.submit(run_arch, arch, args.work.resolve(), args.out.resolve(), packages) for arch in arches}
        for arch, job in jobs.items():
            try:
                job.result()
            except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
                ok = False
                print(f"{arch}: {exc}", flush=True)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
