#!/usr/bin/env python3
"""Promote byte-identical Toybox replays and update the unresolved ledger."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'evidence' / '2026-11-23'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_rows(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def reconcile(tag, originals, archive, runs, output):
    replay = runs / f'exact-{tag}'
    exact = json.loads((replay / 'summary.json').read_text())
    matches = {}
    for row in exact:
        arch, control = row['architecture'], row['bfd_control']
        if (control['linker'] != 'GNU ld (GNU Binutils) 2.43' or control['exit']
                or not control['historical_byte_match'] or row['historical_byte_match']):
            raise ValueError(f'{tag} {arch}: missing controlled link proof')
        sha = row['expected_elf_sha256']
        if (digest(replay / f'{arch}-toybox-bfd.elf') != sha
                or digest(archive / originals / f'{arch}-toybox.elf') != sha):
            raise ValueError(f'{tag} {arch}: exact replay hash differs')
        matches[sha] = arch, f'exact-{tag}/{control["log"]}'
    source = archive / tag
    with (source / 'open-artifacts.tsv').open(newline='') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    closed, remaining = [], []
    for row in rows:
        if row['source'] != 'platform/upstream/toybox' or row['sha256'] not in matches:
            remaining.append(row)
            continue
        arch, log = matches[row['sha256']]
        if row['classification'] != 'unresolved':
            raise ValueError(f'{tag}: unexpected prior Toybox classification')
        closed.append(dict(snapshot=tag, arch=arch, image=row['image'], partition=row['partition'],
                           path=row['path'], source_commit=row['source_commit'],
                           sha256=row['sha256'], linker='GNU ld.bfd 2.43',
                           evidence='byte-identical ELF after restoring original gzip mtime before linking',
                           replay_log=log, rpm_url=row['runtime_rpm_url']))
    if len(closed) != 12 or Counter(r['arch'] for r in closed) != {'aarch64': 6, 'armv7l': 6}:
        raise ValueError(f'{tag}: unexpected number of Toybox image copies')
    write_rows(output / f'{tag}-remaining-artifacts.tsv', remaining)
    initial = json.loads((source / 'summary.json').read_text())['instances']
    initial['unresolved'] -= len(closed)
    initial['gnu-ld-confirmed'] += len(closed)
    open_hashes = {r['sha256'] for r in remaining if r['classification'] == 'unresolved'}
    if initial['unresolved'] != sum(r['classification'] == 'unresolved' for r in remaining):
        raise ValueError(f'{tag}: inconsistent unresolved count')
    print(f'{tag}: 12 images files verified, {initial["unresolved"]} unresolved ({len(open_hashes)} SHA256)')
    return closed, dict(instances=initial, unresolved_unique_sha256=len(open_hashes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--replays', type=Path, default=ARCHIVE / 'toybox-execution')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results, counts = [], {}
    for tag, originals in [('latest', 'toybox'), ('qb1234653', 'toybox-qb1234653')]:
        rows, counts[tag] = reconcile(tag, originals, args.archive, args.replays, args.output)
        results.extend(rows)
    write_rows(args.output / 'confirmed-toybox-files.tsv', results)
    (args.output / 'updated-counts.json').write_text(json.dumps(counts, indent=2) + '\n')


if __name__ == '__main__':
    main()
