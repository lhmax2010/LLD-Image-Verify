#!/usr/bin/env python3
"""Check original log, RPM and device relations without rebuilding artifacts."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import xml.etree.ElementTree as ET

from review_common import BASE, HERE, RELEASE, SNAPSHOT, MODULE_RE, csv_rows, dump, load, log_ref, need, sha, sha_bytes

LOGS = {
    'evidence/build/linux-rpi-armv7l.out': ('linux-rpi','platform/kernel/linux-rpi','42aeefac58edeb081aff440f0b60be71cbe49755'),
    'evidence/build/linux-tizen-modules-armv7l.out': ('linux-tizen-modules','platform/kernel/linux-tizen-modules','458baad02d812098938663971d1b8560a4813375'),
}
EVT_KEYS = ('llvm_selection','event','install_event','rpm_write','build_completion')
MODULE_PREFIX = f'/lib/modules/{RELEASE}/'
LINK_RE = re.compile(r'^\[[^\]]+\]\s+LD \[M\]\s+(\S+)$')
HEX_ROW = re.compile(r'^(?:\s+[0-9a-f]{2})+\s*$')

def selected_packages(base):
    data = load(base,'02_repository_identity.json')
    rows = csv_rows(base,'02_kernel_rpm_inventory.csv')
    names = {(row['name'],row['version'],row['release'],row['architecture']) for row in rows if row['selected']=='True'}
    expected = {(row['name'],row['version'],row['release'],row['architecture']) for row in data['selected_rpms']}
    need(len(rows)==data['candidate_rpm_count'] and names==expected and len(names)==10, 'RPM CSV/JSON mismatch')
    need(data['snapshot']==SNAPSHOT,'unexpected repository snapshot')
    rpm = {Path(row['rpm_path']).name: row for row in data['selected_rpms']}
    for name, row in rpm.items():
        path = base/row['rpm_path']
        need(sha(path)==row['sha256']==row['metadata_checksum'] and row['rpm_digest_verification']=='PASS',
             f'RPM checksum mismatch {name}')
    return data, rpm

def filelists(base, data, rpm):
    area = data['metadata']['packages']
    raw = (base/area['filelists']['path']).read_bytes()
    xml = gzip.decompress(raw)
    need(sha_bytes(raw)==area['filelists']['metadata_checksum'] and sha_bytes(xml)==area['filelists']['metadata_open_checksum'],
         'filelists compressed/open checksum mismatch')
    root = ET.fromstring(xml)
    found = defaultdict(set)
    outside = []
    for package in root.findall('{*}package'):
        version = package.find('{*}version')
        basename = f'{package.get("name")}-{version.get("ver")}-{version.get("rel")}.{package.get("arch")}.rpm'
        for member in package.findall('{*}file'):
            path = member.text or ''
            if path.startswith(MODULE_PREFIX) and MODULE_RE.search(path):
                need(member.get('type','file')=='file', f'non-regular module candidate {path}')
                found[basename].add(path)
                if basename not in rpm:
                    outside.append((basename,path))
    need(not outside and len(found)==2,'unaccounted packaging candidates')
    return found

def rpm_file_digests(base, rpm, package_members, out):
    receipts = []
    result = {}
    for package, members in package_members.items():
        relative = rpm[package]['rpm_path']
        argv = ['rpm','-qp','--qf','%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]',relative]
        proc = subprocess.run(argv,cwd=base,capture_output=True,check=False)
        stem = out/'evidence'/('rpm-files-'+package.removesuffix('.rpm'))
        stem.with_suffix(stem.suffix+'.out').write_bytes(proc.stdout)
        stem.with_suffix(stem.suffix+'.err').write_bytes(proc.stderr)
        receipts.append(dict(argv=argv,cwd=str(base),exit_status=proc.returncode,stdout=str(stem.relative_to(out))+'.out'))
        need(proc.returncode==0, f'RPM query failed {package}')
        algorithm,*lines = proc.stdout.decode().splitlines()
        need(algorithm=='8',f'RPM file-digest algorithm differs for {package}')
        rows = dict(line.split('\t',maxsplit=1) for line in lines)
        need(members=={p for p in rows if p.startswith(MODULE_PREFIX) and MODULE_RE.search(p)},f'filelists drift {package}')
        result.update({(package,path):rows[path] for path in members})
    return result, receipts

def provenance(base, archive, data):
    build = ET.parse(base/data['publication_build_evidence']).getroot()
    need(build.findtext('id')==SNAPSHOT and
         build.findtext('base_id')=='tizen-base-toolchain_20261119.042539' and
         'armv7l' in {arch.text for arch in build.findall('buildtargets/buildtarget/archs/arch')},
         'publication build.xml differs')
    manifest_file = 'evidence/repository/manifest.out'
    need(sha(base/manifest_file)==data['manifest_sha256'],'manifest SHA mismatch')
    manifest = {el.get('name'):el.get('revision') for el in ET.parse(base/manifest_file).getroot().findall('project')}
    receipts = {}
    for path,(log_name,project,rev) in LOGS.items():
        record = load(base,path.removesuffix('.out')+'.cmd.json')
        url = next(arg for arg in record['argv'] if arg.endswith('.buildlog.txt'))
        need(url==data['snapshot_url']+f'builddata/buildlogs/standard/armv7l/succeeded/{log_name}.buildlog.txt'
             and record['exit_status']==0 and manifest[project]==rev and sha(base/path)==archive[path],
             f'build log snapshot binding failed: {path}')
        receipts[path] = dict(full_log_path='round1/'+path, full_log_sha256=archive[path], url=url, source_project=project,
                              manifest_revision=rev, original_receipt='round1/'+path.removesuffix('.out')+'.cmd.json')
    return receipts

def by_unique(rows, key):
    indexed = {key(row):row for row in rows}
    need(len(indexed)==len(rows),'duplicate audit key')
    return indexed

def originals(base):
    manifest = {}
    for entry in (base/'SHA256SUMS').read_text().splitlines():
        digest, relative = entry.split('  ',1)
        need(relative not in manifest and (base/relative).resolve().is_relative_to(base)
             and (base/relative).is_file(),f'invalid manifest member {relative}')
        manifest[relative] = digest
    receipts = []
    for raw in (base/'COMMANDS.jsonl').read_text().splitlines():
        row = json.loads(raw)
        need(all(row[key] in manifest for key in ('record','stdout','stderr')),f'untracked command output {row["record"]}')
        record = load(base,row['record'])
        need(all(record[key]==row[key] for key in ('argv','exit_status','elapsed_seconds','started_utc')),
             f'command index differs {row["record"]}')
        receipts.append(row['record'])
    need(len(receipts)==len(set(receipts)), 'duplicate command receipts')
    return manifest, len(receipts)

def iter_loaded_notes(path):
    name = None
    rows = []
    def parse():
        data = bytes.fromhex(' '.join(line for line in rows if HEX_ROW.fullmatch(line)))
        expected, target = rows[0].split()
        need(target==f'/sys/module/{name}/notes/.note.gnu.build-id',f'unexpected note path {name}')
        need(len(data)==36 and sha_bytes(data)==expected and
             struct.unpack_from('<III',data)==(4,20,3) and data[12:16]==b'GNU\0',f'invalid note framing {name}')
        return name, data[16:].hex(), expected
    for line in path.read_text().splitlines():
        if line.startswith('[MODULE='):
            if name is not None:
                yield parse()
            name, rows = line[8:-1], []
        else:
            rows.append(line)
    if name is not None:
        yield parse()

def scan_modules(base, archive, repo_digests, log_binding):
    binary = load(base,'evidence/modules/module-analysis.json')
    cov = load(base,'05_kernel_module_coverage.json')
    raw_rows = csv_rows(base,'05_kernel_module_inventory.csv')
    ready = load(base,'evidence/runtime/installed-modules.json')
    published = load(base,'evidence/repository/image-profile-verification.json')['boot']['boot_archive_verification']['modules']
    events = load(base,'evidence/build/module-final-commands.json')
    quiet = by_unique(events['quiet_link_observations'],lambda r:(r['package_rpm'],r['payload_path']))
    csv_repo = by_unique([r for r in raw_rows if r['scope']=='repository'],lambda r:(r['rpm']+'.rpm',r['path']))
    csv_dev = by_unique([r for r in raw_rows if r['scope']=='device'],lambda r:r['path'])
    dev_ready = by_unique(ready['files'],lambda r:r['path'])
    structured = by_unique(binary['repository'],lambda r:(r['rpm']+'.rpm',r['path']))
    structured_dev = by_unique(binary['device'],lambda r:r['path'])
    image_parts = by_unique(published['files'],lambda r:r['rpm_path'])
    need(len(repo_digests)==len(quiet)==len(csv_repo)==len(csv_dev)==len(dev_ready)==len(structured)==len(structured_dev)==
         len(image_parts)==59 and set(repo_digests)==set(quiet)==set(csv_repo)==set(structured)
         and set(csv_dev)==set(dev_ready)==set(structured_dev),'module source sets differ')
    names, filenames = Counter(), Counter()
    names_all = {path:(base/path).read_text().splitlines() for path in log_binding}
    links = load(base,'evidence/build/kernel-build-log-events.json')
    starts = {next(iter(LOGS)): [e['line'] for e in links['normal_target_scope']]}
    ext_path = list(LOGS)[1]
    ext_raw = names_all[ext_path]
    ext_fences = [idx for idx,line in enumerate(ext_raw,1) if re.search(r'\+ make -C kernel (?:KERNELDIR=/boot/kernel/devel/kernel-devel-arm-rpi4$|clean KERNELDIR=/boot/kernel/devel/kernel-devel-arm-rpi4-rt$)',line)]
    need(len(ext_fences)==2,'ambiguous ext non-RT scope')
    starts[ext_path]=ext_fences
    scopes = {'in-tree':0,'out-of-tree':0}
    relation = []
    for (package, path), expected_sha in sorted(repo_digests.items()):
        row = csv_repo[package,path]
        observed = quiet[package,path]
        device_path = '/usr'+path
        device = csv_dev[device_path]
        dev_file = dev_ready[device_path]
        package_image = image_parts[path]
        ev = structured[package,path]
        need(sha(base/row['file'])==row['raw_sha256']==sha(base/device['file'])==device['raw_sha256']==
             dev_file['sha256']==expected_sha==package_image['image_file_sha256'],f'module byte chain broken {path}')
        for filename in (row['file'],device['file'],row['readelf'],device['readelf'],package_image['image_extracted_evidence']):
            need(filename in archive,f'evidence outside manifest {filename}')
        need(sha(base/package_image['image_extracted_evidence'])==expected_sha,f'image module hash mismatch {path}')
        need(ev['classification']==structured_dev[device_path]['classification']==row['classification']==device['classification']=='LLD_INDICATED'
             and row['proves_final_link']==device['proves_final_link']=='False' and row['parsed']==device['parsed']=='True',
             f'original classification drift {path}')
        need(json_evidence_shape(row,device),f'class evidence is not bound to output {path}')
        cls = 'out-of-tree' if '/extra/' in path else 'in-tree'
        scopes[cls] += 1
        group = observed['event']['evidence']
        lo,hi = starts[group]
        idx = vars_in_order(observed,names_all[group],group)
        need(lo <= idx[1] < hi,'final target is outside non-RT scope')
        match = LINK_RE.fullmatch(observed['event']['raw'])
        need(match and match[1]==observed['build_output'] and match[1].endswith('.ko') and
             observed['install_event']['raw'].endswith(path) and observed['rpm_write']['raw'].endswith('/'+package),
             f'not a final .ko/install/NEVRA chain {path}')
        build_rel = match[1].split('/kernel/',1)[1] if cls=='out-of-tree' else match[1]
        expected_path = MODULE_PREFIX+('extra/' if cls=='out-of-tree' else 'kernel/')+build_rel
        need(expected_path==path,'build relative path does not map to payload')
        need(sum(bool(m and m[1]==match[1]) for m in (LINK_RE.fullmatch(line) for line in names_all[group][lo-1:hi-1]))==1,
             f'ambiguous .ko target within the same build scope {path}')
        filenames[PurePosixPath(path).name]+=1
        names[row['name']]+=1
        relation.append(dict(module_name=row['name'], module_path=path, device_path=device_path, group=cls,
            binary_rpm=package, build_output=match[1], log=log_ref(observed['event']), log_line=idx[1],
            llvm_line=idx[0], install_line=idx[2], rpm_write_line=idx[3], build_completion_line=idx[4],
            selected_source_revision=log_binding[group]['manifest_revision'], original_classification=row['classification'],
            rpm_payload_sha256=expected_sha, repository_extracted_sha256=row['raw_sha256'], device_sha256=device['raw_sha256'],
            published_image_module_sha256=package_image['image_file_sha256'], final_link_argv_observed=False))
    need(scopes=={'in-tree':52,'out-of-tree':7},'in/out tree denominator drift')
    need(not events['install_without_matching_link'] and not cov['repository_excluded'] and not cov['device_excluded'],
         'unmatched installs or excluded module rows require review')
    for scope in ('repository','device'):
        c = cov[scope]
        need(c['total_module_files']==c['successfully_parsed']==c['counts']['LLD_INDICATED']==59 and
             sum(c['counts'].values())==59 and c['confirmed_lld_coverage']==0 and c['lld_evidence_coverage']==1,
             'coverage does not recompute')
    return relation, scopes, [name for name,count in names.items() if count>1], [name for name,count in filenames.items() if count>1]

def json_evidence_shape(repo, device):
    r, d = (json.loads(row['linker_evidence_details']) for row in (repo,device))
    return (r==d and len(r)==1 and r[0]['linker']=='LLD' and not r[0]['final_link'] and
            'LD [M]' in r[0]['raw'] and 'export LLVM=1' in r[0]['raw'])

def vars_in_order(obj, source, group):
    entries = [obj[key] for key in EVT_KEYS]
    numbers = [x['line'] for x in entries]
    need(numbers==sorted(set(numbers)) and all(x['evidence']==group and source[x['line']-1]==x['raw'] for x in entries)
         and entries[0]['raw'].endswith('export LLVM=1'),f'invalid log source/range {obj["payload_path"]}')
    return numbers

def loaded_verify(base):
    note_file = 'evidence/runtime/loaded-build-ids.out'
    notes = by_unique(list(iter_loaded_notes(base/note_file)),lambda item:item[0])
    map_data = by_unique(csv_rows(base,'05_loaded_module_mapping.csv'),lambda r:r['name'])
    installed = by_unique([r for r in csv_rows(base,'05_kernel_module_inventory.csv') if r['scope']=='device'],lambda r:r['name'])
    runtime = by_unique(load(base,'evidence/runtime/loaded-modules.json')['modules'],lambda r:r['name'])
    snapshots = {line:line.split()[0] for line in (base/'evidence/runtime/loaded-list.out').read_text().splitlines() if ' Live ' in line}
    need(len(notes)==len(map_data)==len(runtime)==len(snapshots)==11 and set(notes)==set(map_data)==set(runtime)==set(snapshots.values()),
         'loaded module inventories mismatch')
    checked = []
    for name, (_,build_id,note_hash) in notes.items():
        record = map_data[name]
        dev = installed[name]
        need(build_id==record['live_gnu_build_id']==record['installed_gnu_build_ids']==dev['elf_build_id']==runtime[name]['build_id']
             and note_hash==runtime[name]['build_id_note_sha256'] and record['device_paths']==dev['path'] and
             record['installed_sha256']==dev['raw_sha256'] and record['proc_modules_raw'] in snapshots,
             f'loaded module ID mismatch {name}')
        need(f'Build ID: {build_id}' in (base/dev['readelf']).read_text(),f'ELF note evidence differs {name}')
        checked.append(dict(name=name,gnu_build_id=build_id,raw_note_sha256=note_hash,device_path=dev['path'],
                            module_sha256=dev['raw_sha256'],elf_receipt='round1/'+dev['readelf']))
    return checked

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=BASE)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    manifest, command_count=originals(base)
    data,rpm=selected_packages(base)
    scanned=filelists(base,data,rpm)
    digests, rpm_receipts=rpm_file_digests(base,rpm,scanned,out)
    logs=provenance(base,manifest,data)
    paths,groups,dupe_names,dupe_file_names=scan_modules(base,manifest,digests,logs)
    loaded=loaded_verify(base)
    result = dict(status='PASS', snapshot=SNAPSHOT, manifest_sha256=sha(base/'SHA256SUMS'),
                  manifest_entries=len(manifest), command_index_sha256=sha(base/'COMMANDS.jsonl'), command_receipts=command_count,
                  rpm_candidates=data['candidate_rpm_count'], selected_rpms=len(rpm), module_groups=groups,
                  module_payload_rows=paths, duplicate_module_names=dupe_names, duplicate_module_basenames=dupe_file_names,
                  loaded_modules=loaded, log_bindings=logs, rpm_query_receipts=rpm_receipts)
    dump(out/'08_01_evidence_integrity_review.json',result)
    print(f'PASS: {len(manifest)} manifest references; {command_count} original receipts; 59 final .ko/install/RPM/byte chains; 11 loaded Build IDs.')

if __name__=='__main__':
    main()
