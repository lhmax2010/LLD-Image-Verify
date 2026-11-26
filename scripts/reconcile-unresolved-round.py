#!/usr/bin/env python3
"""Apply supplemental linker and prebuilt evidence to the archived unresolved rows."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read_tsv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def load_json(path):
    return json.loads(path.read_text())


def save_tsv(path, rows):
    with path.open('w', newline='') as stream:
        output = csv.DictWriter(stream, list(rows[0]), delimiter='\t')
        output.writeheader()
        output.writerows(rows)


def bfd_match(result):
    image = result['image']['sha256_without_debug_crc']
    return image == result['bfd']['sha256_without_debug_crc'] and image != result['lld']['sha256_without_debug_crc']


def read_proofs(proofs, run):
    evidence = {}
    for arch in ('aarch64', 'armv7l'):
        ref = f'glibc/{run}/{arch}/result.json'
        glibc = load_json(proofs / ref)
        if glibc['image_sha256'] != glibc['rpm_elf_sha256'] or 'GNU ld' not in glibc['linker']:
            raise ValueError(ref)
        evidence[glibc['image_sha256']] = ('gnu-ld-confirmed', 'glibc original link and RPM identity', ref)
        for name in ('bzip2', 'zip'):
            ref = f'{name}/{run}/{arch}/results.json'
            results = load_json(proofs / ref)
            log = (proofs / ref).with_name('build.log').read_text()
            if 'GNU ld (GNU Binutils) 2.43' not in log or 'LLD 22.1.8' not in log:
                raise ValueError(f'Missing replay linker versions in {name}/{run}/{arch}')
            bin_results = [results] if name == 'bzip2' else results.values()
            for result in bin_results:
                if not isinstance(result, dict):
                    continue
                if not bfd_match(result):
                    raise ValueError(ref)
                evidence[result['image']['sha256']] = ('gnu-ld-confirmed', 'bfd 2.43 ELF replay except debug CRC', ref)
        ref = f'dart-{arch}.json'
        dart = load_json(proofs / ref)
        if not all(dart[key] for key in ('build_id_matches', 'tpk_member_matches', 'dart_symbols')):
            raise ValueError(ref)
        evidence[dart['elf_sha256']] = ('dart-aot-elf-writer', 'Dart Build ID recomputation and TPK match', ref)
    return evidence


def count_groups(rows, field):
    return {name: Counter(r['classification'] for r in rows if r[field] == name)
            for name in sorted({r[field] for r in rows})}


def reconcile(args):
    summary = {}
    leftovers = set()
    voice = {row['sha256']: row for row in read_tsv(args.proofs / 'voice-source-provenance.tsv')
             if row['elf_byte_match'] == 'True'}
    for run in ('latest', 'qb1234653'):
        files = read_tsv(args.statistics / run / 'elf-results.tsv')
        proofs = read_proofs(args.proofs, run)
        unknown = [row for row in files if row['classification'] == 'unresolved']
        applied = []
        leftover = []
        evidence_digests = set()
        for row in unknown:
            digest = row['sha256']
            if digest in proofs:
                row['classification'], method, ref = proofs[digest]
                evidence_digests.add(digest)
            elif digest in voice:
                method = 'prebuilt source RPM member byte match; original linker unknown'
                ref = 'voice-source-provenance.tsv'
            else:
                method, ref = 'original link trace or controlled replay needed', ''
            entry = {key: row[key] for key in ('image', 'partition', 'path', 'machine', 'rpm', 'source',
                     'source_commit', 'sha256', 'build_id', 'debuglink', 'debug_crc', 'runtime_rpm_url',
                     'classification')}
            entry.update(method=method, evidence_file=ref)
            applied.append(entry)
            if row['classification'] == 'unresolved':
                leftover.append(entry)
        if evidence_digests != set(proofs):
            raise ValueError(f'{run}: orphaned proof digest')
        save_tsv(args.proofs / f'{run}-follow-up.tsv', applied)
        save_tsv(args.proofs / f'{run}-remaining.tsv', leftover)
        leftovers.update(row['sha256'] for row in leftover)
        native = [row for row in files if row['classification'] != 'static-archive']
        summary[run] = {
            'instances': Counter(row['classification'] for row in native),
            'by_image': count_groups(native, 'image'),
            'by_repository': count_groups(native, 'repository'),
            'remaining_by_source': Counter(row['source'] for row in leftover),
            'remaining_unique_sha256': len({row['sha256'] for row in leftover}),
            'remaining_prebuilt_voice_instances': sum(row['sha256'] in voice for row in leftover),
        }
    summary['remaining_unique_sha256_across_rounds'] = len(leftovers)
    (args.proofs / 'updated-counts.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    for name, run in summary.items():
        if isinstance(run, dict):
            print(name, run['instances'], run['remaining_unique_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--statistics', type=Path, required=True)
    parser.add_argument('--proofs', type=Path, required=True)
    reconcile(parser.parse_args())
