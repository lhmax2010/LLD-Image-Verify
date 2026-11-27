#!/usr/bin/env python3
"""Copy the archived evidence needed to review Round 2 without large RPMs or images."""
import argparse
from pathlib import Path
import shutil

from review_common import BASE, HERE, dump, load, need, sha

ALWAYS = (
    'evidence/repository/manifest.out','evidence/repository/publication-build.out',
    'evidence/repository/boot-packages.out','evidence/repository/headed-packages.out',
    'evidence/repository/boot-SHA256SUMS.out','evidence/repository/image-profile-verification.json',
    'evidence/repository/packages-repomd.out','evidence/repository/packages-primary.out',
    'evidence/repository/packages-filelists.out','evidence/repository/boot-manifest.out',
    'evidence/repository/headed-manifest.out','evidence/repository/boot-ks.out',
    'evidence/repository/headed-ks.out','evidence/repository/boot-log.out',
    'evidence/repository/headed-log.out','evidence/kernel_binary/byte-comparison.json',
)

def include(name, path):
    item = Path(name)
    if len(item.parts)==1 or item.parts[0]=='scripts' or name in ALWAYS:
        return True
    if item.parts[:2]==('evidence','build'):
        return (not name.endswith('.rpm') and not name.startswith('evidence/build/historical-base/rpm-build/')
                and path.stat().st_size<=2*1024*1024)
    if item.parts[:2]==('evidence','runtime'):
        return (name.endswith(('.out','.err','.cmd.json','.json')) and not name.endswith('module-archive-base64.out')
                or name=='evidence/runtime/kernel-notes.bin')
    if item.parts[:2]==('evidence','modules'):
        return not name.endswith(('.ko','.bin')) and path.stat().st_size<=3*1024*1024
    if name.startswith('evidence/kernel_binary/analysis/'):
        return not name.endswith('.bin') and path.stat().st_size<=1024*1024
    if name.startswith('evidence/kernel_binary/upstream/'):
        return True
    if name.startswith('evidence/preflight/'):
        return path.stat().st_size<=1024*1024
    if item.parts[:2]==('evidence','repository'):
        return (name.endswith(('.headers','.cmd.json','.err')) or
                item.name.endswith(('-metadata.out','-verify.out','-header.out','-filelist.out')) and
                path.stat().st_size<=256*1024)
    return False

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=BASE)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    hashes={}
    for line in (base/'SHA256SUMS').read_text().splitlines():
        hash_value, name=line.split('  ',1)
        hashes[name]=hash_value
    retained={}
    for name,expected in hashes.items():
        source=base/name
        need(source.is_file() and source.resolve().is_relative_to(base),'archive path escapes root')
        if not include(name,source):
            continue
        need(sha(source)==expected,f'original file hash differs {name}')
        chosen=out/'round1'/name
        chosen.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,chosen)
        retained[name]=expected
    shutil.copy2(base/'SHA256SUMS',out/'round1/SHA256SUMS')
    for suffix in ('out','err','cmd.json'):
        source=base/f'evidence/preflight/self-check.{suffix}'
        if source.is_file():
            shutil.copy2(source,out/'round1'/source.relative_to(base))
    dump(out/'evidence/ROUND1_RETENTION_INDEX.json',dict(archive_original_path=str(base),
         round1_manifest_sha256=sha(base/'SHA256SUMS'), included_count=len(retained),
         included=retained, archived_only={n:h for n,h in hashes.items() if n not in retained}))
    audit=load(out,'08_01_evidence_integrity_review.json')
    logs=[]
    lines_by_path={}
    observed=load(base,'evidence/build/module-final-commands.json')['quiet_link_observations']
    for rel,item in audit['log_bindings'].items():
        lines=(base/rel).read_text().splitlines()
        lines_by_path[rel]=lines
        logs.append(dict(item, line_count=len(lines), local_review_copy=item['full_log_path'],
                         archive_path=str(base/rel)))
    ext_log=out/'evidence/external/source-provider-buildlog.out'
    if ext_log.is_file():
        receipt=load(out,'evidence/external/source-provider-buildlog.cmd.json')
        args=receipt['argv']
        logs.append(dict(local_review_copy='evidence/external/source-provider-buildlog.out', full_log_sha256=sha(ext_log),
                         url=next(arg for arg in args if arg.startswith('http')),line_count=len(ext_log.read_text().splitlines()),
                         original_receipt='evidence/external/source-provider-buildlog.cmd.json',
                         manifest_revision='25797e8af7ed95a5783bbe84c11959560aaf7e92'))
    dump(out/'evidence/ORIGINAL_BUILD_LOG_INDEX.json',logs)
    excerpt=[]
    for item in sorted(observed,key=lambda x:(x['event']['evidence'],x['event']['line'])):
        excerpt.append(item['package_rpm']+' '+item['payload_path'])
        for key in ('llvm_selection','event','install_event','rpm_write','build_completion'):
            row=item[key]
            number=row['line']
            src=row['evidence']
            need(lines_by_path[src][number-1]==row['raw'],'log excerpt no longer matches')
            excerpt.append(f'  round1/{src}:{number} {row["raw"]}')
    (out/'evidence/module-final-link-excerpts.txt').write_text('\n'.join(excerpt)+'\n')
    print(f'PASS: {len(retained)} byte-checked original files copied; {len(logs)} original log indexes and 59 numbered .ko histories.')

if __name__=='__main__':
    main()
