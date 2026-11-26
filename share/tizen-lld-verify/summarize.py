"""Produce the full ELF and RPM audit tables from the raw image evidence."""
from collections import Counter, defaultdict
import csv
import gzip
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

from config import SOURCES, UNIFIED, WORK
PARTITIONS = {
    'boot': '/boot', 'hal': '/hal', 'modules': '/lib/modules', 'rootfs': '',
    'system-data': '/opt', 'ramdisk': '/mnt/initrd', 'ramdisk-recovery': '/mnt/initrd-recovery',
}
LLD = {'lld-confirmed', 'lld-layout'}
OTHER = {'gnu-ld-confirmed', 'other-linker-confirmed', 'not-lld-22.1.8', 'gnu-ld-like-layout'}

def load_inventory(profiles):
    image_rpms = {}
    wanted = set()
    for profile in sorted(profiles):
        folder = WORK / 'images' / profile
        entries = {}
        for line in next(folder.glob('*.packages')).read_text().splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) >= 2:
                name = ' '.join(fields[:2])
                source, _, commit = (fields[2] if len(fields) == 3 else '').partition('#')
                entries[name] = (source, commit)
                wanted.add((name, fields[2] if len(fields) == 3 else ''))
        image_rpms[folder.name] = entries
    locations = {}
    owners = defaultdict(set)
    for repo in ('unified', 'base'):
        wanted_ids = {}
        with gzip.open(WORK / 'raw' / f'{repo}-primary.xml.gz') as f:
            for p in ET.parse(f).getroot():
                v = p.find('{*}version').attrib
                name = f"{p.findtext('{*}name')}.{p.findtext('{*}arch')} {v['ver']}-{v['rel']}"
                vcs = v.get('vcs', '')
                if (name, vcs) not in wanted:
                    continue
                path = p.find('{*}location').get('href')
                wanted_ids[p.findtext('{*}checksum')] = (name, vcs)
                locations.setdefault((name, vcs), (repo, SOURCES[repo] + 'repos/standard/packages/' + path))
        with gzip.open(WORK / 'raw' / f'{repo}-filelists.xml.gz') as f:
            for p in ET.parse(f).getroot():
                if p.get('pkgid') in wanted_ids:
                    for entry in p.findall('{*}file'):
                        if entry.get('type') not in ('dir','ghost'):
                            owners[entry.text].add(wanted_ids[p.get('pkgid')][0])
    return image_rpms, locations, owners


def source_logs_for_kernel(image, paths):
    arch = 'aarch64' if 'aarch64' in image else 'armv7l'
    log = WORK / 'buildlogs' / arch / 'linux-rpi.txt'
    text = log.read_text()
    validated = set(re.findall(r'LD \[M\]\s+(\S+\.ko)\b', text))
    log_root = UNIFIED + 'builddata/buildlogs/standard'
    if not re.search(r'^.*\+ export LLVM=1$', text, re.M):
        raise ValueError(f'No Kbuild LLVM=1 in {log}')
    return {p for p in paths if any(p.endswith('/' + m) or p.endswith('/' + m + '.xz') or p.endswith('/' + m + '.gz') or p.endswith('/' + m + '.zst') for m in validated)}, f'{log_root}/{arch}/succeeded/linux-rpi.buildlog.txt'


def kernel_row(image, rpms):
    name = 'Image' if 'aarch64' in image else 'zImage'
    arch = 'aarch64' if name == 'Image' else 'arm'
    path = WORK / 'extracted' / image / 'boot' / name
    contents = path.read_bytes()
    payload = contents
    if name == 'zImage':
        for match in re.finditer(b'\x1f\x8b\x08', contents):
            try:
                window = zlib.decompress(contents[match.start():], 31)
                if len(window) > 1_000_000:
                    payload = window
                    break
            except zlib.error:
                continue
    version = next(x.decode() for x in re.findall(rb'Linux version [\x20-\x7e]{15,255}', payload)
                   if b'LLD ' in x and b'#1' in x)
    package = next(p for p in rpms if re.search(r'-linux-kernel\.', p))
    source, commit = rpms[package]
    return {'image': image, 'partition': 'boot', 'path': '/boot/' + name, 'kind': 'kernel-image',
            'machine': arch, 'linker': 'LLD', 'evidence': version, 'comments': '', 'build_id': '',
            'sha256': hashlib.sha256(contents).hexdigest(), 'rpm': package, 'source': source, 'source_commit': commit}


def get_debug(debug_results):
    matches = defaultdict(list)
    for file in debug_results:
        for line in file.read_text().splitlines():
            d = json.loads(line)
            matches[d['sha256']].append(d)
    return matches


def package_lookup(row, rpms, owners, sha_owners):
    if row['rpm']:
        return [val for val in row['rpm'].split('|') if val in rpms]
    path = row['path'].partition('!/')[0]
    if row['partition'].startswith('ramdisk'):
        path = path.removeprefix(PARTITIONS[row['partition']])
    alt = path.removeprefix('/usr') if path.startswith('/usr/') else '/usr' + path
    candidates = (owners[path] | owners[alt]) & rpms.keys()
    if not candidates and row['sha256']:
        candidates = sha_owners.get(row['sha256'], set()) & rpms.keys()
    return sorted(candidates)


