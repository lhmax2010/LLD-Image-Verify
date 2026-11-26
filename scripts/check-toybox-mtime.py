#!/usr/bin/env python3
"""Verify that the GNU ld replay differs only in the help gzip mtime."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import zlib

BUILD_TIME = re.compile(r'(?:started|finished) "build toybox\.spec" at (\w+ \w+ \d+ \d\d:\d\d:\d\d UTC \d{4})')


def compare(old, rebuilt, log):
    if len(old) != len(rebuilt):
        raise ValueError('ELF length differs')
    differences = [i for i, (a, b) in enumerate(zip(old, rebuilt)) if a != b]
    pos = differences[0]
    start = pos - 4
    if differences != list(range(pos, pos + 4)) or old[start:pos] != b'\x1f\x8b\x08\x00':
        raise ValueError('ELF difference does not exactly cover the gzip mtime field')
    contents = [zlib.decompress(data[start:], wbits=31) for data in (old, rebuilt)]
    if contents[0] != contents[1] or b'usage:' not in contents[0]:
        raise ValueError('Embedded help text differs')
    times = [datetime.strptime(s, '%a %b %d %H:%M:%S UTC %Y').replace(tzinfo=timezone.utc)
             for s in BUILD_TIME.findall(log)]
    mtime = int.from_bytes(old[pos:pos + 4], 'little')
    if len(times) < 2 or not times[0].timestamp() <= mtime <= times[-1].timestamp():
        raise ValueError('Saved mtime does not fall within the published build window')
    return dict(mtime=mtime, gzip_mtime_offset=pos, different_bytes=len(differences),
                timestamp=datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
                historical_build_started=times[0].isoformat(),
                historical_build_finished=times[-1].isoformat(),
                help_sha256=hashlib.sha256(contents[0]).hexdigest(),
                original_sha256=hashlib.sha256(old).hexdigest(),
                controlled_sha256=hashlib.sha256(rebuilt).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical', required=True, type=Path)
    parser.add_argument('--replay', required=True, type=Path)
    parser.add_argument('--public-logs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = {}
    for arch in ('aarch64', 'armv7l'):
        old = (args.historical / f'{arch}-toybox.elf').read_bytes()
        replay = (args.replay / f'{arch}-toybox-bfd.elf').read_bytes()
        with gzip.open(args.public_logs / arch / 'toybox.txt.gz', 'rt', errors='replace') as f:
            receipt[arch] = compare(old, replay, f.read())
        print(arch, receipt[arch]['timestamp'], 'gzip MTIME confirmed, 4 bytes', flush=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
