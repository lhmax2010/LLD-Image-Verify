#!/usr/bin/env python3
"""Save a command's verbatim streams and execution receipt."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stem',type=Path)
    parser.add_argument('argv',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    args.stem.parent.mkdir(parents=True,exist_ok=True)
    tick=monotonic()
    utc=datetime.now(timezone.utc).isoformat()
    with Path(str(args.stem)+'.out').open('wb') as stdout, Path(str(args.stem)+'.err').open('wb') as stderr:
        rc=subprocess.run(args.argv,stdout=stdout,stderr=stderr,check=False).returncode
    Path(str(args.stem)+'.cmd.json').write_text(json.dumps(
        dict(argv=args.argv,cwd=str(Path.cwd()),started_utc=utc,elapsed_seconds=round(monotonic()-tick,3),exit_status=rc),
        ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(rc)

if __name__=='__main__':
    main()
