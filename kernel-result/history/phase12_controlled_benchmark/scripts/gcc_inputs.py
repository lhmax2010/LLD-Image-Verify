#!/usr/bin/env python3
"""Resolve the pinned Tizen GCC candidate SDK, wrapper and toolchain."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest, new
from pathlib import Path
import gzip
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/gcc"
QB = "https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Dev/tizen-unified-dev_20261120.082616/"
BASE = "https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Dev/tizen-base-dev_20261119.042444/"
QB_PACKAGES = QB + "repos/standard/packages/"
QB_SOURCE = QB + "repos/standard/source/"
BASE_PACKAGES = BASE + "repos/standard/packages/"


def digest(path, algorithm="sha256"):
    with open(path, "rb") as stream:
        return file_digest(stream, algorithm).hexdigest()


def store(name, record):
    (EVIDENCE / name).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")


def fetch(filename, url, expected=None):
    local = EVIDENCE / filename
    if expected and local.is_file() and digest(local, expected[0]) == expected[1]:
        return local
    result = subprocess.run(
        command := ["curl", "-fLsS", "--connect-timeout", "15", "--max-time", "180",
                    "-D", str(local) + ".headers", "-o", str(local), url],
        capture_output=True, text=True,
    )
    store(filename + ".cmd.json", {
        "argv": command, "exit_status": result.returncode, "stderr": result.stderr,
        "sha256": digest(local) if local.is_file() else None,
    })
    result.check_returncode()
    if expected and digest(local, expected[0]) != expected[1]:
        raise ValueError(f"Checksum mismatch for {filename}")
    return local


def primary(label, repo):
    repomd = fetch(label + "-repomd.xml", repo + "repodata/repomd.xml")
    data = ET.parse(repomd).find(".//{*}data[@type='primary']")
    location = data.find("{*}location").attrib["href"]
    checksum = data.find("{*}checksum")
    zipped = fetch(label + "-primary.xml.gz", repo + location, (checksum.attrib["type"], checksum.text))
    opened = gzip.decompress(zipped.read_bytes())
    open_checksum = data.find("{*}open-checksum")
    if open_checksum is not None and new(open_checksum.attrib["type"], opened).hexdigest() != open_checksum.text:
        raise ValueError(f"Uncompressed metadata checksum mismatch for {label}")
    packages = []
    for package in ET.fromstring(opened):
        label = package.findtext("{*}name")
        version = package.find("{*}version").attrib
        href = package.find("{*}location").attrib["href"]
        sha = package.find("{*}checksum")
        packages.append({
            "name": label, "arch": package.findtext("{*}arch"), "version": version,
            "url": repo + href, "filename": Path(href).name,
            "checksum": [sha.attrib["type"], sha.text], "size": int(package.find("{*}size").attrib["package"]),
            "source_rpm": package.findtext(".//{*}sourcerpm"),
        })
    return packages


def package_row(matrix, kind, arch, name):
    rows = [p for p in matrix[kind] if p["arch"] == arch and p["name"] == name]
    if len(rows) != 1:
        raise ValueError(f"Expected 1 {kind}:{arch}:{name}, found {len(rows)}")
    return rows[0]


def download_package(package):
    file = fetch(package["filename"], package["url"], package["checksum"])
    if file.stat().st_size != package["size"]:
        raise ValueError(f"Unexpected size for {file}")
    return file


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    small = {
        "build.xml": QB + "build.xml",
        "project-manifest.xml": QB + "builddata/manifest/tizen-unified-dev_20261120.082616_standard.xml",
        "linux-rpi-armv7l.log": QB + "builddata/buildlogs/standard/armv7l/succeeded/linux-rpi.buildlog.txt",
        "linux-tizen-modules-armv7l.log": QB + "builddata/buildlogs/standard/armv7l/succeeded/linux-tizen-modules.buildlog.txt",
    }
    repositories = {"package": QB_PACKAGES, "source": QB_SOURCE, "base-package": BASE_PACKAGES}
    with ThreadPoolExecutor() as pool:
        remote = {name: pool.submit(fetch, name, url) for name, url in small.items()}
        repo_futures = {kind: pool.submit(primary, kind, repo) for kind, repo in repositories.items()}
        matrix = {kind: future.result() for kind, future in repo_futures.items()}
        for name, request in remote.items():
            try:
                request.result()
            except subprocess.CalledProcessError as error:
                print(f"{name} request failed with curl exit {error.returncode}; see receipt")
        target = {
            "package": {"arm-rpi4-linux-kernel-devel", "arm-rpi4-linux-kernel-btf-devel",
                        "arm-rpi4-linux-kernel", "arm-rpi4-linux-kernel-modules", "linux-tizen-modules-rpi4",
                        "linux-tizen-modules-source"},
            "source": {"linux-tizen-modules", "linux-tizen-modules-source", "rpi4-linux-kernel"},
            "base-package": {"gcc", "cpp", "binutils", "glibc", "libgcc", "make", "dwarves",
                             "qemu-accel-x86_64-armv7l", "gcc-accel-x86_64-armv7l", "elfutils",
                             "libelf", "elfutils-libelf", "libzstd", "zlib"},
        }
        selected = {
            kind: [p for p in matrix[kind] if p["name"] in names and p["arch"] in ("armv7l", "x86_64", "src")]
            for kind, names in target.items()
        }
        store("package-inventory.json", selected)
        needs = [
            ("package", "armv7l", "arm-rpi4-linux-kernel-devel"),
            ("source", "src", "linux-tizen-modules"),
            ("package", "armv7l", "linux-tizen-modules-rpi4"),
        ]
        build_packages = {
            "package": {"linux-tizen-modules-source", "arm-rpi4-linux-kernel-btf-devel",
                        "dwarves", "libdwarves1", "libbpf", "libbpf1"},
            "base-package": {"gcc", "cpp", "binutils", "binutils-libs", "glibc", "libgcc",
                             "libelf", "libdw", "libzstd1", "zlib", "make", "libmpfr",
                             "libmpc", "libgmp", "elfutils", "libbpf", "libbpf1", "libpopt",
                             "qemu-accel-x86_64-armv7l"},
        }
        chosen = [package for kind, names in build_packages.items() for package in matrix[kind]
                  if package["arch"] == "armv7l" and package["name"] in names]
        store("selected-build-packages.json", chosen)
        list(pool.map(download_package, [package_row(matrix, *args) for args in needs] + chosen))
    for kind, values in selected.items():
        for p in values:
            print(kind, p["name"], p["arch"], p["version"], p["size"])


if __name__ == "__main__":
    main()
