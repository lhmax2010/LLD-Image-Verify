#!/usr/bin/env python3
"""Run Round 1 verification in a view containing only the sealed Round 1 archive."""
import argparse
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from review_common import BASE, need

def view(base, target):
    names = {'SHA256SUMS'}
    names.update(line.split('  ',1)[1] for line in (base/'SHA256SUMS').read_text().splitlines())
    for name in ('out','err','cmd.json'):
        path = f'evidence/preflight/self-check.{name}'
        if (base/path).is_file():
            names.add(path)
    for name in sorted(names):
        original = base/name
        need(original.resolve().is_relative_to(base) and not original.is_symlink() and original.is_file(),f'unsafe archived path {name}')
        destination = target/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(original,destination)
    for path in (base/'evidence/repository/images/mtools').rglob('*'):
        if path.is_symlink():
            need(path.resolve().is_relative_to(base),f'unsafe archived mtools symlink {path}')
            dest=target/path.relative_to(base)
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.symlink_to(path.readlink())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('check','replay'))
    parser.add_argument('destination',type=Path,nargs='?')
    parser.add_argument('--base',type=Path,default=BASE)
    args=parser.parse_args()
    chosen=args.base.resolve()
    need((args.mode=='replay')==bool(args.destination),'replay requires a new destination')
    if args.mode=='check':
        sys.dont_write_bytecode=True
        sys.path.insert(0,str(chosen/'scripts'))
        checker=importlib.import_module('check_bundle')
        need(checker.ROOT==chosen,'unexpected archived verifier root')
        original=checker.files
        checker.files=lambda: [p for p in original() if not p.is_relative_to(chosen/'pm_review_round2')]
        sys.argv = [sys.argv[0]]
        checker.main()
        return
    with tempfile.TemporaryDirectory(prefix='.round1-review-view-',dir=chosen.parent) as folder:
        temporary=Path(folder)
        view(chosen,temporary)
        dest=args.destination.resolve()
        need(not dest.is_relative_to(chosen),'replay destination must be outside the archive tree')
        argv=['bash',str(temporary/'verify.sh'),'replay',str(dest)]
        result=subprocess.run(argv,check=False)
    raise SystemExit(result.returncode)

if __name__=='__main__':
    main()
