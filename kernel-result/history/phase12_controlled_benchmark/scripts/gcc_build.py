#!/usr/bin/env python3
"""Build C/D against the exact non-RT GCC SDK in an isolated Tizen ARM root."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/gcc"
WORK = ROOT / "work/gcc"
OLD_ROOT = Path("/local-user/GBS-ROOT-TIZEN-UNIFIED-LLVM/local/BUILD-ROOTS/scratch.armv7l.0")
SDK = "boot/kernel/devel/kernel-devel-arm-rpi4"
PROVIDER = "usr/src/linux-tizen-modules-source"
ACCEL_RPM = "qemu-accel-x86_64-armv7l-0.4-1.1.armv7l.rpm"
ASSIGNMENT = b"LD = ${CROSS_COMPILE}ld\n"
PREFIX = "/usr/armv7l-tizen-linux-gnueabi/bin/"


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def extract(rpm, destination):
    destination.mkdir(parents=True, exist_ok=True)
    first = subprocess.Popen(["rpm2cpio", str(rpm)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = subprocess.run(["cpio", "--quiet", "-idumD", str(destination)], stdin=first.stdout,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    first.stdout.close()
    stderr = first.stderr.read()
    if first.wait() or second.returncode:
        raise RuntimeError((rpm, stderr.decode(errors="replace"), second.stderr.decode(errors="replace")))


def run(stem, argv, trace=False, extra=None):
    stem.parent.mkdir(parents=True, exist_ok=True)
    tracing = stem.with_suffix(".strace")
    command = ["strace", "-f", "-qq", "-s", "32768", "-e", "trace=process", "-o", str(tracing), *argv] if trace else argv
    with stem.with_suffix(".out").open("wb") as stdout, stem.with_suffix(".err").open("wb") as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr)
    dump(stem.with_suffix(".cmd.json"), dict(argv=command, exit_status=result.returncode, **(extra or {})))
    if trace and tracing.exists():
        with tracing.open("rb") as plain, gzip.open(stem.with_suffix(".strace.gz"), "wb", compresslevel=3) as compressed:
            shutil.copyfileobj(plain, compressed)
        tracing.unlink()
    return result.returncode


def manifest(root):
    return {str(path.relative_to(root)): ("symlink:" + os.readlink(path) if path.is_symlink() else digest(path))
            for path in sorted(root.rglob("*")) if path.is_file() or path.is_symlink()}


def prepare(base):
    stage = WORK / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    for relative in ("usr/bin", "usr/lib"):
        target = stage / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cp", "-a", "--reflink=auto", "--no-preserve=ownership", str(base / relative), str(target)],
                           check=True)
            for path in (target, *target.rglob("*")):
                if path.is_dir() and not path.is_symlink():
                    path.chmod(path.stat().st_mode | 0o700)
    repo = json.loads((EVIDENCE / "selected-build-packages.json").read_text())
    known_locations = {}
    for row in repo:
        filename = row["filename"]
        if row["name"] in ("linux-tizen-modules-source", "arm-rpi4-linux-kernel-btf-devel"):
            continue
        source = WORK / "rpm-extract" / filename
        if not source.exists():
            extract(EVIDENCE / filename, source)
        for relative in ("usr/bin", "usr/lib", "usr/armv7l-tizen-linux-gnueabi", "lib"):
            tree = source / relative
            if not tree.is_dir():
                continue
            target = stage / ("usr/lib" if relative == "lib" else relative)
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cp", "-a", "--remove-destination", "--no-preserve=ownership", str(tree) + "/.", str(target)], check=True)
            for member in tree.rglob("*"):
                if member.is_file() and not member.is_symlink():
                    dest = target / member.relative_to(tree)
                    known_locations["/" + str(dest.relative_to(stage))] = filename
        for path in (stage / "usr/bin", stage / "usr/lib"):
            path.chmod(path.stat().st_mode | 0o700)
    sdkroot = WORK / "sdk"
    if not (sdkroot / SDK / "Module.symvers").exists():
        extract(EVIDENCE / "arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm", sdkroot)
    published_root = WORK / "published-reference"
    if not published_root.exists():
        extract(EVIDENCE / "linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm", published_root)
    published_kdbus = next(path for path in published_root.rglob("kdbus.ko")
                           if "6.12.80-arm-rpi4-v7l" in path.parts)
    run(EVIDENCE / "published-gcc-kdbus-modinfo", ["readelf", "-p", ".modinfo", str(published_kdbus)])
    source = WORK / "provider"
    if not (source / PROVIDER / "Makefile").is_file():
        extract(EVIDENCE / "linux-tizen-modules-source-11.0.0-0.armv7l.rpm", source)
    existing = ROOT.parent / "kernel_lld_verification_20261125/evidence/source"
    old = (source / PROVIDER / "Makefile").read_bytes()
    fixed = old.replace(ASSIGNMENT, b"")
    if old.count(ASSIGNMENT) != 1 or old != (existing / "old/Makefile").read_bytes() or fixed != (existing / "new/Makefile").read_bytes():
        raise ValueError("GCC publication provider does not form the approved exact source comparison")
    dump(EVIDENCE / "tool-origins.json", known_locations)
    accelerated_root = WORK / "rpm-extract" / ACCEL_RPM
    if not (accelerated_root / "emul/usr/bin/ld").exists():
        extract(EVIDENCE / ACCEL_RPM, accelerated_root)
    compiler_alias = stage / "usr/armv7l-tizen-linux-gnueabi/bin/gcc"
    if not compiler_alias.is_symlink() and not compiler_alias.exists():
        compiler_alias.symlink_to("../../bin/armv7l-tizen-linux-gnueabi-gcc")
    for lane, patched in (("C", False), ("D", True), ("C-prefix", False), ("D-prefix", True),
                          ("C-accel", False), ("D-accel", True)):
        dest = WORK / lane / "module"
        if not dest.exists():
            shutil.copytree(source / PROVIDER, dest)
        (dest / "Makefile").write_bytes(fixed if patched else old)
    frozen = manifest(source / PROVIDER)
    def selected_manifest(group):
        tree = WORK / group / "module"
        return {name: "symlink:" + os.readlink(tree / name) if (tree / name).is_symlink() else digest(tree / name)
                for name in frozen}
    c = selected_manifest("C")
    d = selected_manifest("D")
    if set(c) != set(d) or [x for x in c if c[x] != d[x]] != ["Makefile"]:
        raise ValueError("Source comparison is not exactly one Makefile")
    if selected_manifest("C-prefix") != c or selected_manifest("D-prefix") != d:
        raise ValueError("Prefix control does not match the source for the corresponding baseline")
    dump(EVIDENCE / "source-manifests.json", {"C": c, "D": d, "C-prefix": c, "D-prefix": d})
    for executable in ("gcc", "armv7l-tizen-linux-gnueabi-gcc", "ld", "ld.bfd", "as", "strip", "objdump", "make", "pahole"):
        member = (stage / "usr/bin" / executable).resolve()
        location = "/" + str(member.relative_to(stage))
        rpm = known_locations[location]
        extracted = WORK / "rpm-extract" / rpm / location.removeprefix("/")
        if digest(member) != digest(extracted):
            raise ValueError(f"Overlay binary does not match extracted package: {member}")
    tool_hashes = {}
    for executable in (stage / "usr/bin").iterdir():
        identity = "/" + str(executable.relative_to(stage))
        if identity in known_locations:
            tool_hashes[identity] = {"source_rpm": known_locations[identity], "sha256": digest(executable)}
    for executable in (stage / "usr/armv7l-tizen-linux-gnueabi/bin").iterdir():
        if executable.is_file():
            resolved = executable.resolve()
            location = "/" + str(resolved.relative_to(stage))
            if location in known_locations:
                tool_hashes["/" + str(executable.relative_to(stage))] = {
                    "source_rpm": known_locations[location], "sha256": digest(resolved), "resolved_path": location,
                }
    dump(EVIDENCE / "tool-hashes.json", tool_hashes)


def bubblewrap(base, group, cross_prefix, cpus, with_accel=False):
    stage = WORK / "stage"
    bind = ["--ro-bind", str(base), "/", "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev"]
    if with_accel:
        bind += ["--ro-bind", str(WORK / "rpm-extract" / ACCEL_RPM / "emul"), "/emul"]
    else:
        bind += ["--tmpfs", "/emul"]
    for relative in ("usr/bin", "usr/lib", "usr/armv7l-tizen-linux-gnueabi"):
        bind += ["--ro-bind", str(stage / relative), "/" + relative]
    bind += ["--ro-bind", str(WORK / "sdk" / "boot"), "/boot", "--bind", str(group), "/tmp/work", "--chdir", "/tmp/work"]
    variables = {
        "LC_ALL": "C", "PATH": "/usr/bin:/bin", "HOME": "/tmp",
        "LOGGER_MAIN_BUFFER_SIZE": "256", "LOGGER_EVENTS_BUFFER_SIZE": "256",
        "LOGGER_RADIO_BUFFER_SIZE": "256", "LOGGER_SYSTEM_BUFFER_SIZE": "256",
        "TIZEN_INFORM_PATH": "/mnt/inform/reboot-param.bin", "THREAD_GROUP_CPUTIME_SUPPORT": "1",
        "TZ": "UTC",
    }
    variables.update({"BUILD_" + name: "m" for name in
                      ("dm_bow", "extcon_usb_fixed", "inform_reboot", "kdbus", "logger", "proc_tsm", "zlogger")})
    if cross_prefix:
        variables["CROSS_COMPILE"] = PREFIX
    for name, value in variables.items():
        bind += ["--setenv", name, value]
    return ["taskset", "-c", cpus, "bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",
            "--die-with-parent", "--clearenv", *bind]


def preserve(lane):
    output = EVIDENCE / "builds" / lane
    source = WORK / lane / "module"
    command_files = ["kdbus/.kdbus.o.cmd", "kdbus/.kdbus.ko.cmd", "kdbus/kdbus.mod", "kdbus/kdbus.o",
                     "kdbus/kdbus.ko", "kdbus/kdbus.mod.o", ".module-common.o", "Module.symvers", "modules.order"]
    for name in command_files:
        path = source / name
        if path.exists():
            target = output / path.name
            shutil.copy2(path, target)
    output_artifacts = {str(path.relative_to(source)): digest(path) for path in sorted(source.rglob("*"))
                        if path.is_file() and path.suffix in (".o", ".ko")}
    installed = {str(path.relative_to(WORK / lane)): digest(path) for path in (WORK / lane / "installed").rglob("*.ko")}
    module = next((path for path in (WORK / lane / "installed").rglob("kdbus.ko")), None)
    if module:
        shutil.copy2(module, output / "kdbus.installed.ko")
    dump(output / "artifacts.json", {"objects_and_modules": output_artifacts, "installed_modules": installed})
    if (source / "kdbus/kdbus.mod").is_file():
        paths = (source / "kdbus/kdbus.mod").read_text().split()
        dump(output / "ordered-inputs.json", [{"path": p, "sha256": digest(source / Path(p).relative_to("/tmp/work/module"))} for p in paths])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "probe", "build"))
    parser.add_argument("--base", type=Path, default=OLD_ROOT)
    parser.add_argument("--cpus", default="14-15")
    parser.add_argument("--lane", choices=("C", "D"), default="C")
    parser.add_argument("--cross-prefix", action="store_true", help="Select the packaged target-prefixed GNU directory")
    parser.add_argument("--with-accel", action="store_true", help="Use checksum-verified candidate accelerated ELF payloads")
    args = parser.parse_args()
    if args.with_accel and args.cross_prefix:
        parser.error("The prefix lane and acceleration lane are separate controls")
    if args.action == "prepare":
        prepare(args.base)
        return
    lane = args.lane + ("-prefix" if args.cross_prefix else "-accel" if args.with_accel else "")
    group = WORK / lane
    bwrap = bubblewrap(args.base, group, args.cross_prefix, args.cpus, args.with_accel)
    build = EVIDENCE / "builds" / lane
    if args.action == "probe":
        probe = """set -eu
uname -m
gcc --version
ld --version
make --version
pahole --version
printf 'CROSS_COMPILE=%s\\n' "${CROSS_COMPILE:-}"
printf 'PATH=%s\\n' "$PATH"
cat /boot/kernel/devel/kernel-devel-arm-rpi4/include/config/kernel.release
"""
        raise SystemExit(run(build / "probe", [*bwrap, "/bin/sh", "-ec", probe]))
    make = ["make", "-j2", "-C", "module", "V=1", "KERNELDIR=/" + SDK]
    cleanup = run(build / "clean", [*bwrap, *make, "clean"])
    if cleanup:
        raise SystemExit(cleanup)
    code = run(build / "make", [*bwrap, *make], trace=True)
    if code == 0:
        code = run(build / "install", [*bwrap, *make, "modules_install", "INSTALL_MOD_STRIP=1",
                                      "INSTALL_MOD_DIR=extra", "INSTALL_MOD_PATH=installed"], trace=True)
    preserve(lane)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
