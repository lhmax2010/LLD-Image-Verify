#!/usr/bin/env python3
"""Reconcile a QB project@SHA list with manifests and native image files."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commits', type=Path, required=True)
    parser.add_argument('--manifest', action='append', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected = {}
    for line in args.commits.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        project, sha = line.split('@', maxsplit=1)
        if project in expected and expected[project] != sha:
            raise ValueError(f'Multiple expected revisions: {project}')
        expected[project] = sha
    built = {}
    for xml in args.manifest:
        for p in ET.parse(xml).iter('project'):
            built[p.get('name')] = p.get('revision')
    rows = defaultdict(list)
    with args.elf.open(newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if r['source'] in expected and r['classification'] != 'static-archive':
                rows[r['source']].append(r)
    table = []
    for project, sha in sorted(expected.items()):
        actual = built.get(project, '')
        observed = rows[project]
        source_shas = sorted({r['source_commit'] for r in observed})
        evidence = Counter(r['classification'] for r in observed)
        other = evidence['gnu-ld-confirmed'] + evidence['other-linker-confirmed']
        if not actual:
            status = 'revision absent from build manifest'
        elif actual != sha:
            status = 'different revision in build manifest'
        elif source_shas and source_shas != [sha]:
            status = 'different revision in image payload'
        elif not observed:
            status = 'no native ELF attributed in scanned images'
        elif evidence['lld-confirmed'] == len(observed):
            status = 'all observed ELF confirmed LLD'
        elif other:
            status = 'has confirmed other linker'
        elif evidence['lld-confirmed']:
            status = 'has confirmed LLD and open ELF'
        else:
            status = 'no confirmed linker on observed ELF'
        table.append(dict(project=project, expected_sha=sha, manifest_sha=actual,
                          image_shas='|'.join(source_shas),
                          images='|'.join(sorted({r['image'] for r in observed})),
                          elf_instances=len(observed),
                          elf_sha256s=len({r['sha256'] for r in observed}),
                          evidence=json.dumps(evidence, sort_keys=True), status=status))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(table)
    print(json.dumps(Counter(r['status'] for r in table), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
