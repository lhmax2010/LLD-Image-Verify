#!/usr/bin/env python3
"""Record the final Toybox link invocation and compare rebuilt RPM ELF bytes."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
from verify import extract_one, sha256

TARGET = re.compile(r' -o\s+\S*unstripped/toybox(?:\s|$)')
LINKER = re.compile(r'(?:^|\]\s{1,3})(GNU ld \(GNU Binutils\) [\d.]+|LLD [\d.]+)')
ARCHES = ('aarch64', 'armv7l')


def find_link_trace(paths):
    for path in paths:
        with path.open(errors='replace') as f:
            lines = f.read().splitlines()
        for pos, cmd in enumerate(lines):
            if not TARGET.search(cmd) or '-Wl,-v' not in cmd:
                continue
            for i in range(pos + 1, min(pos + 12, len(lines))):
                if match := LINKER.search(lines[i]):
                    return dict(log=str(path), command_line=pos + 1, version_line=i + 1,
                                command=cmd, version=lines[i], linker=match[1])
    return {}


def final_rpm(build_root, arch):
    found = []
    suffixes = ('.armv7l.rpm', '.arm.rpm') if arch == 'armv7l' else ('.aarch64.rpm',)
    for path in (build_root / 'local/repos').glob(f'*/{arch}/RPMS/**/toybox-*.rpm'):
        if not path.name.endswith(suffixes):
            continue
        name = subprocess.check_output(['rpm', '-qp', '--qf', '%{NAME}', str(path)],
                                       stderr=subprocess.DEVNULL, text=True)
        if name == 'toybox':
            found.append(path)
    return max(found, key=lambda p: (p.stat().st_mtime_ns, str(p))) if found else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    work, out = args.work.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with args.expected.open(newline='') as f:
        old = {r['arch']: r['elf_sha256'] for r in csv.DictReader(f, delimiter='\t')}
    records = []
    for arch in ARCHES:
        build_root = work / f'gbs-{arch}'
        logs = sorted(build_root.rglob('.build.log'))
        summary = work / f'gbs-{arch}.log'
        if summary.is_file():
            logs.append(summary)
        result = dict(arch=arch, original_elf_sha256=old[arch], named_link=find_link_trace(logs))
        if rpm := final_rpm(build_root, arch):
            exe = out / f'{arch}-rebuilt-toybox.elf'
            extract_one(rpm, '/usr/bin/toybox', exe)
            digest = sha256(exe)
            result.update(rpm=str(rpm), rpm_sha256=sha256(rpm), rebuilt_elf_sha256=digest,
                          historical_byte_match=digest == old[arch])
        records.append(result)
        print(f"{arch}: {result['named_link'].get('linker', 'no direct link trace')}, "
              f"original ELF hash match: {result.get('historical_byte_match', 'no RPM')}")
    (out / 'result.json').write_text(json.dumps(records, indent=2) + '\n')
    return int(any(not r['named_link'] or 'rebuilt_elf_sha256' not in r for r in records))


if __name__ == '__main__':
    sys.exit(main())
