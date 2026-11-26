#!/usr/bin/env python3
"""Combine the image audit receipts and exact Toybox replays."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DIGEST_KEY = ('image', 'partition', 'path', 'sha256')


def read_tsv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def write_tsv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def grouped_counts(rows, column):
    totals = defaultdict(Counter)
    for row in rows:
        totals[row[column] or 'unattributed'][row['classification']] += 1
    return dict(totals)


def consolidate(archive, output, revision, proof):
    inputs = archive / revision
    fixes = {tuple(row[f] for f in DIGEST_KEY): row for row in proof if row['snapshot'] == revision}
    files = read_tsv(inputs / 'elf-results.tsv')
    change_counts = Counter()
    changed_keys = set()
    for row in files:
        key = tuple(row[f] for f in DIGEST_KEY)
        if key not in fixes:
            continue
        if row['classification'] != 'unresolved' or fixes[key]['linker'] != 'GNU ld.bfd 2.43':
            raise ValueError(f'Inconsistent Toybox proof for {key}')
        row.update(classification='gnu-ld-confirmed', linker=fixes[key]['linker'],
                   evidence=fixes[key]['evidence'],
                   trace='toybox-execution/' + fixes[key]['replay_log'],
                   remaining_reason='')
        changed_keys.add(key)
        change_counts[row['rpm'], row['source'], row['source_commit']] += 1
    if changed_keys != fixes.keys():
        raise ValueError(f'{revision}: some Toybox evidence could not be reconciled')
    rpms = read_tsv(inputs / 'rpm-results.tsv')
    changed_rpms = set()
    for row in rpms:
        key = row['rpm'], row['source'], row['source_commit']
        if key not in change_counts:
            continue
        counts = json.loads(row['evidence_counts'])
        if counts != {'unresolved': change_counts[key]}:
            raise ValueError(f'{revision}: unexpected original RPM classifications for {key}')
        row.update(status='confirmed-other-only-observed',
                   evidence_counts=json.dumps({'gnu-ld-confirmed': change_counts[key]}))
        changed_rpms.add(key)
    if changed_rpms != change_counts.keys():
        raise ValueError(f'{revision}: some Toybox RPMs could not be reconciled')
    native = [row for row in files if row['classification'] != 'static-archive']
    unresolved = [row for row in native if row['classification'] == 'unresolved']
    versions = Counter()
    for row in native:
        if row['classification'] == 'lld-confirmed':
            version = re.search(r'LLD (\d+\.\d+\.\d+)', row['evidence'])
            versions[version[1] if version else 'not-recorded-for-kernel-module'] += 1
    output.mkdir(parents=True, exist_ok=True)
    write_tsv(output / 'elf-results.tsv', files)
    write_tsv(output / 'rpm-results.tsv', rpms)
    write_tsv(output / 'unresolved.tsv', unresolved)
    open_classes = {'unresolved', 'not-lld-22.1.8', 'gnu-ld-like-layout', 'lld-layout'}
    write_tsv(output / 'open-evidence.tsv', [row for row in native if row['classification'] in open_classes])
    return {
        'native_file_instances': len(native),
        'unique_native_sha256': len({r['sha256'] for r in native}),
        'static_archive_instances': len(files) - len(native),
        'categories': Counter(r['classification'] for r in native),
        'by_image': grouped_counts(native, 'image'),
        'by_repository': grouped_counts(native, 'repository'),
        'rpm_count': len(rpms),
        'rpm_categories': Counter(r['status'] for r in rpms),
        'lld_version_instances': versions,
        'unresolved_unique_sha256': len({r['sha256'] for r in unresolved}),
        'unresolved_by_source': Counter(r['source'] for r in unresolved),
        'newly_confirmed_toybox_instances': len(changed_keys),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'evidence' / '2026-11-23')
    parser.add_argument('--output', type=Path, default=ROOT / 'statistics')
    args = parser.parse_args()
    proof = read_tsv(args.archive / 'toybox-execution' / 'confirmed-toybox-files.tsv')
    stats = {revision: consolidate(args.archive, args.output / revision, revision, proof)
             for revision in ('qb1234653', 'latest')}
    for revision, receipt in json.loads(
            (args.archive / 'toybox-execution' / 'updated-counts.json').read_text()).items():
        expected = {key: count for key, count in receipt['instances'].items() if key != 'static-archive'}
        if stats[revision]['categories'] != expected:
            raise ValueError(f'{revision}: aggregate differs from saved evidence')
    (args.output / 'summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n')
    for revision, stats in stats.items():
        print(f"{revision}: {stats['native_file_instances']} native instances, "
              f"{stats['rpm_count']} RPMs, {stats['categories']['unresolved']} unresolved")


if __name__ == '__main__':
    main()
