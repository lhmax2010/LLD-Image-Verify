#!/usr/bin/env python3
"""Record exact identity, revision, debug receipt and linker for the six PS3 ELF files."""
import argparse
import csv
from pathlib import Path


def rows(file):
    with file.open(newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--samples', type=Path, required=True)
    parser.add_argument('--expected', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'evidence/2026-11-23/inputs/expected-qb-commits.txt')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old = {(r['image'], r['path']): r for r in rows(args.previous)}
    expected = dict(line.split('@', 1) for line in args.expected.read_text().splitlines() if line)
    result = []
    for arch in ('aarch64', 'armv7l'):
        for row in rows(args.samples / f'sample-{arch}.tsv'):
            prior = old[(f'tizen-headed-{arch}', row['path'])]
            if (row['image_identity'] != 'image-file-sha256-matched'
                    or row['classification'] != 'lld-confirmed'
                    or row['debug_matched'] != 'yes'
                    or row['source_commit'] != expected[row['source']]):
                raise ValueError(f'Missing PS3 ELF evidence for {arch} {row["path"]}')
            result.append(dict(arch=arch, path=row['path'], source=row['source'],
                               previous_commit=prior['source_commit'],
                               latest_commit=row['source_commit'], previous_sha256=prior['sha256'],
                               latest_sha256=row['sha256'], identical=prior['sha256'] == row['sha256'],
                               debug_crc=row['debug_crc'], linker_evidence=row['evidence'],
                               runtime_rpm=row['runtime_rpm_url'], debug_rpm=row['debug_rpm']))
    if len(result) != 6:
        raise ValueError(f'Expected 6 artifacts, got {len(result)}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(result)
    print(f'{len(result)} PS3 image files matched to RPM and debuginfo, '
          f'{sum(row["identical"] for row in result)} byte-identical to QB 1234653')


if __name__ == '__main__':
    main()
