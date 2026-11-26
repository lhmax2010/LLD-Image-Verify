#!/usr/bin/env python3
"""Check that the saved evidence supports the counts in the follow-up report."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def tsv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'evidence/2026-11-23')
    args = parser.parse_args()
    root = args.directory
    for item in ('qb1234653', 'latest'):
        results = root / item
        counts = load(results / 'summary.json')
        files = tsv(results / 'elf-results.tsv')
        packages = tsv(results / 'rpm-results.tsv')
        assert Counter(r['classification'] for r in files) == counts['instances']
        assert Counter(r['status'] for r in packages) == counts['rpm']
        assert len(files) - counts['instances']['static-archive'] == 10875
        assert len({r['sha256'] for r in files if r['classification'] != 'static-archive'}) == 6014
        assert len(packages) == 2556
        assert sum(r['available'] == 'True' for r in tsv(results / 'logs-index.tsv')) == 203
        traces = tsv(results / 'new-link-traces.tsv')
        assert Counter(r['linker'] for r in traces) == {'LLD': 14, 'GNU ld.bfd 2.43': 24}
        print(item, 'ELF/RPM counts, log coverage and promoted evidence checked')
    scope = tsv(root / 'latest-scope.tsv')
    assert len(scope) == 58 and all(r['expected_sha'] == r['manifest_sha'] for r in scope)
    ps3 = tsv(root / 'ps3' / 'identity.tsv')
    assert len(ps3) == 6 and all(r['identical'] == 'True' and 'LLD 22.1.8' in r['linker_evidence']
                                and r['latest_sha256'] == r['previous_sha256'] for r in ps3)
    print('58 expected revisions and 6 new Patchset 3 files checked')
    loader = load(root / 'loader' / 'summary.json')
    assert len(loader) == 10 and all(r['exit_code'] == 0 for r in loader)
    symbols = load(root / 'symbol-load' / 'summary.json')
    assert len(symbols) == 4 and all(r['exit_code'] == 0 for r in symbols)
    for row in symbols:
        assert sum('FOUND' in s and '@SOLV_' in s for s in row['symbols']) == 4
        status = 'FOUND' if row['repository'] == 'gcc' else 'ABSENT'
        assert sum(s.startswith(status + ' _ZN16common_installer') for s in row['symbols']) == 3
    print('10 loader checks, 4 libsolv versioned symbols and 3 app-installers symbols verified')


if __name__ == '__main__':
    main()
