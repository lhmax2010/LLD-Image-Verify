#!/usr/bin/env python3
"""Save verification outputs from a scratch image scan into its run directory."""
import argparse
from pathlib import Path
import shutil

SCAN_FILES = ('elf-linker-audit.tsv', 'rpm-linker-audit.tsv', 'summary.json')
SCAN_GLOBS = ('debug-matches-*.jsonl', 'debug-errors-*.jsonl')
MANIFEST_NAMES = {'SHA256SUMS', 'manifest.json'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    work, output = args.work.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    def save(source):
        dest = output / source.relative_to(work)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    for name in SCAN_FILES:
        if (work / name).is_file():
            save(work / name)
    for pattern in SCAN_GLOBS:
        for source in work.glob(pattern):
            save(source)
    for folder in ('raw', 'observed'):
        for source in (work / folder).glob('*'):
            if source.is_file() and source.suffix in {'.xml', '.gz', '.tsv', '.json'}:
                save(source)
    for source in (work / 'images').glob('*/*'):
        if source.name in MANIFEST_NAMES or source.suffix in {'.files', '.packages'}:
            save(source)
    print(f'Saved scan evidence in {output}')


if __name__ == '__main__':
    main()