@lru_cache
def glibc_uses_gnu_ld(arch):
    log = WORK / 'buildlogs' / 'base' / arch / 'glibc.buildlog.txt'
    return log.is_file() and re.search(r'checking version of .*bin/ld\.\.\. 2\.43, ok', log.read_text())


@lru_cache
def built_with_lld(arch, source):
    eligible = {'mesa', 'glib-networking', 'pulseaudio', 'systemd', 'chromium-efl'}
    package = source.rsplit('/', 1)[-1]
    if package not in eligible:
        return set(), ''
    log = WORK / 'buildlogs' / arch / f'{package}.txt'
    if not log.is_file():
        return set(), ''
    text = log.read_text()
    if package == 'chromium-efl':
        if not re.search(r'use_lld\s*=\s*true', text) or re.search(r'use_lld\s*=\s*false', text):
            return set(), ''
        targets = re.findall(r'\] (?:SOLINK|LINK) (\S+)', text)
    else:
        if not re.search(r'C linker for (?:the )?host machine: .*ld\.lld 22\.1\.8', text):
            return set(), ''
        targets = re.findall(r' Linking target (\S+)', text)
    url = UNIFIED + f'builddata/buildlogs/standard/{arch}/succeeded/{package}.buildlog.txt'
    return {Path(name).name for name in targets}, url


def classify(row, debug, module_paths, kernel_url):
    row['debug_matched'] = 'yes' if debug else ''
    row['debug_rpm'] = '|'.join(sorted({d['rpm'] for d in debug}))
    row['debug_path'] = '|'.join(sorted({d['debug_path'] for d in debug}))
    row['debug_comments'] = '|'.join(sorted({d['comments'] for d in debug if d['comments']}))
    observed = row['linker']
    row['classification'] = 'unresolved'
    if row['kind'] == 'archive':
        row['classification'] = 'static-archive'
        return
    known = {d['linker'] for d in debug if d['linker'] not in ('unknown','conflicting')}
    if observed not in ('unknown','conflicting'):
        known.add(observed)
    if len(known) > 1 or row['linker'] == 'conflicting':
        row['classification'] = 'conflicting'
        return
    if known:
        link = next(iter(known))
        row['classification'] = 'lld-confirmed' if link == 'LLD' else 'other-linker-confirmed'
        if observed == 'unknown':
            row['linker'] = link
            proof = [d for d in debug if d['linker'] == link]
            row['evidence'] = '|'.join(sorted({f"{x['evidence']} (debug CRC {x['crc']})" for x in proof}))
        return
    if row['kind'] == 'REL' and row['path'] in module_paths:
        row['classification'] = 'lld-confirmed'
        row['linker'] = 'LLD'
        row['evidence'] = 'Kbuild LLVM=1 + matching final LD [M] line: ' + kernel_url
        return
    # This excludes the version actually used by the QB, per lld/ELF/SyntheticSections.cpp.
    if row.get('version_parent') == 'yes':
        row['classification'] = 'not-lld-22.1.8'
        row['evidence'] = '.gnu.version_d has vd_cnt > 1'
        if row['source'] == 'platform/upstream/glibc':
            arch = {'aarch64':'aarch64','arm':'armv7l'}.get(row['machine'],'')
            if glibc_uses_gnu_ld(arch):
                row['classification'] = 'gnu-ld-confirmed'
                row['linker'] = 'GNU ld 2.43'
                row['evidence'] += '; glibc build log checks selected bin/ld version 2.43'
        return
    if row.get('load_flags') in ('R,RX,RW,RW','R,RX,RW') and int(row.get('relro_delta') or '0') > 0:
        row['classification'] = 'lld-layout'
        row['evidence'] = f"PT_LOAD {row['load_flags']}, PT_GNU_RELRO memsz-filesz={row['relro_delta']}"
        arch = {'arm': 'armv7l', 'aarch64': 'aarch64'}.get(row['machine'])
        if arch and row['repository'] == 'unified':
            targets, url = built_with_lld(arch, row['source'])
            if Path(row['path']).name in targets:
                row['classification'] = 'lld-confirmed'
                row['linker'] = 'LLD'
                row['evidence'] += ' plus matching link target and LLD setting in ' + url
    elif row.get('load_flags') == 'RX,RW' and row.get('relro_delta') == '0':
        row['classification'] = 'gnu-ld-like-layout'
        row['evidence'] = 'PT_LOAD RX,RW and PT_GNU_RELRO memsz=filesz'


