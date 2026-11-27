#!/usr/bin/env python3
"""Bind the Phase 14 gate matrix and archive hashes to captured results."""
import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re

from review_runtime import ROOT, E, PAST, KDBUS, TARGET, load, require, rows, sha, write_csv

MATRIX=ROOT/'PRODUCT_MERGE_FINAL_GATE_MATRIX.csv'
MANIFEST=ROOT/'SHA256SUMS'
DOCS=('PM_PHASE13_FINAL_DECISION.md','FINAL_LLD_BENEFIT_SUMMARY.md',
      'PHASE14_RUNTIME_REGRESSION_REPORT.md','KERNEL_OWNER_INTEGRATION_REQUEST.md')


def compare_archive_values(result):
    past=load(PAST/'PHASE13_FINAL_ACCEPTANCE_SUMMARY.json')
    require(past['PHASE12_EVIDENCE_REVIEW']=='PASS' and past['GCC_COMPATIBILITY']=='PASS',
            'Approved evidence does not match Phase 13')
    removed=-past['size_bytes']['intermediate']['delta']
    debug=-past['debug_string_attribution']['delta_bytes']
    contribution=(Decimal(100)*debug/removed).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    require((removed,debug,str(contribution))==(506628,506147,'99.91'),'Approved intermediate benefit differs')
    require(past['size_bytes']['stripped']['delta']==-1292 and past['avoided_final_redundant_data_mapping_symbols']==81,
            'Approved final module benefit differs')
    benchmark=past['original_benchmark']
    regressions=benchmark['default_thread_regressions']
    speed=past['thread_sweep']['mode_metrics']['lld-1']['wall_ms']['improvement_vs_default_pct']
    require(benchmark['valid_samples']==160 and regressions['wall_ms']['displayed_medians_delta_ms']==6.231 and
            regressions['peak_rss_kib']['absolute_delta_unrounded']==45648 and round(speed,2)==13.82,
            'Approved benchmarking values differ')
    require(past['RUNTIME_MEMORY_BENEFIT']==result['RUNTIME_MEMORY_BENEFIT']=='NOT_MEASURED',
            'Runtime memory result was expanded without evidence')


