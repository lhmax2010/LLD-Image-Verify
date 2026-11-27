"""Read-only RPM extraction and evidence receipts for Phase 11B–D."""
import csv
import datetime
import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "evidence/repository"
SRC = ROOT / "evidence/source"
BUILD = ROOT / "evidence/build"
ARCHIVE = ROOT.parent / "kernel_lld_verification_20261120"


def rel(path):
    return str(Path(path).relative_to(ROOT))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def store(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def capture(stem, argv, allowed=(0,)):
    argv = [str(x) for x in argv]
    raw = str(stem)
    tick = time.monotonic()
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(raw + ".out", "wb") as stdout, open(raw + ".err", "wb") as stderr:
        outcome = subprocess.run(argv, stdout=stdout, stderr=stderr, cwd=ROOT, check=False)
    store(Path(raw + ".cmd.json"), dict(argv=argv, cwd=str(ROOT), started_utc=start,
                                      elapsed_seconds=round(time.monotonic()-tick, 3), exit_status=outcome.returncode))
    if outcome.returncode not in allowed:
        raise RuntimeError(f"{argv!r}: {outcome.returncode}")
    return Path(raw + ".out")


def lines(stem, argv, allowed=(0,)):
    return capture(stem, argv, allowed).read_text(encoding="utf-8", errors="replace").splitlines()


def metadata_rpm(area, filename):
    parent = REPO / f"{area}-repomd.out"
    primary = REPO / f"{area}-primary.out"
    digest_node = next(x for x in ET.parse(parent).getroot().findall("{*}data")
                       if x.get("type") == "primary")
    stored = primary.read_bytes()
    opened = gzip.decompress(stored)
    for node_name, data in (("checksum", stored), ("open-checksum", opened)):
        node = digest_node.find("{*}"+node_name)
        if hashlib.new(node.get("type"), data).hexdigest() != node.text:
            raise ValueError(f"{primary} {node_name} mismatch")
    found = [x for x in ET.fromstring(opened).findall("{*}package")
             if Path(x.find("{*}location").get("href")).name == filename]
    if len(found) != 1:
        raise ValueError(f"{area}: expected a single {filename}, got {len(found)}")
    p = found[0]
    checksum = p.find("{*}checksum")
    return {"name": p.findtext("{*}name"), "arch": p.findtext("{*}arch"),
            "nevra": p.find("{*}version").attrib,
            "sha256": checksum.text,
            "checksum_type": checksum.get("type"),
            "size": int(p.find("{*}size").get("package")),
            "metadata": rel(primary), "href": p.find("{*}location").get("href"),
            "sourcerpm": p.find("{*}format").findtext("{*}sourcerpm")}


def verify_rpm(rpm, meta):
    if int(meta["size"]) != rpm.stat().st_size or meta["sha256"] != digest(rpm) or meta.get("checksum_type", "sha256") != "sha256":
        raise ValueError(f"wrong RPM bytes for {rpm}")


def extract(rpm, members, folder, stem):
    """Use CPIO to select exact listed members. Preserve both pipeline statuses."""
    folder.mkdir(parents=True, exist_ok=True)
    argv = [["rpm2cpio", str(rpm)], ["cpio", "-idu", "--quiet", "--no-absolute-filenames", "-D", str(folder), *members]]
    tick = time.monotonic()
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (stem.parent / (stem.name+".first.err")).open("wb") as first_err, \
         (stem.parent / (stem.name+".out")).open("wb") as stdout, \
         (stem.parent / (stem.name+".err")).open("wb") as stderr:
        with subprocess.Popen(argv[0], stdout=subprocess.PIPE, stderr=first_err, cwd=ROOT) as first:
            second = subprocess.run(argv[1], stdin=first.stdout, stdout=stdout, stderr=stderr,
                                    cwd=ROOT, check=False)
            first.stdout.close()
            statuses = (first.wait(), second.returncode)
    store(stem.parent / (stem.name+".cmd.json"), dict(argv=argv, cwd=str(ROOT), started_utc=start,
          elapsed_seconds=round(time.monotonic()-tick, 3), pipeline_exit_statuses=statuses,
          exit_status=next((status for status in statuses if status), 0)))
    if statuses != (0, 0):
        raise RuntimeError(f"could not extract {rpm}: {statuses}")


def tool_verify():
    base = BUILD / "base"
    metadata = json.loads((base/"matched-metadata.json").read_text())["packages"]
    candidates = {
        "llvm":("/usr/bin/ld.lld", "/usr/bin/lld"),
        "clang-accel-x86_64-armv7l":("/emul/usr/bin/ld.lld",),
    }
    check_digests = {}
    results = []
    for name, member_paths in candidates.items():
        m = next(row for row in metadata if row["name"]==name)
        rpm = base / "rpms" / Path(m["href"]).name
        verify_rpm(rpm, m)
        capture(base/(name+".rpm-verify"), ["rpm", "-Kv", rpm], (0, 1))
        scripts = lines(base/(name+".rpm-scripts"), ["rpm", "-qp", "--scripts", rpm])
        listing = lines(base/(name+".rpm-members"), ["rpm", "-qp", "--dump", rpm])
        entry = next(line.split() for line in listing if line.startswith(member_paths[0]+" "))
        target_member = member_paths[0] if entry[-1] in ("X", "x") else str(Path(member_paths[0]).parent / entry[-1])
        if target_member not in member_paths:
            raise ValueError(f"unexpected link target {target_member}")
        target_entry = next(line.split() for line in listing if line.startswith(target_member+" "))
        folder = base / "tool-extract" / name
        extract(rpm, ["."+item for item in member_paths], folder, base/(name+".extract"))
        tool_path = folder / target_member.lstrip("/")
        if tool_path.is_symlink() or not tool_path.is_file():
            raise ValueError(f"missing regular linker {tool_path}")
        actual_sha = digest(tool_path)
        if target_entry[3] != actual_sha:
            raise ValueError(f"linker payload digest mismatch: {name}")
        if target_member != member_paths[0] and not (folder/member_paths[0].lstrip("/")).is_symlink():
            raise ValueError(f"expected symlink {member_paths[0]}")
        header = lines(base/(name+".readelf"), ["readelf", "-h", "-l", tool_path])
        tool_build_id = lines(base/(name+".notes"), ["readelf", "-n", tool_path])
        if name == "llvm":
            version = lines(base/(name+".version"),
                            ["bash", "-o", "pipefail", "-c",
                             'strings -a "$1" | grep -E "^LLD 22[.]1[.]8([[:space:]]|$)"', "--", tool_path])
            version_method = "embedded exact version string"
        else:
            symbol = "_ZN3lld13getLLDVersionB5cxx11Ev"
            symbols = lines(base/(name+".symbols"), ["readelf", "--dyn-syms", "--wide", tool_path])
            version_row = next(row.split() for row in symbols if row.rstrip().endswith(symbol))
            if not any("_ZN3lld3elf4link" in row for row in symbols):
                raise ValueError("LLVM ELF linker entry point missing")
            start = int(version_row[1], 16)
            stop = start + int(version_row[2])
            instructions = lines(base/(name+".version-disassembly"),
                                 ["objdump", "-d", f"--start-address={start:#x}",
                                  f"--stop-address={stop:#x}", tool_path])
            prefix = next(re.search(r"movabs \$0x([0-9a-f]+),%rcx", row)
                          for row in instructions if "movabs" in row)
            suffix = next(re.search(r"movw\s+\$0x([0-9a-f]+),0x18\(%rdi\)", row)
                          for row in instructions if "movw" in row)
            version = [(int(prefix[1], 16).to_bytes(8, "little") +
                        int(suffix[1], 16).to_bytes(2, "little")).decode("ascii")]
            if version != ["LLD 22.1.8"]:
                raise ValueError(f"unexpected accelerated linker version: {version}")
            version_method = "ELF dynsyms plus decoded immediate bytes in lld::getLLDVersion()"
        results.append({"rpm": rel(rpm), "package": m, "rpm_sha256_verified": True,
                        "member": member_paths[0], "resolved_in_package": target_member,
                        "payload_sha256": actual_sha, "rpm_file_digest_verified": True,
                        "elf_machine": next(s.split(":",1)[1].strip() for s in header if s.strip().startswith("Machine:")),
                        "version_strings": version, "version_method": version_method,
                        "build_id_lines": [s.strip() for s in tool_build_id if "Build ID:" in s],
                        "payload_evidence": rel(tool_path), "scriptlet_lines": scripts,
                        "verification_method": "RPM header/membership, SHA256 and static ELF inspection"})
        check_digests[name] = actual_sha
    store(base/"linker-payload-identities.json", {"candidates": results,
             "new_base_snapshot": "tizen-base-toolchain_20261030.120529",
             "path_or_executable_actually_run_observed": False})
    print(json.dumps(check_digests, indent=2))


def make_recipe(name):
    filename = Path(name).name
    return (filename in {"Makefile", "Kbuild", "CMakeLists.txt", "configure", "config.guess"} or
            Path(name).suffix in {".spec", ".mk", ".patch", ".diff", ".sh", ".inc"})


def source_verify():
    phase10 = ROOT.parent / "phase10_kdbus_sandbox"
    history_path = phase10 / "KDBUS_LD_FIX_SUBMISSION_SUMMARY.json"
    history = json.loads(history_path.read_text())
    provider_project = "platform/kernel/linux-tizen-modules-source"
    wrapper_project = "platform/kernel/linux-tizen-modules"
    fix = history["new_commit_sha"]
    old_commit = history["historical_image_source_commit"]
    git = ["git", "-C", phase10/"checkout"]
    manifest_paths = {
        "old": ARCHIVE/"evidence/repository/manifest.out",
        "new": REPO/"manifest.out",
    }
    revisions = {}
    for key, path in manifest_paths.items():
        projects = ET.parse(path).getroot().findall(".//project")
        revisions[key] = {entry["name"]: entry.get("revision") for node in projects
                          if (entry := node.attrib)["name"] in {provider_project, wrapper_project}}
    if revisions["new"][provider_project] != fix or revisions["old"][provider_project] != old_commit:
        raise ValueError("manifest and Phase 10 implementation revisions differ")
    if revisions["old"][wrapper_project] != revisions["new"][wrapper_project]:
        raise ValueError("wrapper revision changed")
    observed_fix = lines(SRC/"phase10-git-fix-object", [*git, "show", "-s", "--format=%H%n%P%n%B", fix])
    if observed_fix[:2] != [fix, old_commit] or f"Change-Id: {history['gerrit_change_id']}" not in observed_fix:
        raise ValueError("Phase 10 commit object does not match the independent manifests")
    tracked = lines(SRC/"phase10-git-fix-paths", [*git, "diff", "--name-only", old_commit, fix])
    if tracked != ["kernel/Makefile"]:
        raise ValueError(f"unexpected Phase 10 file list: {tracked}")

    rpm_paths = {"old": ARCHIVE/"pm_review_round2/evidence/external/linux-tizen-modules-source-11.0.0-0.armv7l.rpm",
                 "new": REPO/"rpms/linux-tizen-modules-source-11.0.0-0.armv7l.rpm"}
    prefix = "/usr/src/linux-tizen-modules-source/"
    payloads, payload_sha256, provider_headers = {}, {}, {}
    for key, rpm in rpm_paths.items():
        meta = metadata_rpm("packages", rpm.name) if key == "new" else {
            "sha256": "b8fdab693b2a21fb263ae9e24c5eb14e20097e12ee4a71681ff8edb8aa93f6b9",
            "size": rpm.stat().st_size,
        }
        verify_rpm(rpm, meta)
        listing = lines(SRC/(key+"-provider-rpm-dump"), ["rpm", "-qp", "--dump", rpm])
        headers = [row.split() for row in listing if row.startswith(prefix)]
        if any(not stat.S_ISREG(int(row[4], 8)) for row in headers):
            raise ValueError("nonregular provider members need separate verification")
        folder = SRC/key/"provider-rpm"
        extract(rpm, ["."+row[0] for row in headers], folder, SRC/(key+"-provider-member-extraction"))
        rows = {row[0].removeprefix(prefix): folder/row[0].lstrip("/") for row in headers}
        digests = {name: digest(path) for name, path in rows.items()}
        if digests != {row[0].removeprefix(prefix): row[3] for row in headers}:
            raise ValueError(f"{key} provider CPIO file digest mismatch")
        provider_headers[key] = {
            "rpm": os.path.relpath(rpm, ROOT), "sha256": digest(rpm), "metadata": meta,
            "vcs": lines(SRC/(key+"-provider-header-vcs"),["rpm", "-qp", "--qf", "%{VCS}\\n", rpm])[0],
            "verified_source_member_count": len(digests),
        }
        if provider_headers[key]["vcs"] != f"{provider_project}#{revisions[key][provider_project]}":
            raise ValueError(f"{key} provider RPM VCS does not match its QB manifest")
        for name in ("Makefile", "kdbus/Makefile"):
            destination = SRC/key/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                destination.write_bytes(rows[name].read_bytes())
            git_file = capture(SRC/(key+"-phase10-git-"+name.replace("/","-")), [*git, "show",
                               f"{revisions[key][provider_project]}:kernel/{name}"])
            if not (destination.read_bytes() == rows[name].read_bytes() == git_file.read_bytes()):
                raise ValueError(f"{key} provider/Git Makefile bytes differ: {name}")
        payloads[key], payload_sha256[key] = rows, digests
    differing_members = sorted(k for k in set(payload_sha256["old"]) | set(payload_sha256["new"])
                               if payload_sha256["old"].get(k) != payload_sha256["new"].get(k))
    expected_deletion = b"LD = ${CROSS_COMPILE}ld\n"
    old = payloads["old"]["Makefile"].read_bytes()
    new = payloads["new"]["Makefile"].read_bytes()
    if differing_members != ["Makefile"] or old.count(expected_deletion) != 1 or old.replace(expected_deletion, b"") != new:
        raise ValueError(f"source compare differs from the approved deletion: {differing_members}")
    patch = "diff --git a/kernel/Makefile b/kernel/Makefile\n" + "".join(difflib.unified_diff(
        old.decode().splitlines(keepends=True), new.decode().splitlines(keepends=True), "a/kernel/Makefile", "b/kernel/Makefile"))
    (ROOT/"11B_SOURCE_DIFF.patch").write_text(patch)

    srpm_paths = {"provider": REPO/"rpms/linux-tizen-modules-source-11.0.0-0.src.rpm",
                  "wrapper": ARCHIVE/"evidence/repository/rpms/linux-tizen-modules-11.0.0-0.src.rpm"}
    override = re.compile(r"(?m)^[ \t]*(?:override\s+|export\s+|private\s+)*(?:LD|PATH|CROSS_COMPILE)\s*[:+?!]?=|"
                          r"\bld\.bfd\b|(?:^|[;|&()]\s*|\t)(?:\S*/)?(?:\S+-)?ld(?:\.lld)?\s|"
                          r"(?:^|[ \t])LD\s*[:+?!]?=|\b-fuse-ld=|"
                          r"(?im:^\s*(?:Patch\d*:|%patch\b|%autopatch\b|%autosetup\b))")
    scans = {}; source_info = {}
    for key, rpm in srpm_paths.items():
        meta = metadata_rpm("source", rpm.name)
        verify_rpm(rpm, meta)
        folder = SRC/"new"/(key+"-srpm")
        listed = lines(SRC/(key+"-srpm-members"), ["rpm", "-qpl", rpm])
        extract(rpm, listed+["./"+name for name in listed], folder, SRC/(key+"-srpm-extraction"))
        spec = next(folder.glob("*.spec"))
        source = next(folder.glob("*.tar.xz"))
        recipe_candidates = {rel(spec):spec.read_bytes()}
        with tarfile.open(source) as tar:
            all_members = tar.getmembers()
            archive_files = {entry.name.split("/", 1)[1]:tar.extractfile(entry).read()
                             for entry in all_members if entry.isfile() and "/" in entry.name}
        if sorted(name for name in archive_files if name.startswith("kernel/")) and key == "wrapper":
            raise ValueError("wrapper tarball would already provide ./kernel files")
        recipe_candidates.update({name: content for name,content in archive_files.items() if make_recipe(name)})
        if key == "provider":
            for name, file_path in payloads["new"].items():
                archive_name = "kernel/"+name if name not in {"COPYING"} and not name.startswith("include/") else name
                if archive_files.get(archive_name) != file_path.read_bytes():
                    raise ValueError(f"source provider payload differs from SRPM tarball: {name}")
        matches = {name: [f"{number}:{line}" for number, line in enumerate(raw.decode(errors="replace").splitlines(),1)
                          if override.search(line)] for name,raw in recipe_candidates.items()}
        active_matches = {name: hit for name,hit in matches.items() if hit}
        if active_matches:
            raise ValueError(f"Potential linker bypass in SRPM recipes needs review: {active_matches}")
        scans[key] = {"scanned_recipe_files": sorted(recipe_candidates), "bypass_or_patch_matches": active_matches,
                      "archive_regular_file_count": len(archive_files)}
        vcs = re.search(r"(?m)^VCS:\s+(\S+)",spec.read_text()).group(1)
        project = provider_project if key=="provider" else wrapper_project
        if vcs != f"{project}#{revisions['new'][project]}":
            raise ValueError(f"{key} SRPM SPEC VCS does not match QB manifest")
        source_info[key] = {"rpm": os.path.relpath(rpm, ROOT), "metadata": meta, "vcs": vcs,
                            "spec": rel(spec), "spec_sha256": digest(spec),
                            "source0": rel(source), "source0_sha256": digest(source)}

    log = BUILD/"linux-tizen-modules-armv7l.out"
    provider_log = BUILD/"linux-tizen-modules-source-armv7l.out"
    needed = ["linux-tizen-modules-source-11.0.0-0   #", "cp -a /usr/src/linux-tizen-modules-source ./kernel",
              "sed -i s/-Wno-error=missing-attributes//g"]
    for expected in needed:
        if expected not in log.read_text():
            raise ValueError(f"source preparation not observed: {expected}")
    if "kernel/Makefile COPYING" not in provider_log.read_text():
        raise ValueError("provider source install not observed")
    reference = {
        "status": "PATCH_INCLUDED",
        "new_qb_source_commit": fix,
        "old_qb_source_commit": old_commit,
        "new_qb_commit_matches_phase10": True,
        "phase10": {"summary":os.path.relpath(history_path, ROOT), "summary_sha256":digest(history_path),
                    "remote_branch": history["branch_ref"], "branch_url": history["gerrit_pages"]["branch"]["url"],
                    "change_id":history["gerrit_change_id"],"commit_url":history["gerrit_pages"]["commit"]["url"],
                    "archived_remote_verification": history["status"],
                    "current_read_only_query": "evidence/source/phase10-git-sandbox-head.cmd.json",
                    "commit_object_output": "evidence/source/phase10-git-fix-object.out"},
        "manifests": {key:{"path": os.path.relpath(path, ROOT), "sha256":digest(path), "revisions":revisions[key]}
                      for key,path in manifest_paths.items()},
        "source_provider_rpms": provider_headers, "source_rpms": source_info,
        "source_makefiles":{key:{name:{"path":rel(SRC/key/name),"sha256":payload_sha256[key][name]}
                          for name in ("Makefile","kdbus/Makefile")} for key in payloads},
        "source_payload_member_comparison":{"changed_members":differing_members,"valid_source_patch":"11B_SOURCE_DIFF.patch"},
        "source_recipe_scans":scans,
        "wrap_build_preparation":{"log":rel(log),"sha256":digest(log),"lines":[370, 396, 397, 402, 460],
                                  "original_live_build_directory_recovered":False},
        "provider_build_preparation":{"log":rel(provider_log),"sha256":digest(provider_log),"lines":[634,766,767]},
    }
    store(ROOT/"11B_SOURCE_PROVENANCE.json", reference)
    print(json.dumps({"status":reference["status"], "verified_source_member_counts":
          {key: len(value) for key,value in payloads.items()},"changed_source_members":differing_members},indent=2))


def evidence(path):
    return {"path": rel(path), "sha256": digest(path)}


def verified_repo_xml(parent, compressed, kind):
    node = next(x for x in ET.parse(parent).getroot().findall("{*}data") if x.get("type") == kind)
    stored = compressed.read_bytes()
    opened = gzip.decompress(stored)
    for name, content in (("checksum", stored), ("open-checksum", opened)):
        check = node.find("{*}"+name)
        if hashlib.new(check.get("type"), content).hexdigest() != check.text:
            raise ValueError(f"{compressed} {name} mismatch")
    return ET.fromstring(opened)


def area_scan():
    base = BUILD/"base"
    repos = {
        "base_packages": (base/"repomd.out", base/"filelists.xml.gz"),
        "unified_packages": (REPO/"packages-repomd.out", REPO/"packages-filelists.out"),
        "unified_debug": (REPO/"debug-repomd.out", REPO/"debug-filelists.out"),
    }
    exact = {x["name"]:x for x in json.loads((base/"matched-metadata.json").read_text())["packages"]}
    filelists = {}
    for area,(parent,compressed) in repos.items():
        root = verified_repo_xml(parent, compressed, "filelists")
        result = {"filelists":evidence(compressed), "sdk_or_intermediate": [], "linker_paths":[]}
        for package in root.findall("{*}package"):
            if package.get("arch") not in {"armv7l", "noarch"}:
                continue
            filepath = [x.text for x in package.findall("{*}file") if x.text]
            details = {**package.attrib, "version":package.find("{*}version").attrib}
            linker = [x for x in filepath if Path(x).name in {"ld.lld", "ld.bfd", "ld"}]
            command = [x for x in filepath if Path(x).name in {".kdbus.o.cmd", ".kdbus.ko.cmd", "kdbus.o"}]
            if linker:
                result["linker_paths"].append({**details, "paths":linker})
            if command:
                result["sdk_or_intermediate"].append({**details, "paths":command})
            if area=="base_packages" and package.get("name") in exact:
                metadata = exact[package.get("name")]
                if package.get("pkgid") != metadata["sha256"]:
                    raise ValueError(f"Base primary and filelists rpm digest mismatch {details}")
        filelists[area] = result
    store(base/"repository-filelists-linker-paths.json",filelists)

    base_primary = verified_repo_xml(base/"repomd.out",base/"primary.xml.gz","primary")
    unified_primary = verified_repo_xml(REPO/"packages-repomd.out",REPO/"packages-primary.out","primary")
    package_names = set(exact)
    competition = {}
    for scope,root in (("base",base_primary),("unified",unified_primary)):
        relevant = [p for p in root.findall("{*}package")
                    if p.findtext("{*}name") in package_names and p.findtext("{*}arch") in {"armv7l","noarch"}]
        competition[scope] = [{"name":p.findtext("{*}name"),"arch":p.findtext("{*}arch"),
                               "version":p.find("{*}version").attrib,"sha256":p.findtext("{*}checksum"),
                               "href":p.find("{*}location").get("href")} for p in relevant]
    if set(entry["name"] for entry in competition["base"]) != package_names:
        raise ValueError("selected Base package names could not all be verified")
    for entry in competition["unified"]:
        select = exact[entry["name"]]
        if all(entry["version"][key]==select["version"][key] for key in ("epoch","ver","rel")) and (
                entry["sha256"]!=select["sha256"]):
            raise ValueError(f"same toolchain NEVRA has competing bytes: {entry}")
    store(base/"toolchain-primary-package-candidates.json",competition)
    return filelists


def build_verify():
    base = BUILD/"base"
    toolkit = json.loads((base/"linker-payload-identities.json").read_text())
    filelists = area_scan()
    if any(item["sdk_or_intermediate"] for item in filelists.values()):
        raise ValueError("Intermediate artifacts found in public filelists")
    log = BUILD/"linux-tizen-modules-armv7l.out"
    archived = log.read_text().splitlines()
    old_log = ARCHIVE/"evidence/build/linux-tizen-modules-armv7l.out"
    log_url = ("https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/"
               "tizen-unified-toolchain_20261125.130358/builddata/buildlogs/standard/armv7l/succeeded/"
               "linux-tizen-modules.buildlog.txt")
    declarations = {2:"Using BUILD_ROOT=", 6:'started "build linux-tizen-modules.spec"', 10:"tizen-base-toolchain_20261030.120529",
                    298:"keeping clang-accel-x86_64-armv7l-0.4-2.3",314:"keeping make-4.4.1-1.14",
                    331:"keeping binutils-2.43-1.16",341:"keeping qemu-accel-x86_64-armv7l-0.4-2.3",
                    360:"keeping llvm-22.1.8-4.1",362:"keeping clang-22.1.8-4.1",
                    370:"linux-tizen-modules-source-11.0.0-0 ",378:"arm-rpi4-linux-kernel-devel-6.12.80-0 ",
                    402:"cp -a /usr/src/linux-tizen-modules-source ./kernel",427:"export CC=armv7l",
                    430:"export 'MAKEFLAGS+= -k'",448:"export BUILD_kdbus=m",458:"export LLVM=1",
                    460:"sed -i s/-Wno-error=missing-attributes//g",467:"make -C kernel KERNELDIR=",
                    469:"CFLAGS_MODULE=",505:"LD [M]  /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/kernel/kdbus/kdbus.o",
                    511:"MODPOST ",528:"kdbus.mod.o",529:"kdbus.ko",530:"BTF [M]",550:"INSTALL ",
                    551:"STRIP ",557:"kernel-devel-arm-rpi4-rt",746:"linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm",
                    760:'finished "build linux-tizen-modules.spec"'}
    for index,marker in declarations.items():
        if marker not in archived[index-1]:
            raise ValueError(f"Expected build marker {marker!r} changed at line {index}: {archived[index-1]}")
    observed = {str(index):archived[index-1] for index in declarations}
    (BUILD/"new-wrapper-observed-excerpt.out").write_text("".join(f"{num}: {line}\n" for num,line in observed.items()))
    sdk = REPO/"sdk/boot/kernel/devel/kernel-devel-arm-rpi4"
    sdk_rpm = REPO/"rpms/arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm"
    sdk_metadata = metadata_rpm("packages", sdk_rpm.name)
    verify_rpm(sdk_rpm,sdk_metadata)
    sdk_files = ("Makefile","scripts/Kbuild.include","scripts/Makefile.build","scripts/Makefile.modfinal",
                 "scripts/Makefile.lib", "scripts/Makefile.compiler","scripts/Makefile.clang","arch/arm/Makefile",
                 "include/config/auto.conf",".config","include/generated/utsrelease.h")
    dsp = lines(BUILD/"sdk-rules-rpm-dump",["rpm","-qp","--dump",sdk_rpm])
    header_digests = {row.split()[0]:row.split()[3] for row in dsp}
    for name in sdk_files:
        embedded = "/boot/kernel/devel/kernel-devel-arm-rpi4/"+name
        if digest(sdk/name) != header_digests[embedded]:
            raise ValueError(f"SDK CPIO bytes differ from devel RPM header for {name}")
    bypass_scan = lines(BUILD/"new-sdk-ld-bypass-scan",
                        ["rg","--no-filename","-n",
                         r"^[[:space:]]*(override[[:space:]]+|export[[:space:]]+|private[[:space:]]+)*(LD|PATH)[[:space:]]*[:+?!]?=|\bld\.bfd\b|\b-fuse-ld=",
                         *(sdk/name for name in sdk_files if name.endswith("Makefile") or name.startswith("scripts/"))])
    if [row.split()[0] for row in bypass_scan] != ["480:LD","489:LD"]:
        raise ValueError(f"unexpected SDK assignment or bypass candidates: {bypass_scan}")
    direct_checks = {}
    for name in ("direct-evidence-corrected-log-search","direct-evidence-builder-path-stat"):
        receipt = json.loads((BUILD/(name+".cmd.json")).read_text())
        if receipt["exit_status"] != 1:
            raise ValueError(f"Direct evidence search result changed: {receipt}")
        direct_checks[name] = {**evidence(BUILD/(name+".cmd.json")),"exit_status":receipt["exit_status"],
                               "stdout":evidence(BUILD/(name+".out")),"stderr":evidence(BUILD/(name+".err"))}
    profile = BUILD/"profiling-armv7l-default-index.out"
    if "buildtime.json" not in profile.read_text():
        raise ValueError("expected archived profiling index missing")
    sdk_out = lines(BUILD/"new-sdk-linker-configuration",
                    ["rg","-n","^CONFIG_(CC_VERSION_TEXT|CC_IS_CLANG|AS_IS_LLVM|LD_IS_LLD|LLD_VERSION|LTO_NONE)=",
                     sdk/".config"])
    if not any("CONFIG_LD_IS_LLD=y" in line for line in sdk_out) or not any(
            "CONFIG_LLD_VERSION=220108" in line for line in sdk_out):
        raise ValueError("new SDK Kconfig does not select LLD 22.1.8")

    results_rpm = REPO/"rpms/linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm"
    results_metadata = metadata_rpm("packages", results_rpm.name)
    verify_rpm(results_rpm,results_metadata)
    member = "/lib/modules/6.12.80-arm-rpi4-v7l/extra/kdbus/kdbus.ko"
    module_entry = next(row.split() for row in lines(BUILD/"new-wrapper-rpm-dump",
                        ["rpm","-qp","--dump",results_rpm]) if row.startswith(member+" "))
    extracted_ko = ROOT/"evidence/binary/modules/new"/member.lstrip("/")
    if not extracted_ko.is_file():
        extract(results_rpm, ["."+member], BUILD/"released-module", BUILD/"new-wrapper-kdbus-extract")
        extracted_ko = BUILD/"released-module"/member.lstrip("/")
    if module_entry[3] != digest(extracted_ko) or int(module_entry[1]) != extracted_ko.stat().st_size:
        raise ValueError("released kdbus payload does not match RPM member digest")
    released = {"rpm":evidence(results_rpm),"metadata":results_metadata,"path_in_rpm":member,
                "module":evidence(extracted_ko),"rpm_file_digest_verified":True,
                "rpm_member_size_bytes":int(module_entry[1]),"rpm_member_mtime_utc":
                datetime.datetime.fromtimestamp(int(module_entry[2]),datetime.timezone.utc).isoformat(),
                "observed_install_log_line":550,"observed_strip_log_line":551,"observed_rpm_log_line":746}

    store(ROOT/"11C_INTERMEDIATE_LINK_COMMANDS.json", {
        "status":"HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE","e4_established":False,
        "target":"kdbus/kdbus.o","architecture":"ARMv7l","variant":"RPi4 non-RT",
        "actual_command":None,"actual_argv":None,"actual_executable_path":None,"actual_executable_sha256":None,
        "actual_linker_rpm_nevra":None,"actual_execve_success_record":None,"original_cmd_file":None,
        "historical_intermediate_elf":None,"historical_path_snapshot":None,
        "quiet_success_log":{"url":log_url,**evidence(log),"observed_lines":observed,
                             "target_line":505,"run_subsequent_final_link_line":529,"next_rt_block_line":557},
        "builder_path":{"observed_at_log_line":2,"available_locally":False},
        "public_archive_indexes":[evidence(BUILD/name) for name in ("builddata-index.out",
            "armv7l-succeeded-index.out","profiling-armv7l-default-index.out")],
        "checks":direct_checks,"package_filelists":evidence(base/"repository-filelists-linker-paths.json"),
        "actual_linker_candidates_not_execution_records":toolkit["candidates"],
        "linked_released_module":released,
    })
    variable_trace = {
        "LLVM":{"observed":"1","scope":"exported by wrapper SPEC to both recorded non-RT make levels","log_lines":[458,459],
                "kbuild":"Makefile:425–437 and 477–496","inference":"non-empty LLVM, no LLVM_PREFIX or LLVM_SUFFIX derived from 1"},
        "LD":{"observed":None,"command_line_ld_override_observed":False,"assignment":"$(LLVM_PREFIX)ld.lld$(LLVM_SUFFIX)",
              "kbuild":"Makefile:480,593","effective_inferred":"ld.lld","external_override_deleted":True},
        "CC":{"observed_in_rpm_shell":"armv7l-tizen-linux-gnueabi-clang","log_lines":[427,428],
              "kbuild":"Makefile:479","effective_inferred":"clang","actual_executable_path_observed":False},
        "CROSS_COMPILE":{"observed":None,"kbuild":"Makefile:489,593 and scripts/Makefile.clang",
                         "inference":"can affect target flags, but cannot choose $(CROSS_COMPILE)ld in LLVM=1 branch"},
        "MAKEFLAGS":{"observed_append":"-k","log_lines":[430,431],"kbuild":"Makefile:49 adds -rR",
                     "complete_historical_value_available":False},
        "PATH":{"observed":None,"linker_candidate_rpms":evidence(base/"linker-payload-identities.json"),
                "filelist_coverage":evidence(base/"repository-filelists-linker-paths.json"),
                "inference":"available root/linker package candidates with the selected basename are LLVM LLD"},
    }
    rules = [
        ("01-source","source/prep","provider SPEC:2,32–50; wrapper SPEC:156–159","./kernel copied from the verified source-provider RPM","370,402"),
        ("02-spec","LLVM mode","wrapper SPEC:245–268","export LLVM=1 and BUILD_kdbus=m; no LD argument","448,458–469"),
        ("03-top","linker selection/export","SDK Makefile:425–437,477–496,593","LD=ld.lld via LLVM branch; exported for sub-makes","458–469"),
        ("04-external","external routing","SDK Makefile:133–134,1815,1953–1955; Kbuild.include:65,113; Makefile.build:39–42",
         "M selects verified external directory, includes Makefile without LD override","467,469"),
        ("05-composite","non-RT kdbus.o","external kdbus/Makefile:1–22; SDK Makefile.lib:56–62,257; Makefile.build:432–444",
         "cmd_ld_multi_m = $(LD) $(ld_flags) -r -o $@ @$< $(cmd_objtool)","505"),
        ("06-modpost","module postprocess","SDK Makefile:1880–1889,1904–1907","modules depends on modpost before modfinal","511"),
        ("07-final","non-RT kdbus.ko","SDK Makefile:1886–1889; Makefile.modfinal:36–40,60–64",
         "separate submake uses exported LD for -r -T scripts/module.lds","528–530"),
        ("08-release","module packaging","wrapper SPEC:268 and %files; checksum-verified release RPM",
         "install+strip and released kdbus.ko member digest","550–551,746,760"),
    ]
    with (ROOT/"11D_LINKER_RULE_MATRIX.csv").open("w",newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("step","target_or_operation","source_rule","selection_or_effect","observed_wrapper_log_lines"))
        writer.writerows(rules)
    applies = {"linker":"LLVM LLD","version":"22.1.8","selected_command_name":"ld.lld","evidence_level":"E3",
               "historical_executable_path_observed":False}
    store(ROOT/"11D_LINKER_VARIABLE_TRACE.json", {
        "status":"E3_ENGINEERING_VERIFIED","evidence_level":"E3","variant":"RPi4 ARMv7l non-RT",
        "new_qb":"tizen-unified-toolchain_20261125.130358",
        "intermediate":{"target":"kdbus/kdbus.o","observed_log_line":505,**applies},
        "final":{"target":"kdbus/kdbus.ko","observed_log_line":529,**applies},
        "original_ld_override":"REMOVED","bfd_bypass_risk":"NO_REASONABLE_BFD_PATH_IDENTIFIED",
        "historical_resolution_limit":"PATH, resolved executable, original .cmd and execve unavailable",
        "old_qb":{"intermediate_status":"BFD_PATH_POSSIBLE","log":
                  {"path":os.path.relpath(old_log,ROOT),"sha256":digest(old_log)}},
        "source_provenance":evidence(ROOT/"11B_SOURCE_PROVENANCE.json"),
        "actual_matched_sdk":{"rpm":evidence(sdk_rpm),"metadata":sdk_metadata,
                              "verified_rules":{name:evidence(sdk/name) for name in sdk_files}},
        "sdk_config_lines":sdk_out,"sdk_ld_bypass_scan":evidence(BUILD/"new-sdk-ld-bypass-scan.out"),
        "variables":variable_trace,
        "successful_external_log":{"url":log_url,**evidence(log),"observed_lines":observed},
        "rules":evidence(ROOT/"11D_LINKER_RULE_MATRIX.csv"),"released_module":released,
        "toolchain":{"payloads":toolkit["candidates"],
                     "package_competition":evidence(base/"toolchain-primary-package-candidates.json"),
                     "filelists":evidence(base/"repository-filelists-linker-paths.json")},
    })
    print(json.dumps({"status":"E3_ENGINEERING_VERIFIED","level":"E3",
         "historical_direct_execution_observed":False,"release_module_sha256":digest(extracted_ko)},indent=2))


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("check", choices=("linkers", "source", "build"))
    operation = cli.parse_args().check
    {"linkers": tool_verify, "source": source_verify, "build": build_verify}[operation]()
