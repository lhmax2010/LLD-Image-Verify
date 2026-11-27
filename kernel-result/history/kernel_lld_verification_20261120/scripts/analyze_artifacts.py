#!/usr/bin/env python3
"""Inspect the pinned target RPM payloads and correlate installed module bytes."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import zlib

from record import ROOT, run

RELEASE = '6.12.80-arm-rpi4-v7l'
MODULE = re.compile(r'\.ko(?:\.(?:gz|xz|zst))?$')
CATEGORIES = ('LLD_CONFIRMED', 'LLD_INDICATED', 'BFD_CONFIRMED', 'BFD_INDICATED',
              'OTHER_LINKER', 'CONFLICTING_EVIDENCE', 'UNKNOWN', 'PARSE_FAILED')
BINARY = re.compile(r'^(?:vmlinux(?:\.(?:unstripped|debug|lz4|gz|xz|zst))?|Image|zImage|uImage|boot\.img|vmlinuz|System\.map|config)(?:-.*)?$')
VERSION = re.compile(rb'Linux version [\x20-\x7e]{12,450}')
HEX = r'[0-9a-fA-F]+'

def rel(path):
    return str(Path(path).relative_to(ROOT))

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def dump(path, data):
    (ROOT / path).write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')

def write_csv(path, rows, fields):
    with (ROOT / path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def classify_path(path):
    name = path.name
    if MODULE.search(name) and RELEASE in path.parts:
        return 'module'
    if MODULE.search(name) and '/modules/' in '/'+str(path):
        return 'module_outside_release'
    if '.ko.debug' in name:
        return 'debug_module'
    if any(part in path.parts for part in ('tools', 'Documentation')):
        return None
    if (BINARY.fullmatch(name) or name == '.config' or name in ('compile.h', 'auto.conf')
        or name.endswith('.dtb') and 'bcm2711-rpi-4' in name):
        return 'kernel_binary'
    return None

def take(stream, size, label):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(f'truncated cpio {label}')
    return data

def copy_payload(stream, size, output):
    with output.open('wb') as file:
        while size:
            block = take(stream, min(size, 2**20), 'payload')
            file.write(block)
            size -= len(block)

def unpack(rpm):
    package = rpm.name.removesuffix('.rpm')
    status, archive = run(f'kernel_binary/payload/{package}/rpm2cpio', ['rpm2cpio', rpm], 240)
    if status:
        return [], dict(rpm=rel(rpm), exit_status=status, evidence=rel(archive))
    records, seen, linked, pending = [], set(), {}, []
    output_root = ROOT / 'evidence/kernel_binary/payload' / package / 'files'
    with archive.open('rb') as stream:
        while True:
            header = take(stream, 110, 'header')
            if header[:6] not in (b'070701', b'070702'):
                raise ValueError(f'invalid newc magic at offset {stream.tell()-110}')
            ino, mode, uid, gid, nlink, mtime, size, major, minor, _, _, length, crc = (
                int(header[i:i+8], 16) for i in range(6, 110, 8)
            )
            name = take(stream, length, 'path')
            if not name.endswith(b'\0'):
                raise ValueError('unterminated newc path')
            take(stream, (-(110+length)) % 4, 'path padding')
            name = name[:-1].decode('utf-8', 'surrogateescape')
            if name == 'TRAILER!!!':
                break
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError(f'unsafe RPM path {name!r}')
            if path in seen:
                raise ValueError(f'duplicate RPM archive path {path}')
            seen.add(path)
            category = classify_path(path)
            kind = 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else (
                'directory' if stat.S_ISDIR(mode) else 'special'
            )
            row = dict(rpm=package, rpm_file=rel(rpm), path='/'+str(path), category=category,
                       file_type=kind, payload_size=size, archive=rel(archive), archive_file_offset=stream.tell())
            if category and kind == 'symlink':
                row['symlink_target'] = take(stream, size, 'link target').decode()
            elif kind == 'file' and (category or nlink > 1):
                key = (major, minor, ino)
                if nlink > 1 and size == 0:
                    if category:
                        pending.append((row, key))
                else:
                    target = output_root / (path if category else Path('.hardlinks') / ('-'.join(map(str, key))))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copy_payload(stream, size, target)
                    if category:
                        row['file'] = rel(target)
                        row['raw_sha256'] = sha(target)
                    if nlink > 1:
                        linked[key] = target
            else:
                stream.seek(size, 1)
            take(stream, (-size) % 4, 'payload padding')
            if category:
                records.append(row)
    for row, key in pending:
        if key in linked:
            row.update(file=rel(linked[key]), raw_sha256=sha(linked[key]))
        else:
            row['error'] = 'unresolved RPM hardlink'
    return records, dict(rpm=rel(rpm), exit_status=status, evidence=rel(archive), sha256=sha(archive), archive_entry_count=len(seen))

def strings_by_section(text):
    sections = defaultdict(list)
    section = None
    for line in text.splitlines():
        heading = re.search(r"String dump of section '([^']+)'", line)
        if heading:
            section = heading.group(1)
        else:
            entry = re.match(r'^\s*\[\s*('+HEX+r')\]\s+(.*)$', line)
            if section and entry:
                sections[section].append({'section_offset': int(entry[1], 16), 'text': entry[2]})
    return sections

def elf(row, path, stem, cross=False):
    args = ['-hSWn', '-p', '.comment']
    if row.get('category') in ('module', 'debug_module'):
        args.extend(['-p', '.modinfo'])
    status, output = run(stem+'-readelf', ['readelf', *args, path], 80)
    text = output.read_text(errors='replace')
    row.update(readelf=rel(output), readelf_status=status, representative_elf=rel(path), elf_sha256=sha(path))
    for field in ('Class', 'Data', 'Type', 'Machine', 'Flags'):
        match = re.search(r'^\s*'+field+r':\s*(.*)$', text, re.M)
        if match:
            row['elf_'+field.lower()] = match[1]
    row['build_ids'] = re.findall(r'Build ID: ('+HEX+r')', text)
    row['elf_build_id'] = ';'.join(row['build_ids'])
    row['parsed'] = status == 0 and all('elf_'+field in row for field in ('machine', 'type', 'class'))
    sections = strings_by_section(text)
    row['comment'] = sections['.comment']
    row['compiler'] = ' | '.join(entry['text'] for entry in row['comment']
                                if re.search(r'clang version|\bGCC:', entry['text'], re.I))
    row['modinfo'] = sections['.modinfo']
    for field in ('vermagic', 'name'):
        row[field] = ' | '.join(entry['text'].partition('=')[2] for entry in row['modinfo']
                                if entry['text'].partition('=')[0] == field)
    if not row['name'] and row.get('category') in ('module', 'debug_module'):
        row['name'] = re.sub(r'\.ko.*$', '', PurePosixPath(row['path']).name).replace('-', '_')
    row['vermagic_release_match'] = (row['vermagic'].split()[0] == RELEASE) if row['vermagic'] else None
    if cross:
        llvm = shutil.which('llvm-readelf') or next((str(p) for p in Path('/usr/lib').glob('llvm-*/bin/llvm-readelf') if p.is_file()), None)
        if llvm:
            row['llvm_readelf_status'], output = run(stem+'-llvm-readelf', [llvm, *args, path], 80)
            row['llvm_readelf'] = rel(output)
    return row

def classify(row, commands):
    entries = []
    for entry in row.get('comment', []):
        value = entry['text']
        linker = None
        if re.match(r'^Linker:\s+LLD\b', value, re.I):
            linker = 'LLD'
        elif re.search(r'GNU (?:gold|ld\.gold)|^Linker:\s*(?:mold|gold)\b', value, re.I):
            linker = 'OTHER'
        elif re.match(r'^(?:Linker:\s*)?GNU (?:BFD(?: linker)?|ld(?: \(GNU Binutils[^)]*\)|\.bfd)?)\s+[0-9]', value, re.I):
            linker = 'BFD'
        if linker:
            entries.append(dict(type='ELF .comment linker identification', linker=linker,
                                location=f'{row["readelf"]} .comment+{entry["section_offset"]:#x}',
                                raw=value, final_link=False, confidence='MEDIUM'))
    for entry in commands:
        entries.append(entry)
    row['linker_evidence'] = entries
    families = {entry['linker'] for entry in entries}
    confirmed = {entry['linker'] for entry in entries if entry['final_link']}
    if not row.get('parsed'):
        cls, reason = 'PARSE_FAILED', row.get('error', 'ELF header or section parsing failed')
    elif len(families) > 1:
        cls, reason = 'CONFLICTING_EVIDENCE', 'Linker evidence names different linker families; provenance needs review'
    elif 'OTHER' in families:
        cls, reason = 'OTHER_LINKER', 'Identified linker family outside LLD/BFD'
    elif families:
        linker = next(iter(families))
        cls = linker + ('_CONFIRMED' if linker in confirmed else '_INDICATED')
        reason = ('Exact final output command in matching successful build evidence' if confirmed else
                  'Per-output quiet link, install and packaging records corroborate the LLVM-selected '
                  'recipe; historical final linker executable and command are absent' if
                  any(e['type'].startswith('Per-output') for e in entries) else
                  'Linker string in ELF .comment; it can be retained from an earlier link')
    else:
        cls, reason = 'UNKNOWN', 'No recognized linker identification or artifact-bound final link command'
    row.update(classification=cls, reason=reason,
               evidence_type=' | '.join(entry['type'] for entry in entries),
               evidence_location=' | '.join(entry['location'] for entry in entries) or row.get('readelf', ''),
               raw_evidence=' | '.join(entry['raw'] for entry in entries),
               confidence='HIGH' if confirmed and len(families) == 1 else 'MEDIUM' if entries else 'NONE',
               proves_final_link=bool(confirmed and len(families) == 1 and row.get('parsed')),
               elf_linker_identification=any(entry['type']=='ELF .comment linker identification' for entry in entries))
    return row

def decompress_module(row, path, stem):
    tool = {'.gz': 'gzip', '.xz': 'xz', '.zst': 'zstd'}.get(path.suffix)
    if not tool:
        return path
    status, output = run(stem+'-decompress', [tool, '-dc', '--', path])
    if status:
        raise ValueError(f'decompression exit {status}; {rel(output)}')
    return output

def raw_gzip_candidates(path, stem):
    data = path.read_bytes()
    if len(data) < 48 or data[36:40] != b'\x18\x28\x6f\x01':
        return []
    results = []
    for match in re.finditer(rb'\x1f\x8b\x08', data):
        try:
            decoder = zlib.decompressobj(wbits=31)
            decoded = decoder.decompress(data[match.start():], 128*1024*1024)
            if not decoder.eof or len(decoded) < 1024 or not VERSION.search(decoded):
                continue
        except zlib.error:
            continue
        output = ROOT / 'evidence' / (stem+f'-raw-gzip-{match.start():x}.bin')
        output.write_bytes(decoded)
        results.append(dict(file=rel(output), source_offset=match.start(), size=len(decoded), sha256=sha(output)))
    return results

def located_strings(path, runtime_build_id):
    data = path.read_bytes()
    matches = [{'offset': match.start(), 'text': match.group().decode()} for match in VERSION.finditer(data)]
    raw_notes = []
    if runtime_build_id:
        note_id = bytes.fromhex(runtime_build_id)
        for endian in ('<', '>'):
            note = struct.pack(endian+'III', 4, len(note_id), 3)+b'GNU\0'+note_id
            raw_notes.extend(dict(offset=m.start(), endian=endian, build_id=runtime_build_id,
                                  raw_note_hex=note.hex()) for m in re.finditer(re.escape(note), data))
    markers = re.compile(rb'Linker: LLD[^\x00\r\n]{0,80}|LLD 22\.1\.8|GNU ld(?: \(GNU Binutils[^\x00\r\n]{0,140})?|GNU Binutils|clang version[^\x00\r\n]{0,120}', re.I)
    total = Counter()
    samples = []
    text = b'[^\x20-\x7e]'
    limits = defaultdict(int)
    for hit in markers.finditer(data):
        token = hit.group().split(b' ')[0].lower()
        total[token.decode()] += 1
        if limits[token] >= 25:
            continue
        limits[token] += 1
        start, end = hit.start(), hit.end()
        left = re.split(text, data[max(0, start-105):start])[-1]
        right = re.split(text, data[end:end+100])[0]
        sample = left + hit.group() + right
        samples.append(dict(offset=start, string_offset=start-len(left), match=hit.group().decode(errors='replace'),
                            text=sample.decode(errors='replace'),
                            source_type='Kernel build version string' if b'Linux version ' in sample else
                                'Unresolved byte-string source; use section-specific evidence for ELF'))
    return dict(version_strings=matches, matching_gnu_build_id_notes=raw_notes,
                toolchain_string_samples=samples, toolchain_string_hit_counts=dict(total))

def scan_binary(row, runtime_build_id):
    if not row.get('file'):
        return row
    path = ROOT / row['file']
    stem = 'kernel_binary/analysis/'+row['rpm']+'/'+str(PurePosixPath(row['path'])).lstrip('/')
    status, desc = run(stem+'-file', ['file', '-b', path])
    row.update(file_evidence=rel(desc), file_result=desc.read_text(errors='replace').strip())
    if row['path'].startswith('/usr/src/') and path.name in ('version.h', 'compile.h', 'auto.conf'):
        return row
    with path.open('rb') as stream:
        magic = stream.read(4)
    if magic == b'\x7fELF':
        elf(row, path, stem, cross=True)
        row['extraction'] = 'native ELF' if row['parsed'] else 'ELF parse failed'
        row['linker_classification'] = classify(row, [])['classification']
        row.update(located_strings(path, runtime_build_id))
    elif re.match(r'^(?:Image|zImage|uImage|boot\.img|vmlinuz)(?:-.*)?$', path.name):
        for script in ('extract-vmlinux', 'extract-ikconfig'):
            upstream = ROOT / 'evidence/kernel_binary/upstream' / script
            if upstream.is_file():
                status, output = run(stem+'-'+script, ['sh', upstream, path], 90)
                row[script] = dict(exit_status=status, output=rel(output))
                if status == 0 and script == 'extract-vmlinux':
                    with output.open('rb') as stream:
                        if stream.read(4) == b'\x7fELF':
                            elf(row, output, stem+'-extracted', cross=True)
                            row['extraction'] = 'successfully extracted ELF' if row['parsed'] else 'ELF parse failed'
                            row['linker_classification'] = classify(row, [])['classification']
                        else:
                            row[script]['output_type'] = 'non-ELF output'
        row['raw_payloads'] = raw_gzip_candidates(path, stem)
        if row['raw_payloads']:
            row.setdefault('extraction', 'successfully extracted raw kernel binary')
        for payload in row['raw_payloads']:
            payload.update(located_strings(ROOT / payload['file'], runtime_build_id))
        row.update(located_strings(path, runtime_build_id))
        if 'extraction' not in row:
            row['extraction'] = ('extracted version string only' if row['version_strings']
                                 else 'extraction failed or unsupported')
    return row

def module_key(path):
    value = str(path)
    return value.split('/modules/', 1)[-1] if '/modules/' in value else value

@lru_cache(maxsize=None)
def source_lines(path):
    return (ROOT / path).read_text(errors='replace').splitlines()

def locate(path, pattern):
    matches = ((number, line) for number, line in enumerate(source_lines(path), 1) if re.search(pattern, line))
    number, line = next(matches, (None, None))
    return dict(evidence=path, line=number, raw=line) if number is not None else None

def llvm_selections():
    base = 'evidence/build/devel/boot/kernel/devel/kernel-devel-arm-rpi4/'
    patterns = (
        ('.config', r'^CONFIG_LD_IS_LLD=y$'),
        ('.config', r'^CONFIG_LLD_VERSION='),
        ('Makefile', r'^LD\s*= \$\(LLVM_PREFIX\)ld\.lld\$\(LLVM_SUFFIX\)$'),
        ('scripts/Makefile.modfinal', r'^\s*\$\(LD\) -r .*KBUILD_LDFLAGS'),
    )
    if not all((ROOT/(base+path)).is_file() for path, _ in patterns):
        return []
    matches = [locate(base+path, pattern) for path, pattern in patterns]
    if not all(matches):
        return []
    assignment = matches[-2]
    branch = next(((index, line) for index, line in reversed(list(enumerate(source_lines(assignment['evidence'])[:assignment['line']-1], 1)))
                   if line == 'ifneq ($(LLVM),)'), None)
    if branch is None:
        return []
    matches.insert(-2, dict(evidence=assignment['evidence'], line=branch[0], raw=branch[1]))
    return matches

def quiet_indications(row, selections):
    if not selections:
        return []
    indicated = []
    for item in row.get('quiet_build_observations', []):
        if not item.get('observed_successful_install_and_packaging'):
            continue
        events = [item[key] for key in ('llvm_selection','event','install_event','rpm_write','build_completion')]
        if not all(source_lines(e['evidence'])[e['line']-1] == e['raw'] for e in events):
            continue
        if not re.search(r'\bexport LLVM=1$', events[0]['raw']):
            continue
        locations = events+selections
        indicated.append(dict(type='Per-output quiet Kbuild link and packaged LLVM configuration', linker='LLD',
            location=' | '.join(f'{e["evidence"]}:{e["line"]}' for e in locations),
            raw=' | '.join(e['raw'].strip() for e in locations),
            final_link=False, confidence='MEDIUM'))
    return indicated

def eligible_commands(row, index):
    return index.get((row.get('rpm'), row['path']), [])

def compute_coverage(rows, present=True):
    parsed = sum(row.get('parsed', False) for row in rows)
    counts = Counter(row['classification'] for row in rows)
    total = len(rows)
    return dict(inventory_available=present, total_module_files=total if present else None,
                successfully_parsed=parsed if present else None,
                counts={key: counts[key] if present else None for key in CATEGORIES},
                confirmed_lld_coverage=counts['LLD_CONFIRMED']/total if total else None,
                lld_evidence_coverage=(counts['LLD_CONFIRMED']+counts['LLD_INDICATED'])/total if total else None,
                elf_parsing_coverage=parsed/total if total else None,
                duplicate_paths=sorted(path for path,n in Counter(row['path'] for row in rows).items() if n>1),
                distinct_paths=len({row['path'] for row in rows}) if present else None,
                elf_linker_marker_files=sum(row.get('elf_linker_identification', False) for row in rows),
                per_output_quiet_build_files=sum(bool(row.get('quiet_build_observations')) for row in rows),
                vermagic_match=sum(row.get('vermagic_release_match') is True for row in rows),
                expected_arm_rel=sum(row.get('elf_type','').startswith('REL') and row.get('elf_machine')=='ARM'
                                     and row.get('elf_class')=='ELF32' for row in rows),
                duplicate_names=sorted(name for name,n in Counter(row.get('name') for row in rows if row.get('name')).items() if n>1),
                duplicate_raw_sha256=sorted(value for value,n in Counter(
                    row.get('raw_sha256') for row in rows if row.get('raw_sha256')).items() if n>1))

def analyze_module(row, stem, commands):
    path = ROOT / row['file'] if row.get('file') else None
    if path and path.is_file():
        try:
            payload = decompress_module(row, path, stem)
            elf(row, payload, stem)
        except (ValueError, OSError) as exc:
            row['error'] = str(exc)
    else:
        row.setdefault('error', 'No readable regular file available for ELF analysis')
    classify(row, commands)
    row['linker_evidence_details'] = json.dumps(row['linker_evidence'], ensure_ascii=False)
    return row

def module_mapping(device, repo, loaded_file, loaded_notes):
    index = defaultdict(list)
    repo_index = defaultdict(list)
    for row in device:
        if row.get('name'):
            index[row['name']].append(row)
    for row in repo:
        if row.get('name'):
            repo_index[row['name']].append(row)
    mapping = []
    for line in loaded_file.read_text().splitlines() if loaded_file.exists() else []:
        match = re.match(r'^([A-Za-z0-9_]+)\s+[0-9]+\s+[0-9]+\s+', line)
        if not match:
            continue
        name = match[1]
        device_rows = index[name]
        repo_rows = repo_index[name]
        status = {0:'NO_INSTALLED_CANDIDATE', 1:'ONE_INSTALLED_CANDIDATE'}.get(len(device_rows), 'AMBIGUOUS')
        note = loaded_notes.get(name, {})
        loaded_id = note.get('build_id')
        id_match = 'UNVERIFIABLE'
        if loaded_id and len(device_rows) == 1 and device_rows[0].get('build_ids'):
            id_match = 'MATCH' if loaded_id in device_rows[0]['build_ids'] else 'MISMATCH'
        mapping.append(dict(name=name, status=status, live_gnu_build_id=loaded_id,
                            installed_gnu_build_ids=' | '.join(r.get('elf_build_id','') for r in device_rows),
                            live_installed_build_id_comparison=id_match, live_notes_path=note.get('notes_path'), device_paths=' | '.join(row['path'] for row in device_rows),
                            repository_paths=' | '.join(row['path'] for row in repo_rows),
                            repository_rpm=' | '.join(row['rpm'] for row in repo_rows),
                            device_classification=' | '.join(row['classification'] for row in device_rows),
                            repository_device_match=' | '.join(row.get('repository_identity', '') for row in device_rows),
                            installed_sha256=' | '.join(row.get('raw_sha256','') for row in device_rows),
                            proc_modules_evidence=rel(loaded_file), proc_modules_raw=line))
    return mapping

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-build-id', default=None)
    parser.add_argument('--installed', type=Path, default=Path('evidence/runtime/installed-modules.json'))
    parser.add_argument('--loaded', type=Path, default=Path('evidence/runtime/loaded-list.out'))
    parser.add_argument('--command-index', type=Path, default=Path('evidence/build/artifact-linker-index.json'))
    parser.add_argument('--rpm', type=Path, nargs='*')
    args = parser.parse_args()
    rpm_paths = args.rpm if args.rpm is not None else sorted((ROOT/'evidence/repository/rpms').glob('*.armv7l.rpm'))
    inputs = [ROOT / p for p in rpm_paths if 'debugsource-' not in p.name]
    runtime_json = ROOT / '01_runtime_kernel.json'
    runtime_id = args.runtime_build_id or (
        json.loads(runtime_json.read_text())['kernel']['notes']['gnu_build_id'] if runtime_json.exists() else None
    )
    module_commands = defaultdict(list)
    if (ROOT/args.command_index).is_file():
        for entry in json.loads((ROOT/args.command_index).read_text()):
            module_commands[(entry['rpm'], entry['path'])].append(entry['evidence'])
    quiet_path = ROOT / 'evidence/build/module-final-commands.json'
    quiet = defaultdict(list)
    if quiet_path.is_file():
        for entry in json.loads(quiet_path.read_text())['quiet_link_observations']:
            quiet[(entry['package_rpm'].removesuffix('.rpm'), entry['payload_path'])].append(entry)
    selections = llvm_selections()
    rows, extraction = [], []
    repo_data = ROOT / '02_repository_identity.json'
    rpm_receipts = {entry['rpm_path']: entry for entry in json.loads(repo_data.read_text())['selected_rpms']} if repo_data.is_file() else {}
    for rpm in inputs:
        try:
            receipt = rpm_receipts.get(rel(rpm))
            if receipt is None or not (receipt['metadata_checksum_verification']=='PASS' and
                                       receipt['rpm_digest_verification']=='PASS' and
                                       sha(rpm)==receipt['sha256']==receipt['metadata_checksum']):
                raise ValueError('RPM has no matching verified checksum receipt')
            members, status = unpack(rpm)
            rows.extend(members)
            extraction.append(status)
        except (ValueError, OSError) as exc:
            extraction.append(dict(rpm=rel(rpm), exit_status=1, error=str(exc)))
    binary_rows = [scan_binary(row, runtime_id) for row in rows if row['category'] == 'kernel_binary']
    repo = []
    excluded = []
    for row in rows:
        if row['category'] == 'module' and row['file_type'] == 'file':
            stem = 'modules/repository/'+row['rpm']+'/'+row['path'].lstrip('/')
            row['scope'] = 'repository'
            row['rpm_ownership'] = row['rpm']
            row['quiet_build_observations'] = quiet[row['rpm'], row['path']]
            repo.append(analyze_module(row, stem, eligible_commands(row, module_commands)+quiet_indications(row, selections)))
        elif row['category'] in ('module','debug_module','module_outside_release'):
            excluded.append(row)
    repo_paths = defaultdict(list)
    for row in repo:
        repo_paths[module_key(row['path'])].append(row)
    device = []
    installed = ROOT / args.installed
    installed_input = json.loads(installed.read_text()) if installed.exists() else {'modules': []}
    device_excluded = []
    for record in installed_input.get('files', []):
        row = dict(record, scope='device', category='module', raw_sha256=record.get('sha256'),
                   file=record.get('local_file'), file_type='file' if record['type']=='regular' else record['type'],
                   rpm_ownership=' | '.join(f'{owner["name"]}-{owner["version"]}-{owner["release"]}.{owner["architecture"]}'
                                            for owner in record.get('rpm_owners', [])) or 'UNOWNED_IN_ACTIVE_DB')
        if row['file_type'] != 'file':
            device_excluded.append(row)
            continue
        if row.get('file') and row.get('raw_sha256') != sha(ROOT/row['file']):
            row['error'] = 'Transported device file differs from device SHA256'
            row.pop('file')
        matches = [r for r in repo_paths[module_key(row['path'])]
                   if row.get('raw_sha256') and row['raw_sha256'] == r.get('raw_sha256')]
        row['repository_identity'] = ('EXACT_PATH_AND_SHA256' if len(matches) == 1 else 'AMBIGUOUS'
                                      if matches else 'SHA256_MISMATCH' if repo_paths[module_key(row['path'])]
                                      else 'NO_REPOSITORY_PATH')
        if len(matches) == 1:
            row['repository_rpm'] = matches[0]['rpm']
            row['repository_path'] = matches[0]['path']
            row['quiet_build_observations'] = matches[0]['quiet_build_observations']
        stem = 'modules/device/'+row['path'].lstrip('/')
        commands = (eligible_commands(matches[0], module_commands)+quiet_indications(row, selections)
                    if len(matches) == 1 else [])
        device.append(analyze_module(row, stem, commands))
    loaded_notes_path = (ROOT/args.loaded).with_name('loaded-modules.json')
    notes = {row['name']: row for row in json.loads(loaded_notes_path.read_text())['modules']} if loaded_notes_path.is_file() else {}
    mapping = module_mapping(device, repo, ROOT/args.loaded, notes)
    for row in repo:
        row['device_path_sha256_matches'] = ' | '.join(dev['path'] for dev in device
            if dev.get('repository_path') == row['path'] and dev.get('repository_rpm') == row['rpm'])
    base_coverage = {'repository': compute_coverage(repo, bool(inputs)), 'device':compute_coverage(device, installed.exists())}
    base_coverage.update(repository_excluded=[{k:row.get(k) for k in ('path','rpm','category','file_type','symlink_target')}
                                              for row in excluded],
                         device_excluded=device_excluded, runtime_loaded=len(mapping),
                         live_module_build_id_counts=dict(Counter(row['live_installed_build_id_comparison'] for row in mapping)),
                         device_repo_mapping_counts=dict(Counter(r['repository_identity'] for r in device)),
                         repository_from_filelists_expected=59,
                         repository_expected_inventory_met=len(repo)==59,
                         release=RELEASE,
                         denominator_rule='All regular target-release .ko payload paths, including compressed files; distinct paths and package instances retained; file symlinks and debug sidecars listed separately.')
    dump('03_kernel_linker_evidence.json', dict(binaries=binary_rows, extraction=extraction, runtime_build_id=runtime_id))
    dump('evidence/modules/module-analysis.json', dict(repository=repo, device=device, exclusions=excluded))
    dump('05_kernel_module_coverage.json', base_coverage)
    write_csv('03_kernel_binary_inventory.csv', binary_rows, ['rpm','path','file_type','payload_size','file','raw_sha256',
        'file_result','extraction','elf_class','elf_data','elf_type','elf_machine','elf_build_id','elf_sha256','compiler',
        'linker_classification','readelf','file_evidence'])
    for row in repo+device:
        quiet_events = row.get('quiet_build_observations', [])
        row['quiet_link_locations'] = ' | '.join(f'{x["event"]["evidence"]}:{x["event"]["line"]}' for x in quiet_events)
        row['quiet_link_raw'] = ' | '.join(x['event']['raw'] for x in quiet_events)
    write_csv('05_kernel_module_inventory.csv', repo+device, ['scope','path','file_type','rpm','rpm_ownership',
        'repository_rpm','repository_path','repository_identity','device_path_sha256_matches','raw_sha256','elf_sha256',
        'elf_class','elf_data','elf_type','elf_machine','elf_flags','elf_build_id','name','vermagic','vermagic_release_match',
        'compiler','parsed','classification','confidence','proves_final_link','reason','evidence_type','evidence_location',
        'raw_evidence','linker_evidence_details','quiet_link_locations','quiet_link_raw','readelf','file','representative_elf'])
    write_csv('05_loaded_module_mapping.csv', mapping, ['name','status','device_paths','repository_paths',
        'repository_rpm','device_classification','repository_device_match','installed_sha256','live_gnu_build_id','installed_gnu_build_ids',
        'live_installed_build_id_comparison','live_notes_path','proc_modules_evidence','proc_modules_raw'])
    print(json.dumps({scope:base_coverage[scope] for scope in ('repository','device')}, indent=2))
    if not extraction or any(item['exit_status'] != 0 for item in extraction):
        raise SystemExit(2)

if __name__ == '__main__':
    main()
