#!/usr/bin/env python3
"""Bind the Phase 13 decision and gate matrix to verified data."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import re

from review_phase12 import ROOT, OUT, bench, csv_rows, load, prior, require, save
import thread_sweep as sweep

SUMMARY=ROOT/'PHASE13_FINAL_ACCEPTANCE_SUMMARY.json'
GATES=ROOT/'PRODUCT_MERGE_GATE_MATRIX.csv'
CHECKSUMS=ROOT/'SHA256SUMS'
THREADS=ROOT/'evidence/threads'
REQUIRED=('PHASE13_FINAL_ACCEPTANCE_REPORT.md','PHASE13_FINAL_ACCEPTANCE_SUMMARY.json',
          'INTERMEDIATE_SIZE_ATTRIBUTION.csv','LINKER_THREAD_PERFORMANCE_REPORT.md',
          'RUNTIME_REGRESSION_REPORT.md','KERNEL_OWNER_FINAL_JUSTIFICATION.md','PRODUCT_MERGE_GATE_MATRIX.csv',
          'REPRODUCE.md')


def compare_rows(actual,expected):
    require(len(actual)==len(expected),'Archived CSV row count differs from recalculation')
    for present,derived in zip(actual,expected,strict=True):
        require(present.keys()==derived.keys(),'Archived CSV schema differs from recalculation')
        for key,result in derived.items():
            same=(math.isclose(float(present[key]),float(result),rel_tol=1e-12,abs_tol=1e-12)
                  if isinstance(result,(int,float)) else present[key]==('' if result is None else result))
            require(same,f'Archived CSV field is inconsistent: {key}')


def validate_thread_sweep():
    design=load(THREADS/'design.json')
    claimed=csv_rows(THREADS/'summary.csv')
    raw=csv_rows(THREADS/'measurements.csv')
    require(load(THREADS/'sweep.cmd.json')['exit_status']==0,'Thread sweep did not exit successfully')
    require(design['blocks']==48 and len(raw)==288 and len(design['warmup'])==36,'Unexpected sample count')
    common=','.join(map(str,design['cpus']))
    require(design['cpus']==list(range(8)),'Unexpected sweep capacity')
    require(all(row['affinity']==common and row['exit_status']=='0' for row in raw),'Unequal thread sample resources or failed link')
    require(Counter((r['mode'],r['position']) for r in raw)==
            Counter({(variant,str(position)):8 for variant in sweep.MODES for position in range(1,7)}),'Unbalanced ordering')
    require(Counter((int(r['block']),r['mode']) for r in raw)==
            Counter({(block,variant):1 for block in range(1,49) for variant in sweep.MODES}),'Missing paired block members')
    for mode,record in design['mode_details'].items():
        used={r['output_sha256'] for r in raw if r['mode']==mode}
        trace=(THREADS/design['diagnostic_trace_files'][mode]).read_text()
        observed=len(re.findall(r'CLONE_THREAD.*?= [0-9]+\s*$',trace,re.M))
        require(used=={record['expected_output_sha256']} and observed==record['observed_worker_creations'],
                f'{mode} output or thread count differs')
        artifact=THREADS/f'{mode}.kdbus.o'
        require(artifact.stat().st_size==record['output_bytes'] and bench.sha(artifact) in used,
                f'{mode} retained object identity')
    lld={r['output_sha256'] for r in raw if r['mode'].startswith('lld')}
    require(len(lld)==1,'Thread tuning changed LLD output bytes')
    require(next(iter(lld)) in (ROOT/'LINKER_THREAD_PERFORMANCE_REPORT.md').read_text(),'Report output SHA differs')
    staged=[{**row,'block':int(row['block']),
             **{name:(float(row[name]) if name.endswith('_ms') else int(row[name])) for name in sweep.METRICS}}
            for row in raw]
    new=sweep.summarize(staged,design['seed'])
    compare_rows(claimed,new)
    selected={mode:{r['metric']:r for r in new if r['mode']==mode} for mode in sweep.MODES}
    one=selected['lld-1']['wall_ms']
    require(one['ci95_default_lo']>0 and one['ci95_bfd_hi']<0,'Tuning conclusion not supported')
    require(all(selected[f'lld-{thread}']['wall_ms']['ci95_default_lo']<=0<=
                selected[f'lld-{thread}']['wall_ms']['ci95_default_hi'] for thread in (2,4,8)),'Unexpected thread scaling result')
    return {'valid_measurements':len(raw),'cpus':design['cpus'],'blocks':design['blocks'],
            'worker_creations':{k:v['observed_worker_creations'] for k,v in design['mode_details'].items()},
            'mode_metrics':{mode:{k:{field:value for field,value in r.items() if field not in ('mode','metric')}
                                    for k,r in fields.items()} for mode,fields in selected.items()},
            'identical_lld_output_sha256':next(iter(lld)),
            'perf_capability_probe_exit_status':load(THREADS/'perf-capability.cmd.json')['exit_status'],
            'mechanism_classification':'HYPOTHESIS_WITH_MEASURED_THREAD_SETTING_EFFECT'}


def derive():
    audit=load(OUT/'audit.json')
    layout=load(OUT/'intermediate-layout.json')
    runtime=load(ROOT/'evidence/runtime/identity.json')
    source=prior('PHASE12_LLD_BENEFIT_SUMMARY.json')
    require(audit['status']=='PASS' and audit['benchmark']['samples']==160 and len(audit['linker_execs'])==4,
            'Prior Phase 12 audit inconsistent')
    require(layout['status']=='PASS_EXACT_FILE_DELTA' and layout['total_bytes']['delta']==-506628
            and layout['debug_str']['delta_bytes']==-506147,'Unexpected intermediate size result')
    regions=csv_rows(ROOT/'INTERMEDIATE_SIZE_ATTRIBUTION.csv')
    for column,value in (('bfd_file_bytes',2505192),('lld_file_bytes',1998564),('file_delta_bytes',-506628)):
        require(sum(int(row[column]) for row in regions[:-1])==int(regions[-1][column])==value,'File accounting mismatch')
    require(int(next(row['bfd_file_bytes'] for row in regions if row['section_or_region']=='.bss'))==0,'NOBITS file-size mistake')
    require(audit['mapping']['origin_counts']['stripped']=={'LINK_MAP_UNIQUE':75,'LINK_MAP_MULTIPLE':6} and
            audit['mapping']['final_effective_spans_equal'],'Static mapping validation failed')
    require(source['FINAL_MODULE_SIZE_CHANGE']=='MEASURED_AND_ATTRIBUTED' and source['size_bytes']['stripped']['delta']==-1292,
            'Final size strong claim lacks provenance')
    original={}
    for metric in ('wall_ms','peak_rss_kib'):
        matching={r['linker']:r for r in audit['benchmark']['summary_headline']
                  if r['profile']=='default_threads' and r['metric']==metric}
        bfd,lld=(matching[k]['median'] for k in ('bfd','lld'))
        row=matching['lld']
        require(row['classification']=='REGRESSION','Incorrect original performance status')
        original[metric]={'bfd_median':bfd,'lld_median':lld,'absolute_delta_unrounded':lld-bfd,
                         'delta_percent':-row['improvement_pct'],
                         'ci95_regression_pct':[-row['ci95_upper'],-row['ci95_lower']]}
    original['wall_ms']['displayed_medians_delta_ms']=6.231
    require(runtime['device_identity']=='MISMATCH_IMAGE_AND_PLATFORM' and
            runtime['runtime_regression']=='PENDING_NEW_IMAGE_DEPLOYMENT' and not runtime['device_mutation_performed'],
            'Unexpected actual target state')
    thread=validate_thread_sweep()
    fields={
        'PHASE12_EVIDENCE_REVIEW':'PASS',
        'INTERMEDIATE_SIZE_EXPLAINED':'PASS_EXACT_FILE_DELTA',
        'FINAL_SIZE_ATTRIBUTED':'MEASURED_AND_ATTRIBUTED',
        'MAPPING_SYMBOL_VALIDATION':'PASS_EFFECTIVE_ARM_BOUNDARIES_UNCHANGED',
        'DEFAULT_LINK_TIME_REGRESSION':'REGRESSION_ACCEPTED_FOR_KDBUS',
        'DEFAULT_PEAK_RSS_REGRESSION':'REGRESSION_ACCEPTED_FOR_KDBUS',
        'THREAD_OVERHEAD_ROOT_CAUSE':thread['mechanism_classification'],
        'THREAD_TUNING_POTENTIAL':'OBSERVED_FOR_THIS_WORKLOAD_THREADS_1',
        'GCC_COMPATIBILITY':audit['gcc']['gcc_compatibility'],
        'GCC_PRODUCT_CONFIG_COVERAGE':'THREE_TOOLCHAIN_LANES_RPI4_ARMV7L_NON_RT_ONLY',
        'STATIC_ABI_COMPATIBILITY':'PASS_CHECKED_ARTIFACTS',
        'NEW_QB_DEVICE_IDENTITY':runtime['device_identity'],
        'KERNEL_BOOT':runtime['d1_kernel_boot'],
        'MODULE_RUNTIME':runtime['d3_module_runtime'],
        'FUNCTIONAL_REGRESSION':runtime['d5_functional_regression'],
        'RUNTIME_MEMORY_BENEFIT':'NOT_MEASURED',
        'LLD_KERNEL_001':'CLOSED_ENGINEERING',
        'PRODUCT_MERGE_READINESS':'PENDING',
        'PM_REVIEW_REQUIRED':'YES',
    }
    detail={'recorded_on':'2026-11-27','positioning':'LLVM LLD Adaptation & Binary Size Optimization',
            'change_commit':source['fixed_commit'],'local_execution_evidence_level':'E4',
            'historical_qb_evidence':'UNCHANGED',
            'historical_execution_gap':'HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE',
            'original_benchmark':{'valid_samples':160,'summary_rows_recomputed':28,'default_thread_regressions':original},
            'thread_sweep':thread,'size_bytes':source['size_bytes'],'debug_string_attribution':layout['debug_str'],
            'avoided_final_redundant_data_mapping_symbols':81,
            'gcc_product_config':{'qb':audit['gcc']['qb'],'arch':audit['gcc']['architecture'],
              'release':audit['gcc']['kernel_release'],'linux_revision':audit['gcc']['same_kernel_commit_as_llvm_qb'],
              'lanes':list(audit['gcc']['runs']),'identical_installed_modules_per_pair':7},
            'RUNTIME_REGRESSION':runtime['runtime_regression'],'runtime_observed_qb':runtime['observed']['image_build_id'],
            'runtime_observed_model':runtime['observed']['model'],'runtime_observed_arch':runtime['observed']['arch'],
            'limits':['The Phase 12 comparison uses recovered Tizen user space, an older BFD accelerator and the pinned LLVM SDK and accelerator.',
                      'The original benchmark and Phase 13 sweep use distinct affinities and runs.',
                      'Root-cause component timings, aggregate I/O, debuginfo RPM savings and runtime memory are unmeasured.',
                      'GCC evidence covers one target kernel configuration, with three actual toolchain lanes.']}
    rows=[
        ('Phase 12 integrity and direct links','PASS','Local E4 only','evidence/review/audit.json',''),
        ('Intermediate and final size attribution','PASS','-506628 and -1292 bytes','INTERMEDIATE_SIZE_ATTRIBUTION.csv',''),
        ('ARM mapping symbol semantics','PASS','81 final redundant data markers avoided','evidence/review/mapping-stripped-review.json',''),
        ('Default build linker time and RSS','ACCEPTED_TRADE_OFF','+110.33% wall; +592.83% peak RSS','LINKER_THREAD_PERFORMANCE_REPORT.md','Retest at scale before changing global defaults'),
        ('GCC/BFD and reviewed static ABI','PASS','Three tested RPi4 ARMv7l non-RT lanes','../phase12_controlled_benchmark/GCC_COMPATIBILITY_REPORT.md',''),
        ('New QB identity','PENDING_NEW_IMAGE_DEPLOYMENT','Current device is Pi 5 AArch64 older QB','RUNTIME_REGRESSION_REPORT.md','Correct deployment and confirm approved device identity'),
        ('New QB boot and module / error regression','PENDING_NEW_IMAGE_DEPLOYMENT','D1–D4 pending','RUNTIME_REGRESSION_REPORT.md','Check boot, all 59 modules, existing state and errors after identity gate'),
        ('Functional regression','NOT_RUN','D5 pending','RUNTIME_REGRESSION_REPORT.md','Obtain approved test path and actual results'),
        ('Runtime memory benefit','NOT_MEASURED','No device allocation measurement','../phase12_controlled_benchmark/RUNTIME_MEMORY_FEASIBILITY.md',''),
        ('Product merge readiness','PENDING','Engineering closure approved; runtime open','PHASE13_FINAL_ACCEPTANCE_REPORT.md','PM review of outstanding runtime gates'),
    ]
    gates=[dict(zip(('gate','status','scope','evidence','remaining'),row,strict=True)) for row in rows]
    return fields|detail,gates


def verify_documents():
    for name in REQUIRED:
        path=ROOT/name
        require(path.stat().st_size>0,f'File is empty: {name}')
        if path.suffix!='.md':
            continue
        for link in re.findall(r'\]\(([^()]+)\)',path.read_text()):
            href=link.split('#',1)[0].strip('<>')
            if href and not re.match(r'^[a-z][a-z+.-]*://',href):
                require((path.parent/href).exists(),f'{name} has broken link {link}')
    owner=(ROOT/'KERNEL_OWNER_FINAL_JUSTIFICATION.md').read_text()
    require(not re.search(r'[\u3400-\u9fff]',owner),'Kernel owner record must be in English')
    require(all(s in owner for s in ('6.231','45,648','110.33%','592.83%')), 'Required trade-offs absent')


def records():
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path!=CHECKSUMS and '__pycache__' not in path.parts:
            yield f'{bench.sha(path)}  {path.relative_to(ROOT)}\n'


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('seal','verify'))
    mode=cli.parse_args().mode
    summary,gates=derive()
    if mode=='seal':
        save(SUMMARY,summary)
        with GATES.open('w',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=list(gates[0]))
            writer.writeheader()
            writer.writerows(gates)
        verify_documents()
        CHECKSUMS.write_text(''.join(records()))
    else:
        verify_documents()
        require(load(SUMMARY)==summary and csv_rows(GATES)==gates,'Decision differs from evidence')
        require(CHECKSUMS.read_text()==''.join(records()),'Phase 13 SHA256 manifest mismatch')
    print('PASS: acceptance results, all deliverables, statistics, gate matrix and Phase 13 SHA-256')


if __name__=='__main__':
    main()