def write_tsv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def run(profiles, debug_results):
    rpms, locations, owners = load_inventory(profiles)
    debugs = get_debug(debug_results)
    files = []
    sha_owners = defaultdict(set)
    for profile in sorted(profiles):
        file = WORK / 'observed' / f'{profile}.tsv'
        with file.open() as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        assert rows and all(None not in row and all(v is not None for v in row.values()) for row in rows), f'Incomplete {file}'
        assert len(rows) == len({(r['partition'], r['path']) for r in rows}), f'Duplicate paths in {file}'
        assert json.loads(file.with_name(file.stem+'-issues.json').read_text()) == [], file
        if '-boot-' in file.stem:
            rows.append(kernel_row(file.stem, rpms[file.stem]))
            modules, url = source_logs_for_kernel(file.stem, {row['path'] for row in rows if row['kind'] == 'REL'})
        else:
            modules, url = set(), ''
        for row in rows:
            row['module_log'] = url if row['path'] in modules else ''
            if row['sha256'] and row['rpm']:
                sha_owners[row['sha256']].update(row['rpm'].split('|'))
        files.extend(rows)
    columns = list(max(files, key=len))
    files = [{key: row.get(key, '') for key in columns} for row in files]
    pkg_bins = defaultdict(list)
    for row in files:
        src = rpms[row['image']]
        keys = package_lookup(row, src, owners, sha_owners)
        if keys:
            row['rpm'] = '|'.join(keys)
            row['source'] = '|'.join(sorted({src[k][0] for k in keys} - {''}))
            row['source_commit'] = '|'.join(sorted({src[k][1] for k in keys} - {''}))
        loc = [locations.get((k, '#'.join(src[k])), ('','')) for k in keys]
        row['repository'] = '|'.join(sorted({item[0] for item in loc} - {''}))
        row['runtime_rpm_url'] = '|'.join(sorted({item[1] for item in loc} - {''}))
        classify(row, debugs.get(row['sha256'], []),
                 {row['path']} if row['module_log'] else set(), row['module_log'])
        for k in keys:
            pkg_bins[(row['image'], k)].append(row)
    package_rows = []
    for image, packages in rpms.items():
        for package, (source, commit) in sorted(packages.items()):
            binaries = pkg_bins[(image, package)]
            counts = Counter(x['classification'] for x in binaries)
            lld = sum(counts[k] for k in LLD)
            other = sum(counts[k] for k in OTHER)
            unknown = counts['unresolved'] + counts['conflicting']
            if lld and other:
                state = 'mixed'
            elif lld and unknown:
                state = 'has-lld-and-unresolved'
            elif other and unknown:
                state = 'has-non-lld-and-unresolved'
            elif lld:
                state = 'has-confirmed-lld' if counts['lld-confirmed'] else 'lld-layout-only'
            elif other:
                exact = counts['gnu-ld-confirmed'] + counts['other-linker-confirmed'] + counts['not-lld-22.1.8']
                state = 'has-confirmed-non-lld' if exact else 'gnu-ld-like-layout-only'
            elif unknown:
                state = 'unresolved'
            elif counts['static-archive']:
                state = 'archive-only'
            else:
                state = 'no-attributed-elf'
            repo, url = locations.get((package, '#'.join((source, commit))), ('',''))
            package_rows.append({'image': image, 'rpm': package, 'source': source, 'source_commit': commit,
                                 'repository': repo, 'runtime_rpm_url': url, 'classification': state,
                                 'lld_confirmed': counts['lld-confirmed'], 'lld_layout': counts['lld-layout'],
                                 'gnu_ld_confirmed': counts['gnu-ld-confirmed'],
                                 'other_linker_confirmed': counts['other-linker-confirmed'],
                                 'not_lld_22_1_8': counts['not-lld-22.1.8'],
                                 'gnu_ld_like': counts['gnu-ld-like-layout'],
                                 'unresolved': unknown, 'static_archives': counts['static-archive'],
                                 'example_path': binaries[0]['path'] if binaries else ''})
    write_tsv(WORK / 'elf-linker-audit.tsv', files)
    write_tsv(WORK / 'rpm-linker-audit.tsv', package_rows)
    output = {'images': {}, 'overall': {}}
    labels = sorted({f['classification'] for f in files})
    for name in rpms:
        chunk = [r for r in files if r['image']==name]
        out = output['images'][name] = {}
        out['elf'] = dict(Counter(r['classification'] for r in chunk))
        out['elf_without_owner'] = sum(not r['rpm'] for r in chunk)
        out['packages'] = dict(Counter(r['classification'] for r in package_rows if r['image']==name))
        out['debug_matched'] = sum(r['debug_matched']=='yes' for r in chunk)
    output['overall']['elf_occurrences'] = dict(Counter(r['classification'] for r in files))
    output['overall']['elf_unique_sha256'] = {label: len({r['sha256'] for r in files if r['classification']==label and r['sha256']}) for label in labels}
    output['overall']['elf_debug_matched'] = len({r['sha256'] for r in files if r['debug_matched']=='yes'})
    (WORK / 'summary.json').write_text(json.dumps(output, indent=2) + '\n')
    return output
