#!/usr/bin/env python3
"""Read only scoped source files and inventories from the sealed Phase 1 RPM inputs."""
from collections import defaultdict
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile

DEVEL = PurePosixPath('boot/kernel/devel/kernel-devel-arm-rpi4')
RPM = 'arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l'
SRPM = 'rpi4-linux-kernel-6.12.80-0.src.rpm'
SNAPSHOT = 'tizen-unified-toolchain_20261120.082536'
REVISION = '42aeefac58edeb081aff440f0b60be71cbe49755'

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def header(infile):
    head = infile.read(110)
    if len(head) != 110 or head[:6] not in (b'070701', b'070702'):
        raise ValueError('invalid cpio newc header')
    size = int(head[54:62],16)
    namesize = int(head[94:102],16)
    name = PurePosixPath(infile.read(namesize).decode().rstrip('\0'))
    if name.is_absolute() or '..' in name.parts:
        raise ValueError(f'unsafe archive member {name}')
    padding = (-110-namesize)%4
    infile.read(padding)
    return name, size, int(head[14:22],16)

def store_exact(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

def scan_devel(base, out, parents, include_dirs, exact):
    payload = base/f'evidence/kernel_binary/payload/{RPM}/rpm2cpio.out'
    results = []
    tracked_postlink = []
    touched_member_count = 0
    with payload.open('rb') as file:
        while True:
            p, size, mode = header(file)
            if str(p)=='TRAILER!!!':
                break
            start = file.tell()
            if p.is_relative_to(DEVEL):
                rel = p.relative_to(DEVEL)
                text = str(rel)
                rules = rel.name in ('Kbuild','Makefile') and (rel.parent in parents or rel.parent in include_dirs)
                if rel.name == 'Makefile.postlink' and rel.parent == PurePosixPath('arch/arm'):
                    tracked_postlink.append(text)
                if (text in exact or rules) and (mode & 0o170000)==0o100000:
                    data = file.read(size)
                    dest = out/'source'/text
                    store_exact(dest,data)
                    results.append(dict(file='source/'+text, rpm_member='/'+str(p), size=size,
                                        sha256=hashlib.sha256(data).hexdigest(), cpio_offset=start))
                touched_member_count += 1
            file.seek(start+size+(-size)%4)
    return dict(payload=str(payload.relative_to(base)), scope_member_count=touched_member_count,
                arm_postlink=tracked_postlink, members=sorted(results,key=lambda item:item['file']))

def is_prebuilt(path):
    return bool(re.search(r'(?:\.o|\.a|\.so(?:\.\d+)*|\.ko(?:\.(?:zst|xz|gz))?|\.obj|\.rlib|\.o_shipped|\.a_shipped|\.ko_shipped)$',path))

def scan_srpm(base,out,scratch,parents):
    pkg = base/'evidence/repository/rpms'/SRPM
    proc = subprocess.Popen(['rpm2cpio',str(pkg)],stdout=subprocess.PIPE)
    tar_path = scratch/'linux-kernel-6.12.80.tar.xz'
    all_members, patches, matched_spec_members = [], [], []
    handle = proc.stdout
    while True:
        p, size, mode = header(handle)
        if str(p)=='TRAILER!!!':
            break
        all_members.append(str(p))
        remaining = size
        if p.name == tar_path.name:
            with tar_path.open('wb') as target:
                while remaining:
                    block = handle.read(min(remaining,1024*1024))
                    if not block:
                        raise IOError('short SRPM stream')
                    target.write(block)
                    remaining -= len(block)
        else:
            content = handle.read(size)
            if len(content)!=size:
                raise IOError('short SRPM stream')
            remaining = 0
            if p.name in ('linux-rpi.spec','linux-rpi.manifest'):
                previously_extracted = out/'source/spec'/p.name
                if previously_extracted.read_bytes()!=content:
                    raise ValueError(f'Archived SPEC/manifest copy differs from exact SRPM member {p.name}')
                matched_spec_members.append(dict(member=p.name,file='source/spec/'+p.name,
                                                  sha256=hashlib.sha256(content).hexdigest()))
            if '.patch' in p.name or '.diff' in p.name:
                decoded = gzip.decompress(content) if p.suffix=='.gz' else content
                entries = []
                for line in decoded.decode(errors='replace').splitlines():
                    if line.startswith('diff --git ') or line.startswith(('--- a/','+++ b/')):
                        paths = re.findall(r'\b[ab]/([^\s]+)',line)
                        entries.extend(paths)
                bin_diff = [line for line in decoded.decode(errors='replace').splitlines()
                            if line.startswith(('GIT binary patch','Binary files '))]
                changed = sorted(set(entries))
                patches.append(dict(file=p.name, sha256=hashlib.sha256(content).hexdigest(),
                                    changed_paths=changed,
                                    potentially_prebuilt_scoped=[x for x in changed if is_prebuilt(x) and PurePosixPath(x).parent in parents],
                                    binary_diff_marker_count=len(bin_diff)))
        handle.read((-size)%4)
    handle.read()
    if proc.wait():
        raise ValueError('rpm2cpio failed')
    if not tar_path.is_file():
        raise ValueError('target source archive not found')
    prebuilt, scoped_members, total = [], [], 0
    with tarfile.open(tar_path,'r|xz') as archive:
        for member in archive:
            total += 1
            path = PurePosixPath(member.name)
            if len(path.parts)<2:
                continue
            rootpath = PurePosixPath(*path.parts[1:])
            if rootpath.parent in parents and (member.isfile() or member.islnk() or member.issym()):
                posix = rootpath.as_posix()
                scoped_members.append(posix)
                if is_prebuilt(posix):
                    prebuilt.append(posix)
    (out/'raw-source-scoped-member-list.txt').write_text('\n'.join(sorted(scoped_members))+'\n')
    return dict(rpm=str(pkg.relative_to(base)), rpm_sha256=digest(pkg), member_list=all_members,
                tar_member=tar_path.name, tar_sha256=digest(tar_path),
                tar_members_examined=total, scope_regular_members=len(scoped_members), srpm_spec_members=matched_spec_members,
                prebuilt_scoped=prebuilt, patches=patches)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase1',type=Path)
    parser.add_argument('out',type=Path)
    parser.add_argument('scratch',type=Path)
    args = parser.parse_args()
    base, out, scratch = args.phase1.resolve(), args.out.resolve(), args.scratch.resolve()
    out.mkdir(parents=True,exist_ok=True)
    scratch.mkdir(parents=True,exist_ok=True)
    module_evidence = json.loads((base/'evidence/build/module-final-commands.json').read_text())['quiet_link_observations']
    targets = [PurePosixPath(row['build_output']) for row in module_evidence if row['package_rpm'].startswith('arm-rpi4-linux-kernel-modules')]
    assert len(set(targets))==len(targets)==52
    parents = {p for value in targets for p in value.parents}
    include_dirs = {PurePosixPath('arch/arm/boot'),PurePosixPath('arch/arm'),PurePosixPath('arch/arm/boot/compressed')}
    core_files = ['Makefile','.config','include/config/auto.conf','include/generated/compile.h',
                  'include/generated/utsrelease.h','include/generated/utsversion.h',
                  'scripts/Makefile.vmlinux','scripts/link-vmlinux.sh','scripts/Makefile.vmlinux_o',
                  'scripts/Makefile.modfinal','scripts/Makefile.modinst','scripts/Makefile.lib',
                  'scripts/Makefile.build','scripts/Makefile.clang','scripts/Makefile.compiler','scripts/Makefile.modpost',
                  'scripts/Kbuild.include','scripts/Kconfig.include','scripts/ld-version.sh','scripts/cc-version.sh','init/Kconfig']
    devel = scan_devel(base,out,parents,include_dirs,set(core_files))
    indexed = {m['file'] for m in devel['members']}
    assert all('source/'+f in indexed for f in core_files)
    for filename in ('linux-rpi.spec','linux-rpi.manifest'):
        src = base/'evidence/build/source'/filename
        store_exact(out/'source/spec'/filename,src.read_bytes())
    srpm = scan_srpm(base,out,scratch,parents)
    report = dict(snapshot=SNAPSHOT, vcs_revision=REVISION, target='arm-rpi4 non-RT',
                  target_relative_build_outputs=sorted(map(str,targets)),
                  directory_scope=sorted(map(str,parents)), devel=devel, srpm=srpm)
    (out/'kernel-source-binding.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"Kernel source scan: {len(devel['members'])} matching devel files, {srpm['tar_members_examined']} tar members and {len(srpm['patches'])} SRPM patches.")
    print(f"Scoped potentially prebuilt archive members: {len(srpm['prebuilt_scoped'])}.")
    print(f"Scoped potentially prebuilt paths in patches: {sum(len(x['potentially_prebuilt_scoped']) for x in srpm['patches'])}.")

if __name__=='__main__':
    main()
