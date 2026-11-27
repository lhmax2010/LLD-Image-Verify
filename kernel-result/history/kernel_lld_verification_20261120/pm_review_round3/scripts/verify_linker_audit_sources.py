#!/usr/bin/env python3
"""Bind selected audit files to exact package headers and sealed build logs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[1]
BASENAME = 'arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm'
LOGS = {
    'evidence/build/linux-rpi-armv7l.out': [
        1677, 2701, 2708, 3371, 3388, 3455, 7941, 7962, 8141
    ],
    'pm_review_round2/evidence/external/external-buildlog-full.out': [
        437, 565, 574, 575, 576, 612, 636, 657
    ],
}

def sha(path):
    with path.open('rb') as fd:
        return hashlib.file_digest(fd,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=HERE.parent)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    if out==base or out.is_relative_to(base/'pm_review_round2'):
        raise ValueError('Audit output directory would modify an older archive.')
    audit=out/'evidence/audit'
    round2=base/'pm_review_round2'
    scope=json.loads((audit/'source-scope.json').read_text())
    original_manifest=dict((line.split('  ',1)[1],line.split('  ',1)[0])
                           for line in (base/'SHA256SUMS').read_text().splitlines())
    second_manifest=dict((line.split('  ',1)[1],line.split('  ',1)[0])
                         for line in (round2/'BUNDLE_SHA256SUMS').read_text().splitlines())
    reasons=[]
    rpm=f'evidence/repository/rpms/{BASENAME}'
    command=['rpm','-qp','--qf','%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]',rpm]
    metadata=subprocess.run(command,cwd=base,capture_output=True,check=True)
    algorithm,*header_lines=metadata.stdout.decode().splitlines()
    if algorithm!='8':
        raise ValueError(f'Devel RPM filelist does not use SHA256: {algorithm}')
    header=dict(line.split('\t',1) for line in header_lines)
    if sha(base/rpm)!=original_manifest[rpm]:
        raise ValueError('Exact SDK RPM package checksum changed.')
    for row in scope['files']:
        local=sha(audit/row['file'])
        if row['group']=='host-and-tools':
            expected=header['/'+row['cpio_member']]
            route='exact SDK RPM FILEDIGESTS'
        else:
            expected=second_manifest[row['origin'].removeprefix('pm_review_round2/')]
            route='Round 2 BUNDLE_SHA256SUMS'
        if not local==expected==row['sha256']:
            raise ValueError(f"Source member SHA256 mismatch: {row['file']}")
        reasons.append(dict(file='evidence/audit/'+row['file'],sha256=local,verified_by=route))
    binding=json.loads((round2/'evidence/kernel/kernel-source-binding.json').read_text())
    bins=json.loads((round2/'evidence/external/historical-binutils-resolution.json').read_text())
    src=json.loads((round2/'evidence/external/source-content-inventory.json').read_text())
    capsule=dict(
        verdict='PASS', exact_devel_rpm=dict(path=rpm,sha256=original_manifest[rpm],query_argv=command,query_exit_status=metadata.returncode),
        sources=reasons,
        patches=[{key:value for key,value in item.items() if key!='changed_paths'} for item in binding['srpm']['patches']],
        external_sources=dict(provider=src['provider_package'],source0_sha256=src['source0_sha256'],prebuilt=src['prebuilt_findings']),
        binutils=bins, logs=[]
    )
    excerpts=[]
    for rel,nums in LOGS.items():
        log=base/rel
        actual=sha(log)
        expected=(second_manifest[rel.removeprefix('pm_review_round2/')]
                  if rel.startswith('pm_review_round2/') else original_manifest[rel])
        if actual!=expected:
            raise ValueError(f'Log is not bound to original manifest: {rel}')
        capsule['logs'].append(dict(path=rel,sha256=expected,selected_lines=nums))
        lines=log.read_text().splitlines()
        excerpts.append(f'{rel}\nSHA256 {expected}')
        excerpts.extend(f'{num:>5}  {lines[num-1]}' for num in nums)
        excerpts.append('')
    (audit/'audit-build-log-excerpts.txt').write_text('\n'.join(excerpts))
    (audit/'audit-source-verification.json').write_text(json.dumps(capsule,indent=2)+'\n')
    print(f'PASS: {len(reasons)} source digests, exact SDK RPM SHA256, and both archived build-log hashes.')

if __name__=='__main__':
    main()