def gates():
    result=load(E/'runtime-result.json')
    compare_archive_values(result)
    modules=rows(E/'module-runtime-to-rpm.csv')
    require(len(modules)==59 and Counter(m['group'] for m in modules)=={'in-tree':52,'out-of-tree':7} and
            all(m['new_qb_file_match']=='PASS' for m in modules),'Incorrect runtime module inventory')
    kb=next(m for m in modules if m['path']==KDBUS)
    kernel=result['kernel_release_binding']
    require(result['device']['image_build_id']==TARGET and result['NEW_QB_DEVICE_IDENTITY']=='PASS' and
            kernel['status']=='EXACT_LIVE_NOTES_AND_BANNER_MATCH','Wrong admitted QB')
    require(kernel['device_note_length']==84 and sha(E/'release/raw-Image')==kernel['raw_image_sha256'],
            'Incorrect raw image and note proof')
    require(kb['device_module_sha256']==result['kdbus']['module_sha256'] and
            result['kdbus']['sysfs']['initstate']=='live','Wrong kdbus state')
    log=load(E/'kernel-log-review.json')
    require(log['dmesg_lines']==548 and not any(log['hits'].values()) and log['journal_exit_status']==1,
            'Observed kernel error scope differs')
    require(result['old_qb_baseline']['only_old_loaded_snapshot']==['binfmt_misc'] and
            not result['old_qb_baseline']['only_new_loaded_snapshot'],'Unexpected loaded-list comparison')
    require(result['FUNCTIONAL_REGRESSION']=='NOT_RUN_NO_APPROVED_CASE_AVAILABLE' and
            result['KERNEL_OWNER_TRADEOFF_ACCEPTANCE']=='PENDING_OWNER_REVIEW' and
            result['PRODUCT_MERGE_READINESS']=='PENDING' and not result['device_mutation_performed'],
            'Unapproved product or functional status')
    rows_to_write=[
        ('Phase 13 engineering acceptance','PASS','PM-approved engineering scope',
         'PM_PHASE13_FINAL_DECISION.md',''),
        ('Target QB runtime admission','PASS','RPi4 ARMv7l non-RT at private-address-03:26101; live kernel notes and banner match published boot RPM',
         'evidence/runtime-result.json',''),
        ('Kernel boot','PASS','running, boot targets active, zero failed units',
         'evidence/device-boot.out',''),
        ('Published module file identity','PASS_59_OF_59','52 in-tree and 7 out-of-tree files match published RPM members',
         'evidence/module-runtime-to-rpm.csv',''),
        ('Installed and live kdbus','PASS_LIVE_STATE','Installed SHA and live Build ID match, state live, kdbusfs mounted',
         'PHASE14_RUNTIME_REGRESSION_REPORT.md',''),
        ('Critical runtime error review','PASS_OBSERVED_DMESG_SCOPE','No matching errors in 548 readable dmesg lines',
         'evidence/kernel-log-review.json','Functional test-period log review pending; kernel journal ACL limited'),
        ('kdbus functional regression','NOT_RUN_NO_APPROVED_CASE_AVAILABLE','No approved runnable case in the current session',
         'PHASE14_RUNTIME_REGRESSION_REPORT.md','Run an approved functional test and archive behavior, exit status and log'),
        ('GCC/BFD target compatibility','PASS_RPI4_ARMV7L_NON_RT','Three tested real lanes on matching GCC SDK',
         '../phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md','Kernel Owner to confirm product scope'),
        ('Build performance trade-off','PM_ACCEPTED_FOR_KDBUS','Default wall +110.33%, process peak RSS +592.83%',
         'FINAL_LLD_BENEFIT_SUMMARY.md',''),
        ('Kernel Owner trade-off acceptance','PENDING_OWNER_REVIEW','Review request prepared',
         'KERNEL_OWNER_INTEGRATION_REQUEST.md','Record explicit owner acceptance'),
        ('Runtime memory benefit','NOT_MEASURED','Module footprint observation does not measure device memory benefit',
         'FINAL_LLD_BENEFIT_SUMMARY.md',''),
        ('Product merge readiness','PENDING','Read-only runtime checks passed; functional regression and owner review open',
         'PHASE14_RUNTIME_REGRESSION_REPORT.md','PM product review after open gates pass'),
    ]
    return [dict(zip(('gate','status','scope','evidence','remaining'),line,strict=True)) for line in rows_to_write]


def scan_links():
    for doc in DOCS:
        path=ROOT/doc
        require(path.stat().st_size>0,f'Empty deliverable: {doc}')
        for link in re.findall(r'\]\(([^()]+)\)',path.read_text()):
            href=link.split('#',1)[0]
            if href and not re.match(r'^[a-z][a-z+.-]*://',href):
                require((path.parent/href).exists(),f'{doc} has broken reference {link}')


def digests():
    return ''.join(f'{sha(path)}  {path.relative_to(ROOT)}\n' for path in sorted(ROOT.rglob('*'))
                   if path.is_file() and path!=MANIFEST and '__pycache__' not in path.parts)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('seal','verify'))
    mode=cli.parse_args().mode
    matrix=gates()
    if mode=='seal':
        write_csv(MATRIX,matrix)
        scan_links()
        MANIFEST.write_text(digests())
    else:
        scan_links()
        require(rows(MATRIX)==matrix,'Gate matrix does not match the evidence')
        require(MANIFEST.read_text()==digests(),'Phase 14 archive checksum mismatch')
    print('PASS: five deliverables, acceptance gates, scope boundaries and SHA-256 archive')


if __name__=='__main__':
    main()
