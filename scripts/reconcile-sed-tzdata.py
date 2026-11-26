#!/usr/bin/env python3
"""Update image totals from a completed sed/tzdata replay."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

CANDIDATES = {'sed', 'tzdata'}
LINKERS = {'bfd': 'GNU ld (GNU Binutils) 2.43', 'lld': 'LLD 22.1.8'}
CLASSIFICATION = {'bfd': 'gnu-ld-confirmed', 'lld': 'lld-confirmed'}


def read_tsv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def write_tsv(path, fields, rows):
    with path.open('w', newline='') as stream:
        output = csv.DictWriter(stream, fields, delimiter='\t')
        output.writeheader()
        output.writerows(rows)


def load_proofs(archive, round_name):
    proofs = {}
    for arch in ('aarch64', 'armv7l'):
        for package in sorted(CANDIDATES):
            receipt = archive / round_name / arch / package / 'results.json'
            report = json.loads(receipt.read_text())
            log = receipt.with_name('build.log').read_text()
            if not all(v in log for v in LINKERS.values()):
                raise ValueError(f'{receipt}: missing one of the actual linker versions')
            for name, target in report['targets'].items():
                image = target['image']
                if image['sha256'] != target['rpm']['sha256']:
                    raise ValueError(f'{receipt}: {name} differs between RPM and image')
                matches = [variant for variant in LINKERS
                           if target[variant]['sha256_without_debug_crc'] == image['sha256_without_debug_crc']]
                if len(matches) != 1:
                    raise ValueError(f'{receipt}: {name} matches {matches}, expected exactly one linker')
                variant, = matches
                fields = {
                    'replay_linker': LINKERS[variant],
                    'rpm_elf_sha256': target['rpm']['sha256'],
                    'replay_elf_sha256': target[variant]['sha256'],
                    'elf_sha256_without_debug_crc': image['sha256_without_debug_crc'],
                    'full_sha256_match': str(target[variant]['sha256'] == image['sha256']).lower(),
                    'evidence_file': str(receipt.relative_to(archive)),
                }
                proofs[(package, arch, name)] = (image['sha256'], CLASSIFICATION[variant], fields)
    return proofs


def reconcile(previous, archive):
    stats = json.loads((previous / 'updated-counts.json').read_text())
    remaining_digests = set()
    for round_name in ('latest', 'qb1234653'):
        proofs = load_proofs(archive, round_name)
        previous_rows = read_tsv(previous / f'{round_name}-remaining.tsv')
        promoted = []
        remaining = []
        applied = set()
        totals = stats[round_name]
        for row in previous_rows:
            package = row['source'].rsplit('/', 1)[-1]
            prefix = row['image'].rsplit('-', 1)[-1]
            key = package, prefix, Path(row['path']).name
            if key not in proofs:
                remaining.append(row)
                continue
            digest, category, fields = proofs[key]
            if row['sha256'] != digest:
                raise ValueError(f'Unexpected original SHA for {row["path"]} in {row["image"]}')
            applied.add(key)
            promoted.append(dict(row, classification=category,
                                 method='original RPM byte match and one replay matches outside debug CRC', **fields))
            for counts in (totals['instances'], totals['by_image'][row['image']], totals['by_repository']['base']):
                counts['unresolved'] -= 1
                counts[category] = counts.get(category, 0) + 1
        if applied != proofs.keys():
            raise ValueError(f'{round_name}: replay proof missing from baseline')
        write_tsv(archive / f'{round_name}-confirmed.tsv', list(promoted[0]), promoted)
        write_tsv(archive / f'{round_name}-remaining.tsv', list(remaining[0]), remaining)
        remaining_digests.update(row['sha256'] for row in remaining)
        totals['remaining_by_source'] = Counter(row['source'] for row in remaining)
        totals['remaining_unique_sha256'] = len({row['sha256'] for row in remaining})
        totals['sed_tzdata_confirmed_instances'] = len(promoted)
        totals['sed_tzdata_confirmed_unique_sha256'] = len({row['sha256'] for row in promoted})
        print(round_name, f'{len(promoted)} confirmed, {len(remaining)} unresolved')
    stats['remaining_unique_sha256_across_rounds'] = len(remaining_digests)
    (archive / 'updated-counts.json').write_text(json.dumps(stats, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--proofs', type=Path, required=True)
    args = parser.parse_args()
    reconcile(args.previous, args.proofs)
