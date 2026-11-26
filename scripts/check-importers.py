#!/usr/bin/env python3
"""Look for actual dynamic imports of the app-installers symbols under review."""
import argparse
from collections import Counter
import json
import mmap
import os
from pathlib import Path
import re
import subprocess


def candidates(contracts):
    result = set()
    for row in json.loads(contracts.read_text())['packages']:
        if row['package'] != 'app-installers':
            continue
        for target in row['targets'].values():
            entries = target['differences']['exports']
            gcc, llvm = ({s.split()[3] for s in entries[k]} for k in ('gcc_only', 'llvm_only'))
            result.update(gcc - llvm)
    return {s.encode(): s for s in result}


def inspect(root, names):
    totals = Counter()
    matches, issues = [], []
    for directory, _, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open('rb') as f:
                    if f.read(4) != b'\x7fELF':
                        continue
                    totals['elf'] += 1
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                        selected = {symbol for spelling, symbol in names.items()
                                    if mapped.find(spelling + b'\0') != -1}
                if not selected:
                    continue
                totals['readelf_candidates'] += 1
                raw = subprocess.run(['readelf', '--dyn-syms', '-W', path], text=True,
                                     capture_output=True, timeout=30)
                if raw.returncode:
                    issues.append({'path': str(path.relative_to(root)), 'error': raw.stderr.strip()})
                    continue
                for line in raw.stdout.splitlines():
                    tokens = line.split()
                    if len(tokens) < 8 or tokens[6] != 'UND':
                        continue
                    symbol = tokens[7].split('@', 1)[0]
                    if symbol in selected:
                        matches.append({'file': '/' + str(path.relative_to(root)), 'symbol': symbol,
                                        'readelf': line.strip()})
            except (OSError, subprocess.TimeoutExpired) as exc:
                issues.append({'file': str(path.relative_to(root)), 'error': str(exc)})
    return {'elf': totals['elf'], 'readelf_candidates': totals['readelf_candidates'],
            'imports': matches, 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contracts', required=True, type=Path)
    parser.add_argument('--root', required=True, action='append', help='LABEL=/path/to/rootfs')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    names = candidates(args.contracts)
    results = {}
    for item in args.root:
        label, directory = item.split('=', 1)
        root = Path(directory).resolve()
        if not root.is_dir():
            raise ValueError(f'Missing root {root}')
        results[label] = inspect(root, names)
        print(label, results[label]['elf'], len(results[label]['imports']), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(symbols=sorted(names.values()), roots=results),
                                     indent=2) + '\n')


if __name__ == '__main__':
    main()
