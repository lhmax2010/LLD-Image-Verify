#!/usr/bin/env python3
"""Reconstruct and validate Phase 1 evidence captured from the specified SDB device."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import PurePosixPath
import re
import struct
import tarfile

from record import ROOT

EVIDENCE = ROOT / 'evidence/runtime'
SHA_PATTERN = re.compile(r'[0-9a-f]{64}')
HEX_DUMP = re.compile(r'(?:\s+[0-9a-f]{2})+\s*')
MODULE_SUFFIX = re.compile(r'\.ko(?:\.(?:gz|xz|zst))?$')
RPM_KEYS = ('name', 'epoch', 'version', 'release', 'architecture', 'source_rpm', 'build_time_epoch', 'install_time_epoch')


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def lines(stem):
    return (EVIDENCE / f'{stem}.out').read_text().splitlines()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def note_records(raw):
    """Parse Linux ELF notes framing. The live ARMv7l platform is little endian."""
    notes = []
    offset = 0
    while offset < len(raw):
        require(offset + 12 <= len(raw), f'truncated note header at {offset}')
        name_size, desc_size, kind = struct.unpack_from('<III', raw, offset)
        name_offset = offset + 12
        desc_offset = name_offset + ((name_size + 3) & ~3)
        end = desc_offset + ((desc_size + 3) & ~3)
        require(end <= len(raw), f'truncated note contents at {offset}')
        name = raw[name_offset:name_offset + name_size].rstrip(b'\0')
        desc = raw[desc_offset:desc_offset + desc_size]
        notes.append(dict(offset=offset, type=kind, owner=name.decode('ascii'), description_hex=desc.hex()))
        offset = end
    return notes


def hex_bytes(records):
    return bytes.fromhex(' '.join(line for line in records if HEX_DUMP.fullmatch(line)))


def build_ids(notes):
    return [row['description_hex'] for row in notes if row['type'] == 3 and row['owner'] == 'GNU']


def kernel_notes():
    raw = lines('notes')
    data = hex_bytes(raw)
    expected = raw[0].split()[0]
    require(SHA_PATTERN.fullmatch(expected) and expected == sha256(data), '/sys/kernel/notes SHA256 mismatch')
    notes = note_records(data)
    (EVIDENCE / 'kernel-notes.bin').write_bytes(data)
    return dict(gnu_build_id=build_ids(notes)[0], size_bytes=len(data), sha256=expected, notes=notes,
                evidence_path='evidence/runtime/notes.out', bytes_path='evidence/runtime/kernel-notes.bin')


def rpm_record(line):
    fields = line.split('|')
    require(len(fields) == len(RPM_KEYS), f'invalid RPM record: {line}')
    row = dict(zip(RPM_KEYS, fields))
    for key in ('build_time_epoch', 'install_time_epoch'):
        row[key] = int(row[key])
    return row


def installed_inventory(release):
    canonical = f'/usr/lib/modules/{release}'
    alternate = f'/lib/modules/{release}'
    rows = {}
    capture = lines('module-files')
    require('FIND_EXIT\t0' in capture, 'module file inventory find failed')
    for line in capture:
        if not line.startswith('FILE\t'):
            continue
        _, path, file_type, *data = line.split('\t')
        require(path.startswith(canonical + '/') and path not in rows, f'invalid or duplicate path: {path}')
        row = dict(path=path, alias_paths=[alternate + path[len(canonical):]], type=file_type,
                   sha256=None, size_bytes=None, device_id=None, inode=None, symlink_target=None,
                   rpm_owners=[], rpm_owner_attempts=[])
        if file_type == 'regular':
            require(len(data) == 3, f'incomplete hash record: {path}')
            stat, hash_status, digest = data
            require(hash_status == '0' and SHA_PATTERN.fullmatch(digest), f'device hash failed: {path}')
            row['device_id'], row['inode'], row['size_bytes'] = map(int, stat.split(':'))
            row['sha256'] = digest
        elif file_type == 'symlink':
            row['symlink_target'] = data[0]
        rows[path] = row

    for stem, physical in (('find-direct', canonical), ('alias-find', alternate)):
        find = lines(stem)
        found = {canonical + line[len(physical):] for line in find if line.startswith(physical + '/')}
        require('[FIND_EXIT=0]' in find and found == set(rows), f'{stem} did not match module inventory')

    query = lines('module-owners')
    require('FIND_EXIT\t0' in query, 'module ownership inventory find failed')
    path = None
    attempt = None
    for line in query:
        if line.startswith('OWNER\t'):
            _, path, filename, rc = line.split('\t')
            attempt = dict(path=filename, exit_status=int(rc), output=[])
            rows[path]['rpm_owner_attempts'].append(attempt)
        elif attempt is not None and line:
            attempt['output'].append(line)
            if attempt['exit_status'] == 0:
                rows[path]['rpm_owners'].append(rpm_record(line))
    for row in rows.values():
        require(row['rpm_owner_attempts'], f'missing ownership result for {row["path"]}')
    return rows


def validate_archive(release, rows):
    raw = lines('module-archive-base64')
    require(raw[-1] == '[BASE64_EXIT=0]', 'device stream failed')
    compressed = base64.b64decode(''.join(raw[:-1]), validate=True)
    archive = EVIDENCE / 'installed-modules.tar.gz'
    archive.write_bytes(compressed)
    tar_index = set()
    with tarfile.open(archive, 'r:gz') as the_tar:
        for member in the_tar:
            rel = PurePosixPath(member.name)
            require(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] == release,
                    f'invalid archive member: {member.name}')
            if not MODULE_SUFFIX.search(rel.name):
                continue
            path = '/usr/lib/modules/' + str(rel)
            require(path in rows and path not in tar_index, f'unexpected or duplicate tar path: {path}')
            tar_index.add(path)
            row = rows[path]
            if member.issym():
                require(row['type'] == 'symlink' and row['symlink_target'] == member.linkname,
                        f'archive symlink mismatch: {path}')
                continue
            require(row['type'] == 'regular' and member.isfile(), f'archive type mismatch: {path}')
            with the_tar.extractfile(member) as handle:
                content = handle.read()
            require(len(content) == row['size_bytes'] and sha256(content) == row['sha256'],
                    f'archive size or SHA256 mismatch: {path}')
            output = EVIDENCE / 'installed-files' / path.removeprefix('/')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            row['local_file'] = str(output.relative_to(ROOT))
    require(tar_index == set(rows), 'archive misses installed module paths')
    return dict(path=str(archive.relative_to(ROOT)), size_bytes=len(compressed), sha256=sha256(compressed),
                members_checked=len(tar_index), transport_sha256_check='PASS')


def make_loaded():
    snapshot = lines('loaded-list')
    require(snapshot[-1] == '[PROC_MODULES_EXIT=0]', 'cat /proc/modules failed')
    modules = {}
    for line in snapshot[:-1]:
        name, size, use, dependencies, state, address, *taint = line.split()
        require(name not in modules, f'duplicate live module: {name}')
        modules[name] = dict(name=name, size=int(size), use_count=int(use), dependencies=dependencies,
                             state=state, address=address, taint=' '.join(taint), raw_line=line)
    notes_by_module = {}
    for line in lines('loaded-build-ids'):
        match = re.fullmatch(r'\[MODULE=(.*)\]', line)
        if match:
            name = match[1]
            notes_by_module[name] = []
        else:
            notes_by_module[name].append(line)
    require(set(notes_by_module) == set(modules), 'runtime note probe paths differ from loaded list')
    for name, row in modules.items():
        records = notes_by_module[name]
        data = hex_bytes(records)
        if data:
            actual = sha256(data)
            expected = records[0].split()[0]
            require(SHA_PATTERN.fullmatch(expected) and expected == actual, f'sysfs module note checksum mismatch: {name}')
            parsed = build_ids(note_records(data))
            row['build_id'] = parsed[0] if parsed else None
            row['build_id_note_sha256'] = actual
        else:
            row['build_id'] = None
        row['srcversion'] = next((line.removeprefix('[SRCVERSION] ') for line in records if line.startswith('[SRCVERSION] ')), None)
        row['notes_path'] = f'/sys/module/{name}/notes/.note.gnu.build-id'
    return list(modules.values())


def main():
    uname, release, arch, proc_version, *system = lines('banner')
    build = re.fullmatch(r'Linux version (\S+) \((.+?)\) \(clang version ([^,]+), LLD ([^)]+)\) #1 SMP (.+)', proc_version)
    require(build is not None and build[1] == release, 'runtime banner kernel-release mismatch')
    build_id = next(line.split('=', 1)[1].strip('"') for line in system if line.startswith('BUILD_ID='))
    boot_line = next(line for line in system if 'Linux version ' in line)
    require(proc_version in boot_line, 'boot banner differs from /proc/version')
    rows = installed_inventory(release)
    archive = validate_archive(release, rows)
    by_type = Counter(row['type'] for row in rows.values())
    modules = dict(kernel_release=release, device_serial='private-address-02:26101',
                   physical_root=f'/usr/lib/modules/{release}', alias_root=f'/lib/modules/{release}',
                   total_unique_paths=len(rows), file_type_counts=dict(by_type),
                   rpm_owned_files=sum(bool(row['rpm_owners']) for row in rows.values()),
                   archive=archive, files=[rows[path] for path in sorted(rows)])
    write_json(EVIDENCE / 'installed-modules.json', modules)

    initial = [line.split()[0] for line in lines('loaded') if ' Live ' in line]
    current = make_loaded()
    lsmod = lines('lsmod')
    require(lsmod[-1] == '[LSMOD_EXIT=0]', 'lsmod failed')
    lsmod_names = [line.split()[0] for line in lsmod[1:-1]]
    loaded = dict(snapshot_path='evidence/runtime/loaded-list.out',
                  sysfs_note_path='evidence/runtime/loaded-build-ids.out',
                  initial_snapshot_path='evidence/runtime/loaded.out', initial_snapshot_names=initial,
                  lsmod_snapshot_path='evidence/runtime/lsmod.out', lsmod_snapshot_names=lsmod_names,
                  total=len(current), modules=current)
    write_json(EVIDENCE / 'loaded-modules.json', loaded)
    kernel_id = kernel_notes()
    ip_capture = '\n'.join(lines('ip-fallback'))
    require(re.search(r'\b192\.168\.108\.13\b', ip_capture), 'target IP was not observed inside the authorized device')
    model = lines('boot-dtb')[1]
    require(model.startswith('Raspberry Pi 4 Model B'), 'device-tree model is outside the RPi4 target scope')

    all_rpm = lines('rpm-list')
    require(all_rpm[-1] == '[RPM EXIT 0]', 'rpm -qa failed on device')
    rpm_records = [rpm_record(line) for line in all_rpm[:-1] if line]
    relevant = re.compile(r'kernel|rpi4|^(?:proc-tsm|kdbus|dm-bow|extcon-usb-fixed|inform-reboot|zlogger)(?:$|[.-])', re.I)
    package_candidates = [row for row in rpm_records if any(relevant.search(row[key])
                          for key in ('name', 'source_rpm'))]
    require(not package_candidates, 'newly observed installed RPM candidates require manual review')

    pinned_query = lines('pinned-rpm-device-queries')
    pinned_names = [line.removeprefix('[PACKAGE=').removesuffix(']') for line in pinned_query
                    if line.startswith('[PACKAGE=')]
    require(pinned_names and all(f'package {name} is not installed' in pinned_query for name in pinned_names),
            'pinned device package query requires manual review')

    result = dict(status='PASS', status_scope='live device and recorded toolchain metadata',
                  device=dict(ip='private-address-02', serial='private-address-02:26101', authorized_sdb=True,
                              ip_evidence_path='evidence/runtime/ip-fallback.out',
                              model=model, model_evidence_path='evidence/runtime/boot-dtb.out',
                              image_build_id=build_id),
                  kernel=dict(is_running=True, uname=uname, release=release, architecture=arch, proc_version=proc_version,
                              boot_banner=boot_line, compiler='Clang', clang_version=build[3], linker='LLD', lld_version=build[4],
                              build_timestamp=build[5], build_user_and_host=build[2], toolchain_evidence='recorded build metadata',
                              final_link_verified=False, notes=kernel_id,
                              banner_evidence_path='evidence/runtime/banner.out'),
                  runtime_config=dict(available=False, paths=[f'/boot/config-{release}', '/proc/config.gz'],
                                      evidence_path='evidence/runtime/files.out'),
                  installed_kernel_rpm=dict(status='UNVERIFIABLE', active_database_query_completed=True,
                                            queried_rpm_database_records=len(rpm_records), matching_packages=package_candidates,
                                            evidence_path='evidence/runtime/rpm-list.out',
                                            explicit_query_evidence_path='evidence/runtime/kernel-package-names.out',
                                            pinned_query_evidence_path='evidence/runtime/pinned-rpm-device-queries.out',
                                            pinned_package_names_without_device_rpm_record=pinned_names,
                                            installed_metadata_fields=['name', 'epoch', 'version', 'release', 'architecture',
                                                                       'source_rpm', 'build_time', 'install_time'],
                                            mounted_files_evidence_path='evidence/runtime/partition-metadata.out',
                                            owner_query_evidence_path='evidence/runtime/module-owners.out'),
                  installed_module_inventory=dict(total_unique_paths=len(rows),
                                                  file_type_counts=dict(by_type),
                                                  rpm_owned_files=modules['rpm_owned_files'],
                                                  inventory_path='evidence/runtime/installed-modules.json'),
                  loaded_module_inventory=dict(total=len(current), initial_snapshot_total=len(initial),
                                               inventory_path='evidence/runtime/loaded-modules.json'),
                  repository_identity_status='DEFERRED_TO_PHASE_6')
    write_json(ROOT / '01_runtime_kernel.json', result)
    print(json.dumps({'kernel_build_id': kernel_id['gnu_build_id'], 'archive': archive,
                      'installed': len(rows), 'loaded': len(current),
                      'active_device_rpm_database_records': len(rpm_records)}, indent=2))


if __name__ == '__main__':
    main()
