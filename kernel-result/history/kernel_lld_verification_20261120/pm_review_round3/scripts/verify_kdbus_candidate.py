#!/usr/bin/env python3
"""Generate the one-line candidate and dry-run it against a verified source copy."""
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'evidence/external/source/Makefile'
EXCERPTS = {
    SOURCE: [(1, 7), (26, 49)],
    'evidence/external/source/kdbus/Makefile': [(1, 22)],
    'evidence/external/linux-tizen-modules.spec': [(156, 161), (176, 190), (221, 275)],
    'evidence/kernel/source/Makefile': [(423, 435), (476, 496), (593, 599), (1811, 1838), (1881, 1889)],
    'evidence/kernel/source/scripts/Kbuild.include': [(63, 65)],
    'evidence/kernel/source/scripts/Makefile.build': [(36, 43), (429, 444), (480, 488)],
    'evidence/kernel/source/scripts/Makefile.modfinal': [(9, 18), (36, 40), (59, 63)],
    'evidence/kernel/source/scripts/Makefile.clang': [(1, 6), (20, 29)],
    'round1/evidence/repository/manifest.out': [(487, 488)],
    'evidence/external/external-buildlog-full.out': [(565, 577), (611, 613), (635, 637)],
}

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round2', type=Path, default=ROOT.parent/'pm_review_round2')
    args=parser.parse_args()
    source_root=args.round2.resolve(strict=True)
    archive={}
    for line in (source_root/'BUNDLE_SHA256SUMS').read_text().splitlines():
        digest, path=line.split('  ',1)
        archive[path]=digest
    sources={}
    numbered=[]
    for relative,ranges in EXCERPTS.items():
        file=source_root/relative
        digest=sha(file)
        if digest!=archive[relative]:
            raise ValueError(f'Round 2 archive member differs: {relative}')
        lines=file.read_text().splitlines()
        sources[relative]={'sha256':digest,'lines':[list(span) for span in ranges]}
        numbered.append(f'=== {relative} | SHA256 {digest} ===')
        for low,high in ranges:
            if high>len(lines):
                raise ValueError(f'line range outside {relative}: {low}-{high}')
            numbered.extend(f'{number:5}: {lines[number-1]}' for number in range(low,high+1))
        numbered.append('')

    evidence=ROOT/'evidence/fix-proposal'
    reference=evidence/'reference/Makefile'
    reference.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source_root/SOURCE,reference)
    (evidence/'source-excerpts.txt').write_text('\n'.join(numbered)+'\n')
    original=reference.read_text().splitlines(keepends=True)
    assignment='LD = '+chr(36)+'{CROSS_COMPILE}ld\n'
    if original[1]!=assignment or original.count(assignment)!=1:
        raise ValueError('unexpected external module assignment')
    candidate=original[:1]+original[2:]
    delta=difflib.unified_diff(original,candidate,'a/Makefile','b/Makefile',n=3)
    patch_path=ROOT/'KDBUS_LD_FIX_CANDIDATE.patch'
    patch_path.write_text('diff --git a/Makefile b/Makefile\n'+''.join(delta))

    timestamp=datetime.now(timezone.utc).isoformat()
    patch_command=['patch','--dry-run','--batch','--fuzz=0','-p1','-i',str(patch_path)]
    with tempfile.TemporaryDirectory(prefix='candidate-dry-run-',dir=evidence) as folder:
        scratch=Path(folder)
        target=scratch/'Makefile'
        shutil.copyfile(reference,target)
        before=sha(target)
        command=subprocess.run(patch_command,cwd=scratch,capture_output=True,check=False)
        after=sha(target)
    (evidence/'patch-dry-run.out').write_bytes(command.stdout)
    (evidence/'patch-dry-run.err').write_bytes(command.stderr)
    result=dict(started_utc=timestamp,argv=patch_command,cwd=str(scratch),exit_status=command.returncode,
                stdout='evidence/fix-proposal/patch-dry-run.out',stderr='evidence/fix-proposal/patch-dry-run.err',
                tool=subprocess.check_output(['patch','--version'],text=True).splitlines()[0],
                archive_summary_sha256=sha(source_root/'BUNDLE_SHA256SUMS'),checked_round2_sources=sources,
                source_before_sha256=before,source_after_sha256=after,source_copy_unchanged=before==after,
                patch_sha256=sha(patch_path),deleted_lines=1,added_lines=0)
    (evidence/'patch-dry-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if command.returncode or before!=after:
        raise SystemExit('patch did not pass pristine-copy dry-run')
    print('PASS: 10 matched source/log references, one-line candidate applies with zero fuzz and copy remains unchanged.')

if __name__=='__main__':
    main()
