#!/usr/bin/env python3
"""Reconcile archived Phase 14 device reads with the pinned release artifacts."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
NEW=ROOT.parent/'kernel_lld_verification_20261125'
OLD=ROOT.parent/'kernel_lld_verification_20261120'
PAST=ROOT.parent/'phase13_final_acceptance'
E=ROOT/'evidence'
sys.path.insert(0,str(NEW/'scripts'))
from parse_runtime import read_notes, SHA

ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
TARGET='tizen-unified-toolchain_20261125.130358_tizen-headed-armv7l'
RELEASE='6.12.80-arm-rpi4-v7l'
KDBUS='extra/kdbus/kdbus.ko'
SERIAL='private-address-03:26101'
PATTERNS={
    'unknown_symbol':r'unknown symbol|unresolved symbol|undefined symbol',
    'invalid_module_format':r'invalid module format|exec format error|invalid (elf|module header)',
    'version_magic':r'version magic|vermagic.*(?:mismatch|invalid)|disagrees about version',
    'module_relocation':r'(?:module|kdbus|\.ko\b).*relocat|relocat.*(?:failed|error|unsupported|overflow)|unknown relocation',
    'module_load_failure':r'(?:module|kdbus|\.ko\b).*(?:failed to load|load failed|cannot load|loading error)|(?:failed|unable) to (?:load|insert).*module',
    'oops_panic_trace':r'\boops\b|kernel panic|call trace:|internal error:|kernel BUG at|unable to handle kernel|\bKASAN:',
    'kdbus_error':r'\bkdbus(?:fs)?\b.*(?:fail(?:ed|ure)?|error|invalid|unable|warning|timeout|denied)|(?:fail(?:ed|ure)?|error|invalid|unable|warning|timeout|denied).*\bkdbus(?:fs)?\b',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path,data):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def capture_scope(scope):
    record=load(E/f'device-{scope}.cmd.json')
    require(record['exit_status']==0,f'{scope} SDB command failed')
    fields={}
    active=None
    for line in (E/f'device-{scope}.out').read_text().splitlines():
        clean=ANSI.sub('',line)
        if re.fullmatch(r'\[[A-Z0-9_]+\]',clean):
            active=clean[1:-1]
            fields[active]=[]
        elif active:
            fields[active].append(clean)
    require('END' in fields,f'{scope} response is incomplete')
    return fields


def one(section,key):
    require(len(section[key])==1,f'Expected unique {key}')
    return section[key][0]


def bind_kernel(identity,published_rows):
    note=read_notes(identity['KERNEL_NOTES'])
    require(note and note['build_id'],'No live GNU kernel Build ID')
    kernel=next(row for row in published_rows if row['role']=='KERNEL_IMAGE')
    rpm=E/'release'/kernel['filename']
    require(sha(rpm)==kernel['published_checksum'],'Kernel RPM differs from published metadata')
    extract=E/'release/kernel-rpm-extract.out'
    require(load(E/'release/kernel-rpm-extract.cmd.json')['exit_status']==0,'Kernel RPM extraction failed')
    published_zimage=next(line.split() for line in extract.read_text().splitlines() if line.startswith('/boot/zImage '))
    boot=(E/'release/boot/zImage')
    require(boot.stat().st_size==int(published_zimage[1]) and sha(boot)==published_zimage[3],
            'Published boot RPM zImage member mismatch')
    compressed=boot.read_bytes()
    require(compressed[36:40]==b'\x18\x28\x6f\x01','Published zImage ARM magic invalid')
    live_banner=one(identity,'PROC_VERSION').encode()
    device_note=bytes.fromhex(note['raw_hex'])
    matches=[]
    for magic in re.finditer(b'\x1f\x8b\x08',compressed):
        try:
            decoder=zlib.decompressobj(wbits=31)
            raw=decoder.decompress(compressed[magic.start():],128*1024*1024)
        except zlib.error:
            continue
        if decoder.eof and raw.count(device_note)==1 and raw.count(live_banner)==1:
            matches.append((magic.start(),raw))
    require(len(matches)==1,'Live kernel notes/banner did not uniquely match a published kernel RPM payload')
    offset,raw=matches[0]
    live_note_offset=raw.index(device_note)
    raw_file=E/'release/raw-Image'
    raw_file.write_bytes(raw)
    (E/'release/runtime-kernel-notes.bin').write_bytes(device_note)
    sdk=(PAST/'evidence/runtime/new-sdk-vmlinux-build-id.out').read_text()
    sdk_id=re.search(r'Build ID: ([0-9a-f]{40})',sdk).group(1)
    result={'status':'EXACT_LIVE_NOTES_AND_BANNER_MATCH','rpm':kernel['filename'],
            'rpm_published_sha256':kernel['published_checksum'],'url':kernel['download_url'],
            'rpm_member':'/boot/zImage','zimage_sha256':published_zimage[3],
            'raw_image_sha256':sha(raw_file),'raw_image_size':len(raw),'gzip_offset':offset,
            'device_note_offset_in_raw':live_note_offset,'device_note_sha256':note['sha256'],
            'device_kernel_build_id':note['build_id'],'device_note_length':len(device_note),
            'device_banner_offset_in_raw':raw.index(live_banner),'device_banner':live_banner.decode(),
            'sdk_vmlinux_build_id_reference':sdk_id,'sdk_reference_build_id_same_as_live':sdk_id==note['build_id']}
    save(E/'release/kernel-identity.json',result)
    return result


def compare_modules(source, baseline_modules, pub):
    expected=rows(NEW/'11G_MODULE_INVENTORY_DIFF.csv')
    covered={r['filename']:r for r in pub if r['role'] in ('IN_TREE_MODULES','OUT_OF_TREE_MODULES')}
    require(len(expected)==59 and len(covered)==2,'Invalid pinned module manifest or carrier count')
    require(all(row['repository_checksum_verification']=='PASS' and row['local_sha256']==row['published_checksum']
                for row in covered.values()),'Carrier lacks Phase 11 repository verification')
    entries={}
    for raw in source['MODULE_SHA256']:
        match=SHA.fullmatch(raw)
        require(match is not None,f'Unexpected device SHA output: {raw}')
        path=match[2].removeprefix('./')
        require(path not in entries,f'Duplicate module path: {path}')
        entries[path]=match[1]
    old_matches=baseline_modules['device_module_sha256_matches']
    require(old_matches==59,'Old instrumented baseline incomplete')
    pending=set(entries)
    report=[]
    for row in expected:
        key=row['module_path']
        actual=entries.get(key,'')
        pending.discard(key)
        require(row['new_rpm'] in covered and row['new_present']=='True','Target module carrier unknown')
        report.append({'path':key,'group':row['module_group'],'published_rpm':row['new_rpm'],
            'published_rpm_sha256':covered[row['new_rpm']]['published_checksum'],
            'published_module_sha256':row['new_sha256'],'device_module_sha256':actual,
            'new_qb_file_match':'PASS' if actual==row['new_sha256'] else ('MISSING' if not actual else 'MISMATCH'),
            'old_qb_published_module_sha256':row['old_sha256'],
            'device_content_vs_old_qb':'IDENTICAL' if actual==row['old_sha256'] else 'CHANGED'})
    write_csv(E/'module-runtime-to-rpm.csv',report)
    require(len(pending)==0 and len(entries)==59 and all(r['new_qb_file_match']=='PASS' for r in report),
            'Device module files differ from pins')
    return report,{'count':len(entries),'installed_rpm_header_exit_status':int(one(source,'RPM_HEADER_EXIT')),
        'installed_rpm_file_digest_exit_status':int(one(source,'RPM_FILE_DIGESTS_EXIT')),
        'root':one(source,'MODULE_ROOT'),'published_member_sha256_match':59,
        'in_tree_matches':sum(r['group']=='in-tree' for r in report),'out_of_tree_matches':sum(r['group']=='out-of-tree' for r in report),
        'module_symlinks':source['MODULE_SYMLINKS'],'old_release_byte_identical_count':sum(r['device_content_vs_old_qb']=='IDENTICAL' for r in report)}


def main():
    identity=capture_scope('identity')
    boot=capture_scope('boot')
    kdbus=capture_scope('kdbus')
    modules=capture_scope('modules')
    device_targets=[l.split()[0] for l in (E/'sdb-target.out').read_text().splitlines() if l.startswith('private-address-03:')]
    require(device_targets==[SERIAL],'SDB device admission receipt mismatch')
    uname,release,arch=identity['UNAME']
    model=one(identity,'DEVICE_MODEL')
    require(release==RELEASE and arch=='armv7l' and model.startswith('Raspberry Pi 4'),'Target platform identity mismatch')
    require(one(identity,'IMAGE_BUILD_ID')=='BUILD_ID='+TARGET,'Target image identity mismatch')
    banner=one(identity,'PROC_VERSION')
    require(one(identity,'BOOT_BANNER').endswith(banner),'Kernel boot banner and /proc/version mismatch')
    old_kernel=load(OLD/'01_runtime_kernel.json')
    old_modules=load(OLD/'06_identity_verification.json')
    pub=rows(NEW/'11A_RPM_INVENTORY.csv')
    release_identity=bind_kernel(identity,pub)
    report,mods=compare_modules(modules,old_modules,pub)
    expected=load(NEW/'11F_MODULE_ABI_SUMMARY.json')['modules'][KDBUS]
    live_note=read_notes(identity['KDBUS_NOTE'])
    live_file=SHA.fullmatch(one(identity,'KDBUS_FILES'))
    live_line=next(line for line in kdbus['PROC_MODULES'] if line.startswith('kdbus '))
    require(live_file and live_file[1]==expected['new']['artifact_sha256'],'Installed kdbus digest differs')
    require(live_line==one(identity,'KDBUS_LOADED') and live_note['build_id'] in expected['new']['build_ids'],
            'Loaded kdbus identity differs')
    sysfs=dict(line.split('=',1) for line in kdbus['KDBUS_SYSFS'] if '=' in line)
    require(sysfs['initstate']=='live' and any(' - kdbusfs ' in line for line in kdbus['KDBUS_MOUNTINFO']),
            'kdbus runtime not live')
    _,core,refs,deps,state,*_=live_line.split()
    require((core,refs,state.lower())==(sysfs['coresize'],sysfs['refcnt'],sysfs['initstate']),
            'kdbus proc/sysfs runtime fields differ')
    require(boot['SYSTEM_STATE']==['running','exit=0'],'System is not running')
    require('0 loaded units listed.' in boot['FAILED_UNITS'],'Failed units observed, inspect separately')
    boot_targets={}
    for line in boot['BOOT_TARGETS']:
        field,value=line.split('=',1)
        if field=='Id':
            active=value
            boot_targets[active]={}
        else:
            boot_targets[active][field]=value
    require(all(state['ActiveState']=='active' for state in boot_targets.values()) and
            'multi-user.target' in boot_targets and 'graphical.target' in boot_targets,'Boot target did not reach active')
    kernel_logs=boot['DMESG']
    require(one(boot,'DMESG_EXIT')=='0' and any(line.endswith(banner) for line in kernel_logs),
            'Readable dmesg does not include recorded kernel boot')
    errors={name:[line for line in kernel_logs if re.search(rx,line,re.I)] for name,rx in PATTERNS.items()}
    initialized=[line for line in kernel_logs if 'kdbus: initialized' in line]
    other_warnings=[line for line in kernel_logs if
                    re.search(r'regulatory\.db|brcmf_sdio_htclk|brcm/.*failed with error|lsm=SMACK.*action=denied',line,re.I)]
    scan={'dmesg_lines':len(kernel_logs),'patterns':PATTERNS,'hits':errors,'kdbus_initialization':initialized,
          'other_warnings_sample':other_warnings,'journal_exit_status':int(one(boot,'KERNEL_JOURNAL_EXIT')),
          'journal_diagnostics':boot['KERNEL_JOURNAL'],
          'old_full_boot_and_kernel_log_comparable':False}
    save(E/'kernel-log-review.json',scan)
    require(not any(errors.values()) and len(initialized)==1,'Target kernel error or init exception observed')
    old_loaded=rows(OLD/'05_loaded_module_mapping.csv')
    old_line=next(r for r in old_loaded if r['name']=='kdbus')
    old_loaded_names={row['name'] for row in old_loaded}
    new_loaded_names={line.split()[0] for line in kdbus['PROC_MODULES']}
    kb={'status':'PASS_LIVE_STATE','module_sha256':live_file[1],'path':live_file[2],
        'build_id':live_note['build_id'],'proc_modules':live_line,'dependencies':[] if deps=='-' else deps.rstrip(',').split(','),
        'sysfs':sysfs,'holders':kdbus['KDBUS_HOLDERS'],'mountinfo':kdbus['KDBUS_MOUNTINFO'],
        'nodes':kdbus['KDBUS_NODES'],'loaded_module_count':len(kdbus['PROC_MODULES']),
        'functional_test_candidate_paths_found':kdbus['TEST_CANDIDATE_PATHS']}
    baseline={'image_build_id':old_kernel['device']['image_build_id'],'model':old_kernel['device']['model'],
              'proc_version':old_kernel['kernel']['proc_version'],'build_id':old_modules['runtime_build_id'],
              'module_matches_published':old_modules['device_module_sha256_matches'],
              'loaded_module_count':old_kernel['loaded_module_inventory']['total'],
              'initial_loaded_module_count':old_kernel['loaded_module_inventory']['initial_snapshot_total'],
              'only_old_loaded_snapshot':sorted(old_loaded_names-new_loaded_names),
              'only_new_loaded_snapshot':sorted(new_loaded_names-old_loaded_names),
              'kdbus_proc_modules':old_line['proc_modules_raw'],'kdbus_installed_sha256':old_line['installed_sha256'],
              'kdbus_loaded_build_id':old_line['live_gnu_build_id']}
    result={'NEW_QB_DEVICE_IDENTITY':'PASS','KERNEL_BOOT':'PASS','MODULE_INVENTORY':'PASS_59_OF_59',
            'MODULE_RUNTIME':'PASS_LIVE_STATE','KERNEL_ERROR_REVIEW':'PASS_OBSERVED_DMESG_SCOPE',
            'FUNCTIONAL_REGRESSION':'NOT_RUN_NO_APPROVED_CASE_AVAILABLE',
            'RUNTIME_REGRESSION':'PARTIAL_PASS_FUNCTIONAL_PENDING',
            'RUNTIME_MEMORY_BENEFIT':'NOT_MEASURED','KERNEL_OWNER_TRADEOFF_ACCEPTANCE':'PENDING_OWNER_REVIEW',
            'PRODUCT_MERGE_READINESS':'PENDING','device':{'serial':SERIAL,'image_build_id':TARGET,'model':model,
            'arch':arch,'release':release,'uname':uname,'boot_id':one(boot,'BOOT_ID'),'uptime':one(boot,'UPTIME')},
            'kernel_release_binding':release_identity,'module_inventory':mods,'kdbus':kb,'boot_targets':boot_targets,
            'observed_kernel_error_count':sum(map(len,errors.values())),'journal_exit_status':scan['journal_exit_status'],
            'old_qb_baseline':baseline,'device_mutation_performed':False}
    save(E/'runtime-result.json',result)
    print('PASS: pinned kernel notes and banner, 59/59 module payloads, boot and kdbus live state; functional remains pending')


if __name__=='__main__':
    main()
