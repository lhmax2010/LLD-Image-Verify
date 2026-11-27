#!/usr/bin/env python3
"""Record one command, its exit status and unmodified stdout/stderr."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent

def run(stem, argv, timeout=60, echo=False):
    base = ROOT / 'evidence' / stem
    base.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ticks = time.monotonic()
    args = list(map(str, argv))
    with base.with_suffix(base.suffix + '.out').open('wb') as out, base.with_suffix(base.suffix + '.err').open('wb') as err:
        try:
            result = subprocess.run(args, cwd=ROOT, stdout=out, stderr=err, stdin=subprocess.DEVNULL, timeout=timeout)
            status = result.returncode
        except subprocess.TimeoutExpired:
            status = 124
        except OSError as exc:
            err.write((str(exc) + '\n').encode())
            status = 127
    meta = dict(argv=args, cwd=str(ROOT), started_utc=started, elapsed_seconds=round(time.monotonic()-ticks, 3), exit_status=status)
    base.with_suffix(base.suffix + '.cmd.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    output = base.with_suffix(base.suffix + '.out')
    if echo:
        sys.stdout.buffer.write(output.read_bytes())
        sys.stderr.buffer.write(base.with_suffix(base.suffix + '.err').read_bytes())
    return status, output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('stem')
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    sys.exit(run(options.stem, options.argv, options.timeout, True)[0])
