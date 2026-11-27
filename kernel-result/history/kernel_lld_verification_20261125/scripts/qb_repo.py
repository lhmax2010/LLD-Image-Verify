#!/usr/bin/env python3
"""Verify pinned repository metadata and obtain only the relevant Phase 11 RPMs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT.parent / "kernel_lld_verification_20261120"
REPO = ROOT / "evidence/repository"
AREAS = ("packages", "debug", "source")
NEW_ID = "tizen-unified-toolchain_20261125.130358"
OLD_ID = "tizen-unified-toolchain_20261120.082536"
URL = f"https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/{NEW_ID}/"
STANDARD = URL + "repos/standard/"
TARGET_RELEASE = "6.12.80-arm-rpi4-v7l"
MODULE = re.compile(r"\.ko(?:\.(?:gz|xz|zst))?$")
TARGETS = {
    ("packages", "armv7l", "arm-rpi4-linux-kernel"): "KERNEL_IMAGE",
    ("packages", "armv7l", "arm-rpi4-linux-kernel-devel"): "KERNEL_DEV",
    ("packages", "armv7l", "arm-rpi4-linux-kernel-modules"): "IN_TREE_MODULES",
    ("packages", "armv7l", "linux-tizen-modules-rpi4"): "OUT_OF_TREE_MODULES",
    ("packages", "armv7l", "linux-tizen-modules-source"): "MODULE_BUILD_INPUT",
    ("debug", "armv7l", "arm-rpi4-linux-kernel-devel-debuginfo"): "KERNEL_DEBUGINFO",
    ("debug", "armv7l", "rpi4-linux-kernel-debugsource"): "KERNEL_DEBUGSOURCE",
    ("debug", "armv7l", "linux-tizen-modules-debugsource"): "MODULE_DEBUGSOURCE",
    ("debug", "armv7l", "linux-tizen-modules-source-debugsource"): "MODULE_IMPLEMENTATION_DEBUGSOURCE",
    ("debug", "armv7l", "linux-tizen-modules-tests-debuginfo"): "USERSPACE_TEST_DEBUGINFO",
    ("source", "src", "rpi4-linux-kernel"): "KERNEL_SRPM",
    ("source", "src", "linux-tizen-modules"): "MODULE_WRAPPER_SRPM",
    ("source", "src", "linux-tizen-modules-source"): "MODULE_IMPLEMENTATION_SRPM",
}
ACQUIRE = {"KERNEL_DEV", "IN_TREE_MODULES", "OUT_OF_TREE_MODULES", "MODULE_BUILD_INPUT",
           "KERNEL_SRPM", "MODULE_WRAPPER_SRPM", "MODULE_IMPLEMENTATION_SRPM"}
PROJECTS = {
    "platform/kernel/linux-rpi": "linux-rpi-armv7l",
    "platform/kernel/linux-tizen-modules": "linux-tizen-modules-armv7l",
    "platform/kernel/linux-tizen-modules-source": "linux-tizen-modules-source-armv7l",
}

def relative(path):
    path = Path(path).resolve()
    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return str(path)

def run(stem, args):
    file = Path("evidence") / stem
    proc = subprocess.run(["python3", "-B", "scripts/record_review.py", str(file), *map(str, args)],
                          cwd=ROOT)
    return proc.returncode, ROOT / f"{file}.out"

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")

def digest(path, algorithm="sha256", decompressed=False):
    source = gzip.open if decompressed else open
    with source(path, "rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()

def line_find(path, pattern):
    rc = []
    for no, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        if re.search(pattern, line):
            rc.append({"line": no, "raw": line})
    return rc

def try_build_excerpt(stem):
    path = ROOT / "evidence/build" / f"{stem}.out"
    if not path.exists():
        return None
    lines = line_find(path, r'BUILD_ROOT=|^.*(started|finished).+spec|keeping (clang(?:-accel-x86_64-armv7l)?|llvm|binutils|make)-[0-9]|Wrote:.+(rpi4|linux-tizen-modules)')
    return {"path": relative(path), "sha256": digest(path), "records": lines}

def verify_meta(area):
    raw = REPO / f"{area}-repomd.out"
    root = ET.parse(raw)
    records = {"repomd_path": relative(raw), "repomd_sha256": digest(raw)}
    for kind in ("primary", "filelists"):
        obj = root.find(f".//{{*}}data[@type='{kind}']")
        path = REPO / f"{area}-{kind}.out"
        href = obj.find("{*}location").get("href")
        reference = obj.find("{*}checksum")
        opened = obj.find("{*}open-checksum")
        given, plain = digest(path, reference.get("type")), digest(path, opened.get("type"), True)
        if not (given == reference.text and plain == opened.text and path.stat().st_size == int(obj.findtext("{*}size"))):
            raise ValueError(f"Metadata verification failed for {area}/{kind}")
        records[kind] = {"path": relative(path), "url": urljoin(STANDARD + area + "/", href), "compressed": given,
                         "open_checksum": plain, "compressed_size": path.stat().st_size, "verified": True}
    sig = REPO / f"{area}-repomd-signature.headers"
    if sig.exists():
        matches = re.findall(r"^HTTP/\S+\s+(\d{3})", sig.read_text(), re.M)
        records["signature_http_status"] = int(matches[-1]) if matches else None
    return records

def grouped_files(area):
    scope = {}
    with gzip.open(REPO / f"{area}-filelists.out", "rb") as stream:
        for _, row in ET.iterparse(stream, events=("end",)):
            if row.tag.split("}")[-1] != "package":
                continue
            identity = (area, row.get("arch"), row.get("name"))
            files = [child.text for child in row.findall("{*}file") if child.text]
            release_hits = [name for name in files if f"/modules/{TARGET_RELEASE}/" in name and MODULE.search(name)]
            targeted = [name for name in files if re.search(r"(?:^|/)(?:\.kdbus\.o\.cmd|kdbus\.o(?:\..*)?|kdbus\.ko(?:\..*)?)$", name)]
            if identity in TARGETS or release_hits or targeted:
                scope[row.get("pkgid")] = {"files": files if identity in TARGETS else [],
                                         "target_release_modules": release_hits, "kdbus_path_hits": targeted}
            row.clear()
    return scope

def read_rows(area, files, option_image):
    rows = []
    with gzip.open(REPO / f"{area}-primary.out", "rb") as stream:
        for _, p in ET.iterparse(stream, events=("end",)):
            if p.tag.split("}")[-1] != "package":
                continue
            name, arch = p.findtext("{*}name"), p.findtext("{*}arch")
            item = (area, arch, name)
            checksum = p.find("{*}checksum")
            info = files.get(checksum.text, {})
            if item not in TARGETS and not info.get("target_release_modules") and not info.get("kdbus_path_hits"):
                p.clear()
                continue
            version = p.find("{*}version")
            stamp = int(p.find("{*}time").get("build"))
            filetime = int(p.find("{*}time").get("file"))
            href = p.find("{*}location").get("href")
            role = TARGETS.get(item, "OTHER_FILELIST_MATCH")
            download = role in ACQUIRE or (option_image and role=="KERNEL_IMAGE")
            if role=="OTHER_FILELIST_MATCH" and info.get("target_release_modules"):
                role, download = "OTHER_TARGET_RELEASE_MODULE_PAYLOAD", True
            if role=="OTHER_FILELIST_MATCH" and any(n.endswith("kdbus.ko.debug") for n in info.get("kdbus_path_hits", [])):
                role, download = "KDBUS_MODULE_DEBUGINFO", True
            src = p.findtext("{*}format/{*}sourcerpm") or None
            label = f"{name}-{version.get('ver')}-{version.get('rel')}.{arch}.rpm"
            rows.append({"role": role, "area": area, "name": name, "epoch": version.get("epoch"),
                         "version": version.get("ver"), "release": version.get("rel"), "arch": arch,
                         "nevra": f"{name}-{version.get('epoch')}:{version.get('ver')}-{version.get('rel')}.{arch}",
                         "filename": label, "source_rpm": src, "source_revision": version.get("vcs"),
                         "build_time_epoch_metadata": stamp,
                         "build_time_utc_metadata": datetime.fromtimestamp(stamp,timezone.utc).isoformat() if stamp else None,
                         "metadata_file_time_utc": datetime.fromtimestamp(filetime,timezone.utc).isoformat() if filetime else None,
                         "download_url": urljoin(STANDARD + area + "/", href),
                         "published_bytes": int(p.find("{*}size").get("package")),
                         "checksum_algorithm": checksum.get("type"),
                         "published_checksum": checksum.text, "acquire": download,
                         "target_release_modules_count": len(info.get("target_release_modules", [])),
                         "target_release_modules": info.get("target_release_modules", []),
                         "kdbus_path_hits": info.get("kdbus_path_hits", []),
                         "filelists_count": len(info.get("files", []))})
            if area=="debug" and info.get("files"):
                destination = REPO / "filelists" / f"{label}.txt"
                destination.parent.mkdir(exist_ok=True,parents=True)
                destination.write_text("\n".join(info["files"])+"\n")
                rows[-1]["metadata_filelist_path"] = relative(destination)
            p.clear()
    return rows

def prior_checksums():
    with (OLD / "02_kernel_rpm_inventory.csv").open(newline="") as stream:
        return {(r["repository_area"], r["name"], r["architecture"]):r for r in csv.DictReader(stream)}

def obtain(row, old_rows):
    expected = row["published_checksum"]
    old = old_rows.get((row["area"], row["name"], row["arch"]))
    row["old_metadata_checksum"] = old["metadata_checksum"] if old else None
    row["identical_to_old_metadata_checksum"] = expected==old["metadata_checksum"] if old else None
    row["artifact_path"] = None
    row["local_sha256"] = None
    row["repository_checksum_verification"] = "METADATA_ONLY"
    row["rpm_verification"] = "NOT_RUN"
    if not row["acquire"]:
        return row
    label = row["filename"]
    path = REPO / "rpms" / label
    path.parent.mkdir(exist_ok=True,parents=True)
    old_path = OLD / "evidence/repository/rpms" / label
    reuse = bool(row["identical_to_old_metadata_checksum"] and old_path.is_file())
    if reuse:
        path = old_path
    elif not path.exists() or digest(path,row["checksum_algorithm"])!=expected:
        partial=path.with_name(path.name+".part")
        rc, _ = run(f"repository/rpm-{label}-download", ["curl","-fLsS","--retry","2","--connect-timeout","8",
                             "--max-time","160","-D",f"evidence/repository/{label}.headers","-o",relative(partial),row["download_url"]])
        if rc!=0:
            row["repository_checksum_verification"]="DOWNLOAD_FAILED"
            return row
        if partial.stat().st_size!=row["published_bytes"] or digest(partial,row["checksum_algorithm"])!=expected:
            row["repository_checksum_verification"]="MISMATCH"
            row["artifact_path"]=relative(partial)
            return row
        partial.replace(path)
    row["artifact_path"] = relative(path)
    row["local_sha256"] = digest(path)
    row["acquisition"] = "REUSED_OLD_BYTES_FROM_NEW_METADATA" if reuse else "DOWNLOADED_NEW_SNAPSHOT"
    if digest(path,row["checksum_algorithm"])!=expected or path.stat().st_size!=row["published_bytes"]:
        row["repository_checksum_verification"]="MISMATCH"
        return row
    row["repository_checksum_verification"] = "PASS"
    rc, output = run(f"repository/rpm-{label}-header",
                     ["rpm","-qp","--qf","%{NAME}\\t%{EPOCH}\\t%{VERSION}\\t%{RELEASE}\\t%{ARCH}\\t%{SOURCERPM}\\t%{BUILDTIME}\\t%{BUILDHOST}\\t%{VCS}\\t%{SOURCEPACKAGE}\\n",
                      relative(path)])
    row["header_evidence"] = relative(output)
    if rc==0:
        values = output.read_text().strip().split("\\t")
        if len(values)==1:
            values = output.read_text().strip().split("\t")
        if len(values)==10:
            keys = ("name","epoch","version","release","arch","source_rpm","buildtime","buildhost","vcs","sourcepackage")
            row["rpm_header"] = dict(zip(keys,values,strict=True))
            expected_arr = [row["name"],row["version"],row["release"],row["source_revision"]]
            seen_arr = [values[0], values[2], values[3], values[8]]
            is_expected_arch = values[4]==row["arch"] or (row["arch"]=="src" and values[9]=="1")
            row["rpm_header_verified"] = is_expected_arch and seen_arr == expected_arr
    rc, output = run(f"repository/rpm-{label}-verify", ["rpm","-Kv",relative(path)])
    row["verification_evidence"] = relative(output)
    row["rpm_verification"] = "PASS" if rc==0 else "NEEDS_REVIEW"
    rc, output = run(f"repository/rpm-{label}-members", ["rpm","-qpl",relative(path)])
    row["member_evidence"] = relative(output)
    return row

def snapshot_info(snapshot_root, build, manifest):
    root=ET.parse(build).getroot()
    tree=ET.parse(manifest).getroot()
    return {"id":root.findtext("id"),"base_id":root.findtext("base_id"),
            "build_xml":str(build.relative_to(snapshot_root)),"build_xml_sha256":digest(build),
            "manifest":str(manifest.relative_to(snapshot_root)),"manifest_sha256":digest(manifest),
            "project_revisions":{p.get("name"):p.get("revision") for p in tree.iter("project") if p.get("name") in PROJECTS}}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--include-image",action="store_true")
    args=parser.parse_args()
    old=prior_checksums()
    with ThreadPoolExecutor(max_workers=3) as pool:
        metadata = dict(zip(AREAS,pool.map(verify_meta,AREAS),strict=True))
        filelists = dict(zip(AREAS,pool.map(grouped_files,AREAS),strict=True))
    rows=[r for a in AREAS for r in read_rows(a,filelists[a],args.include_image)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows=list(pool.map(lambda r:obtain(r,old),rows))
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT / "11A_RPM_INVENTORY.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    old_meta=snapshot_info(OLD,OLD/"evidence/repository/publication-build.out",OLD/"evidence/repository/manifest.out")
    new_meta=snapshot_info(ROOT,REPO/"build-identity.out",REPO/"manifest.out")
    old_wrapper = next(r for r in old.values() if r["name"]=="linux-tizen-modules-rpi4" and r["architecture"]=="armv7l")
    new_wrapper = next(r for r in rows if r["role"]=="OUT_OF_TREE_MODULES")
    if new_meta["id"]!=NEW_ID or old_meta["id"]!=OLD_ID:
        raise RuntimeError("Snapshot identity mismatch")
    planned=[r for r in rows if r["acquire"]]
    bad=[r["filename"] for r in planned if r["repository_checksum_verification"]!="PASS" or
         r["rpm_verification"]!="PASS" or not r.get("rpm_header_verified")]
    debug_hits=[{"name":r["name"],"arch":r["arch"],"paths":r["kdbus_path_hits"]} for r in rows if r["area"]=="debug" and r["kdbus_path_hits"]]
    if not new_wrapper.get("artifact_path"):
        raise RuntimeError("Target wrapper artifact unavailable")
    dump(ROOT/"11A_QB_IDENTITY.json",
         {"old":old_meta,"new":new_meta,"metadata":metadata,"rpm_rows":rows,
          "preflight_status":"PASS" if not bad else "PARTIAL","acquisition_issues":bad,
          "requested_runtime_release":TARGET_RELEASE,
          "target_wrapper_changed_rpm_sha256":new_wrapper["published_checksum"]!=old_wrapper["metadata_checksum"],
          "total_new_modules_filelists":sum(r["target_release_modules_count"] for r in rows),
          "published_matching_module_debug_hits":debug_hits,
          "build_records":{p:try_build_excerpt(log) for p,log in PROJECTS.items()}})
    print(f"Recorded {len(rows)} RPM inventory rows, planned {len(planned)}; acquisition issues {bad}.")
    for r in planned:
        print(r["role"],r["artifact_path"],r["repository_checksum_verification"],r.get("rpm_header_verified"))

if __name__=="__main__":
    main()
