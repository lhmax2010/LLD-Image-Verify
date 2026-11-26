#!/usr/bin/env python3
"""Tie image ELF hashes to named link steps and summarize the remaining gaps."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
import config
import verify

WEAK = {'unresolved', 'lld-layout', 'gnu-ld-like-layout', 'not-lld-22.1.8'}
OTHER = {'gnu-ld-confirmed', 'other-linker-confirmed'}
INSTALL_TARGET = re.compile(r' -- Installing: (/.*)')
MESON = re.compile(r'(C(?:\+\+)? linker for (?:the )?host machine: .*?\b)(ld\.bfd|ld\.lld) ([\d.]+)')
MESON_LINK = re.compile(r'\] Linking target (\S+)')
EXPLICIT = re.compile(r'(?:^|\s)(?:/\S*/)?(?:[^\s/]*-)?(ld\.bfd|ld\.lld)(?=\s)|-fuse-ld=(bfd|lld)(?=\s)')
OUTPUT = re.compile(r'(?:^|\s)-o\s+[\'"]?([^\s\'";]+)')
CANONICAL_SO = re.compile(r'\.so(?:\.[\d.]+)?$')


def read_rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def tsv(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def arch_of(row):
    return 'aarch64' if 'aarch64' in row['image'] else 'armv7l'


def rpm_index(root, base, cache, name):
    old = root / 'raw' / f'{name}-primary.xml.gz'
    if old.is_file():
        path = old
    else:
        area = base + 'repos/standard/packages/'
        metadata = verify.fetch(area + 'repodata/repomd.xml', cache / f'{name}-repomd.xml')
        primary = ET.parse(metadata).find(".//{*}data[@type='primary']")
        path = verify.fetch(area + primary.find('{*}location').get('href'),
                            cache / f'{name}-primary.xml.gz', primary.findtext('{*}checksum'))
    result = {}
    with gzip.open(path) as f:
        for _, p in ET.iterparse(f, events=['end']):
            if not p.tag.endswith('}package'):
                continue
            version = p.find('{*}version')
            pkg = f"{p.findtext('{*}name')}.{p.findtext('{*}arch')} {version.get('ver')}-{version.get('rel')}"
            result[pkg, version.get('vcs')] = (
                base + 'repos/standard/packages/' + p.find('{*}location').get('href'),
                p.findtext('{*}checksum'))
            p.clear()
    return result


def exact_rpm(row, indexes, out):
    key = row['rpm'], row['source'] + '#' + row['source_commit']
    url, checksum = indexes[row['repository']][key]
    if row['runtime_rpm_url'] and url != row['runtime_rpm_url']:
        raise ValueError(f'Runtime RPM URL mismatch for {key}')
    return verify.fetch(url, out / row['repository'] / PurePosixPath(url).name, checksum), url, checksum


def file_digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load_log(root, cache, spec):
    repo, arch, name, url = spec
    local = root / 'buildlogs'
    candidates = ([local / 'base' / arch / f'{name}.buildlog.txt'] if repo == 'base'
                  else [local / arch / f'{name}.txt', root / 'follow-up' / 'logs' / arch / f'{name}.txt'])
    for path in candidates:
        if path.is_file():
            return path
    path = cache / repo / arch / f'{name}.txt.gz'
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.part')
    try:
        with urlopen(url, timeout=25) as response:
            if int(response.headers.get('Content-Length') or 0) > 140_000_000:
                return 'exceeds 140 MB log collection limit'
            with gzip.open(temp, 'wb', compresslevel=3) as f:
                size = 0
                for block in iter(lambda: response.read(262144), b''):
                    size += len(block)
                    if size > 140_000_000:
                        return 'exceeds 140 MB log collection limit'
                    f.write(block)
        temp.replace(path)
        return path
    except (HTTPError, URLError, OSError) as exc:
        return str(exc)
    finally:
        temp.unlink(missing_ok=True)


def read_log(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f, 1):
            yield i, line.rstrip()


def log_records(path):
    meson, links, installed, selectors = [], defaultdict(list), defaultdict(list), []
    for i, line in read_log(path):
        if match := MESON.search(line):
            meson.append((match[2], match[3], i, line))
        if match := MESON_LINK.search(line):
            links[PurePosixPath(match[1]).name].append(('', '', i, line))
        if match := INSTALL_TARGET.search(line):
            installed[PurePosixPath(match[1]).name].append((i, line))
        explicit = EXPLICIT.search(line)
        out = OUTPUT.search(line)
        if explicit and out and not re.search(r'\s-(?:c|S|E)(?:\s|$)', line):
            linker = explicit[1] or 'ld.' + explicit[2]
            links[PurePosixPath(out[1]).name].append((linker, '', i, line))
        if re.search(r'checking if the linker .* is GNU ld\.\.\. yes|'
                     r'checking version of .*bin/ld\.\.\. [\d.]+, ok|'
                     r'CLANG_DEFAULT_LINKER=|Building with LLVM|Using LLD', line):
            selectors.append((i, line[:1500]))
    return meson, links, installed, selectors


def actual_target(row, records):
    basename = PurePosixPath(row['path']).name
    meson, links, installed, _ = records
    for linker, version, number, line in links.get(basename, []):
        if linker:
            return linker, f'{linker} (final link command)', [number], [line]
    selectors = {(x[0], x[1]) for x in meson}
    if len(selectors) == 1:
        linker, version = next(iter(selectors))
        targets = links.get(basename, [])
        if not targets and basename in installed:
            normalized = CANONICAL_SO.sub('.so', basename)
            targets = links.get(normalized, [])
        display = {'ld.bfd': 'GNU ld.bfd', 'ld.lld': 'LLD'}[linker]
        for identity, _, number, line in targets:
            if not identity:
                return (linker, f'{display} {version}', [meson[-1][2], number],
                        [meson[-1][3], line])
    return None


def homescreen(rows, runtime, out):
    for arch in ('aarch64', 'armv7l'):
        artifacts = [r for r in rows if arch_of(r) == arch
                     and r['path'].startswith('/usr/apps/org.tizen.homescreen/')]
        runtime_arch = runtime.get(arch)
        if not artifacts or not runtime_arch:
            continue
        rpm, base_row, tpk_path, url, rpm_sha = runtime_arch
        tpk = out / f'homescreen-{arch}.tpk'
        verify.extract_one(rpm, tpk_path, tpk)
        with ZipFile(tpk) as z:
            files = {name.removeprefix('./'): name for name in z.namelist()}
            for row in artifacts:
                member = row['path'].split('/usr/apps/org.tizen.homescreen/', 1)[1]
                if member not in files:
                    continue
                with z.open(files[member]) as f:
                    digest = hashlib.file_digest(f, 'sha256').hexdigest()
                if digest == row['sha256']:
                    for col in ('rpm', 'source', 'source_commit', 'repository'):
                        row[col] = base_row[col]
                    row.update(runtime_rpm_url=url, runtime_rpm_sha256=rpm_sha,
                               rpm_match='image SHA256 = packaged TPK member SHA256',
                               trace=f'{tpk_path}!/{member}')


def load_homescreen(root, rows, indexes, output):
    sources = {}
    for arch in ('aarch64', 'armv7l'):
        folder = root / 'images' / f'tizen-headed-{arch}'
        manifest = next(folder.glob('*.packages'), None)
        if not manifest:
            continue
        candidates = verify.installed_rpms(manifest, arch)
        if 'org.tizen.homescreen' not in candidates:
            continue
        version, vcs = candidates['org.tizen.homescreen']
        project, sha = vcs.split('#')
        row = dict(rpm=f'org.tizen.homescreen.{arch} {version}', source=project,
                   source_commit=sha, repository='unified', runtime_rpm_url='')
        rpm, url, digest = exact_rpm(row, indexes, output / 'rpms')
        package_files = subprocess.check_output(['rpm', '-qpl', rpm], text=True, stderr=subprocess.DEVNULL)
        tpk_path, = (line for line in package_files.splitlines() if line.endswith('.tpk'))
        sources[arch] = (rpm, row, tpk_path, url, digest)
    homescreen(rows, sources, output)


def build_logs(root, output, rows, sources, workers, all_base):
    aliases = {('unified', 'sppc'): 'push',
               ('unified', 'homescreen-app'): 'org.tizen.homescreen',
               ('unified', 'stt-engine-default'): 'org.tizen.stt-engine-default',
               ('unified', 'tts-engine-default'): 'org.tizen.tts-engine-default',
               ('unified', 'vc-engine-default'): 'org.tizen.vc-engine-default',
               ('unified', 'hand-drawing-engine'): 'pen-wave'}
    wanted = {}
    for row in rows:
        if row['classification'] not in WEAK or not row['repository'] or not row['source']:
            continue
        if row['repository'] == 'base' and not all_base and row['classification'] != 'unresolved':
            continue
        key = row['repository'], arch_of(row), row['source']
        if key not in wanted:
            repo, arch, source = key
            name = source.rsplit('/', 1)[-1]
            name = aliases.get((repo, name), name)
            wanted[key] = repo, arch, name, f'{sources[repo]}builddata/buildlogs/standard/{arch}/succeeded/{name}.buildlog.txt'

    def collect(item):
        key, log = item
        path = load_log(root, output / 'logs', log)
        if isinstance(path, str):
            return key, log[3], path, None
        return key, log[3], file_digest(path), log_records(path)

    gathered = {}
    index = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for key, url, digest, records in executor.map(collect, sorted(wanted.items())):
            gathered[key] = url, records
            index.append(dict(repository=key[0], arch=key[1], source=key[2], url=url,
                              cached_sha256_or_error=digest, available=bool(records)))
    tsv(output / 'logs-index.tsv', index)
    return gathered


def meaningful_path(row):
    path = row['path']
    for prefix in ('/mnt/initrd/', '/mnt/initrd-recovery/'):
        if path.startswith(prefix):
            return '/' + path.removeprefix(prefix)
    return path


def check_exact_file(row, indexes, output, expected):
    if row['rpm_match']:
        return True
    if not row['rpm'] or '|' in row['rpm'] or row['kind'] not in {'EXEC', 'DYN', 'REL'}:
        return False
    key = (row['repository'], row['rpm'], row['source_commit'], row['sha256'])
    if key not in expected:
        rpm, _, rpm_digest = exact_rpm(row, indexes, output / 'rpms')
        artifact = output / (row['sha256'] + '.check')
        try:
            verify.extract_one(rpm, meaningful_path(row), artifact)
            expected[key] = rpm_digest, file_digest(artifact) == row['sha256']
        except ValueError:
            expected[key] = rpm_digest, False
        finally:
            artifact.unlink(missing_ok=True)
    rpm_digest, matched = expected[key]
    if matched:
        row.update(runtime_rpm_sha256=rpm_digest, rpm_match='image SHA256 = RPM ELF SHA256')
    return matched


def trace_external_modules(root, rows, indexes, source, output, checked):
    traces = []
    for arch in ('aarch64', 'armv7l'):
        profile = f'tizen-boot-{arch}-rpi'
        modules = [r for r in rows if r['image'] == profile and r['kind'] == 'REL'
                   and '/extra/' in r['path'] and r['classification'] in WEAK]
        if not modules:
            continue
        package = 'linux-tizen-modules-rpi4'
        manifest = next((root / 'images' / profile).glob('*.packages'))
        identity = verify.installed_rpms(manifest, arch).get(package)
        if not identity:
            continue
        version, vcs = identity
        project, sha = vcs.split('#', 1)
        url = source + f'builddata/buildlogs/standard/{arch}/succeeded/linux-tizen-modules.buildlog.txt'
        path = load_log(root, output / 'logs', ('unified', arch, 'linux-tizen-modules', url))
        if isinstance(path, str):
            print(f'{arch}: external modules log unavailable: {path}', file=sys.stderr)
            continue
        targets = {}
        links = {}
        selected = None
        in_rpi4 = False
        for number, line in read_log(path):
            if re.search(r'\+ export LLVM=1$', line):
                selected = number, line
            elif re.search(r'\+ (?:unset LLVM|export LD=)', line):
                selected = None
                in_rpi4 = False
            if match := re.search(r'\+ make -C kernel KERNELDIR=(\S+)', line):
                in_rpi4 = match[1].rstrip('/').endswith(('kernel-devel-arm64-rpi4', 'kernel-devel-arm-rpi4'))
                links = {}
            if selected and in_rpi4:
                if match := re.search(r'\bLD \[M\]\s+(\S+\.ko)$', line):
                    links[PurePosixPath(match[1]).name] = [selected, (number, line)]
                if match := re.search(r'\bINSTALL\s+.*?(/lib/modules/[^ ]+/extra/\S+\.ko)$', line):
                    key = PurePosixPath(match[1]).name
                    if key in links:
                        targets[match[1]] = [*links[key], (number, line)]
        for row in modules:
            notes = targets.get(row['path'])
            if notes is None:
                continue
            candidate = dict(row, rpm=f'{package}.{arch} {version}', source=project,
                             source_commit=sha, repository='unified', runtime_rpm_url='')
            key = candidate['rpm'], vcs
            candidate['runtime_rpm_url'] = indexes['unified'][key][0]
            if not check_exact_file(candidate, indexes, output, checked):
                continue
            numbers = ','.join(str(n) for n, _ in notes)
            candidate.update(linker='LLD', classification='lld-confirmed', trace_url=url,
                             trace_lines=numbers,
                             trace='Kbuild LLVM=1, named LD [M], exact RPi install path, matching RPM SHA256')
            row.update(candidate)
            traces.append(dict(image=row['image'], path=row['path'], sha256=row['sha256'],
                               linker='LLD', rpm=row['rpm'], url=url, lines=numbers,
                               quoted_lines=' | '.join(line for _, line in notes)))
    return traces


def reason(row):
    path = row['path']
    source = row['source'].rsplit('/', 1)[-1]
    if row['classification'] not in WEAK:
        return ''
    if source in {'homescreen-app', 'sppc'}:
        return 'packaged application payload; requires original producer link record'
    if source == 'tizen-debug' and '.debug' in path:
        return 'repackaged debug file; requires identity comparison to the original ELF/debuginfo'
    if source == 'linux-rpi' and '/extra/' in path:
        return 'extra kernel module; missing the exact final module link line in the main kernel log'
    if row['classification'] == 'not-lld-22.1.8':
        return 'version-parent evidence rules out LLD 22.1.8; alternative linker remains open'
    if source == 'nnfw':
        return 'LLD-like layout and Clang selected; final link invocation is absent from public log'
    if row['classification'] == 'gnu-ld-like-layout':
        return 'GNU ld-like program headers; linker choice needs explicit target or matched marker'
    if not row['debuglink'] and not row['build_id']:
        return 'no debug identity in runtime ELF and no direct linker evidence'
    if row['debug_matched']:
        return 'paired debuginfo has no linker marker and no conclusive target proof'
    return 'public debuginfo could not be paired and no conclusive target proof'


def summarize_results(rows, rpm_rows, output):
    by_image = defaultdict(Counter)
    by_repo = defaultdict(Counter)
    by_rpm = defaultdict(list)
    distinct = defaultdict(set)
    for row in rows:
        classification = row['classification']
        by_image[row['image']][classification] += 1
        by_repo[row['repository'] or 'unattributed'][classification] += 1
        if row['sha256']:
            distinct[classification].add(row['sha256'])
        if row['rpm'] and '|' not in row['rpm']:
            by_rpm[row['rpm'], row['source'], row['source_commit']].append(row)
    for row in rpm_rows:
        by_rpm.setdefault((row['rpm'], row['source'], row['source_commit']), [])
    rpm_output = []
    for (rpm, source, sha), files in sorted(by_rpm.items()):
        native = [r for r in files if r['classification'] != 'static-archive']
        statuses = {r['classification'] for r in native}
        lld, other = 'lld-confirmed' in statuses, bool(statuses & OTHER)
        if lld and other:
            status = 'confirmed-mixed'
        elif statuses == {'lld-confirmed'}:
            status = 'confirmed-lld-only-observed'
        elif lld:
            status = 'confirmed-lld-and-open'
        elif statuses and statuses <= OTHER:
            status = 'confirmed-other-only-observed'
        elif other:
            status = 'confirmed-other-and-open'
        elif statuses:
            status = 'no-final-linker-confirmation'
        else:
            status = 'no-attributed-native-elf'
        rpm_output.append(dict(rpm=rpm, source=source, source_commit=sha, status=status,
                               elf_instances=len(native),
                               distinct_elf_sha256=len({r['sha256'] for r in native}),
                               evidence_counts=json.dumps(Counter(r['classification'] for r in native),
                                                          sort_keys=True)))
    tsv(output / 'rpm-results.tsv', rpm_output)
    summary = dict(images=by_image, repository=by_repo,
                   instances=Counter(r['classification'] for r in rows),
                   distinct_sha256_per_class={k: len(v) for k, v in distinct.items()},
                   distinct_native_sha256=len(set().union(*(v for k, v in distinct.items()
                                                           if k != 'static-archive'))),
                   rpm=Counter(r['status'] for r in rpm_output),
                   remaining_reasons=Counter(r['remaining_reason'] for r in rows if r['remaining_reason']))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: summary[k] for k in ('instances', 'rpm', 'remaining_reasons')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--unified', default=config.UNIFIED)
    parser.add_argument('--base', default=config.BASE)
    parser.add_argument('--all-base-logs', action='store_true')
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    options = parser.parse_args()
    root, out = options.audit_dir.resolve(), options.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = read_rows(root / 'elf-linker-audit.tsv')
    rpm_rows = read_rows(root / 'rpm-linker-audit.tsv')
    sources = {'base': options.base.rstrip('/') + '/', 'unified': options.unified.rstrip('/') + '/'}
    indexes = {name: rpm_index(root, url, out, name) for name, url in sources.items()}
    for row in rows:
        row.update(original_classification=row['classification'], runtime_rpm_sha256='',
                   rpm_match='', trace='', trace_url='', trace_lines='', remaining_reason='')
    load_homescreen(root, rows, indexes, out)
    logs = build_logs(root, out, rows, sources, options.jobs, options.all_base_logs)
    checked = {}
    traces = trace_external_modules(root, rows, indexes, sources['unified'], out, checked)
    for row in rows:
        log_url, records = logs.get((row['repository'], arch_of(row), row['source']), ('', None))
        if records and row['classification'] in WEAK:
            target = actual_target(row, records)
            if target and check_exact_file(row, indexes, out, checked):
                linker, display, line_numbers, lines = target
                if row['classification'] == 'not-lld-22.1.8' and linker == 'ld.lld':
                    row['classification'] = 'conflicting'
                else:
                    row['classification'] = 'lld-confirmed' if linker == 'ld.lld' else 'gnu-ld-confirmed'
                row.update(linker=display, trace_url=log_url,
                           trace_lines=','.join(map(str, line_numbers)),
                           trace='named link step and byte-identical runtime RPM')
                traces.append(dict(image=row['image'], path=row['path'], sha256=row['sha256'],
                                   linker=display, rpm=row['rpm'], url=log_url,
                                   lines=row['trace_lines'], quoted_lines=' | '.join(lines)))
        row['remaining_reason'] = reason(row)
        if not row['trace_url'] and row['remaining_reason']:
            row['trace_url'] = log_url
    tsv(out / 'elf-results.tsv', rows)
    tsv(out / 'new-link-traces.tsv', traces)
    tsv(out / 'open-artifacts.tsv', [r for r in rows if r['remaining_reason']])
    summarize_results(rows, rpm_rows, out)


if __name__ == '__main__':
    main()
