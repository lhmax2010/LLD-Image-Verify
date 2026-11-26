#!/usr/bin/env python3
"""Recover image RPM ownership by exact payload bytes, path and installed RPM list."""
import argparse
from collections import defaultdict
from importlib import import_module
from pathlib import Path
import re

image = import_module("export-image-evidence")
RENAMED = {
    "powerkey-popup": "powerkey-popup.common",
    "system-syspopup": "system-syspopup.common",
    "fota_gui": "fota_gui_common",
    "rw-update-ani": "rw-update-ani-common",
    "sysapp-launcher": "sysapp-launcher.common",
    "system-recovery_gui": "recovery_gui_common",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--rpm-files", type=Path, required=True)
    parser.add_argument("--package-lists", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rpm_files = defaultdict(list)
    for row in image.rows(args.rpm_files):
        rpm_files[row["snapshot"], row["arch"], row["path"], row["sha256"]].append(row)
    buildlogs = args.data / "buildlog-package-evidence.csv"
    sources = {(r["snapshot"], r["arch"], r["package"]): r for r in image.rows(buildlogs)} if buildlogs.exists() else {}
    result = []
    for row in image.rows(args.data / "unattributed-lld-instances.csv"):
        target = row["path"].removeprefix("/mnt/initrd-recovery")
        name = Path(target).name
        alternatives = [target, str(Path(target).with_name(RENAMED[name]))]
        candidates = [r for path in alternatives for r in
                      rpm_files[row["snapshot"], row["arch"], path, row["sha256"]]]
        listing = next(args.package_lists.glob(f'{row["snapshot"]}*{row["image"]}.packages'))
        packages = {}
        for line in listing.read_text().splitlines():
            parts = line.split(maxsplit=2)
            if len(parts) == 3:
                packages[" ".join(parts[:2])] = parts[2].split("#")
        matched = []
        for candidate in candidates:
            # Strip the candidate's epoch and reconstruct the MIC label.
            name, version = re.split(r"-\d+:", candidate["nevra"], maxsplit=1)
            version, arch = version.rsplit(".", 1)
            label = f"{name}.{arch} {version}"
            if label in packages:
                matched.append((candidate, label))
        if len(matched) != 1:
            raise ValueError(f"Expected one installed RPM match for {row['image']} {row['path']}: {matched}")
        rpm, label = matched[0]
        source, revision = packages[label]
        source_package = rpm["source"].removesuffix(".src.rpm").rsplit("-", 2)[0]
        compiler = sources.get((row["snapshot"], row["arch"], source_package), {})
        result.append(dict(snapshot=row["snapshot"], image=row["image"], arch=row["arch"],
                           partition=row["partition"], path=row["path"], sha256=row["sha256"],
                           rpm_payload_path=rpm["path"], rpm_payload_sha256=rpm["sha256"], rpm_label=label,
                           rpm_nevra=rpm["nevra"], rpm_url=rpm["url"], rpm_digest=rpm["digest"],
                           source=source, source_commit=revision, image_package_list=listing.name,
                           debug_url=rpm["debug_url"], debug_path=rpm["debug_path"],
                           compiler_observed=compiler.get("compiler_observed", ""),
                           gcc_only_by_recipe="no" if compiler.get("compiler_observed") == "Clang" else "undetermined",
                           compiler_log=compiler.get("url", ""),
                           compiler_log_lines=compiler.get("cc_cxx_export", ""),
                           recovery_note=("recovery ramdisk copy of RPM file" if row["partition"] == "ramdisk-recovery"
                                          else "profile-suffixed installed RPM file with the same payload SHA256")))
    if len(result) != 32:
        raise ValueError(f"Expected 32 recovered instances, got {len(result)}")
    image.write_csv(args.output, result)


if __name__ == "__main__":
    main()
