#!/usr/bin/env python3
"""Six-way blocked thread sweep against the unchanged Phase 12 link response."""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIOR = Path('/phase12') if Path('/phase12').is_dir() else ROOT.parent/'phase12_controlled_benchmark'
OUT = ROOT / 'evidence/threads'
sys.path.insert(0, str(PRIOR/'scripts'))
import benchmark_linkers as baseline

MODES = {'bfd': ('bfd', None), 'lld-default': ('lld', None),
         **{f'lld-{n}': ('lld', n) for n in (1, 2, 4, 8)}}
METRICS = ('wall_ms', 'user_ms', 'system_ms', 'peak_rss_kib', 'major_faults', 'minor_faults', 'output_bytes')
ENV = {'LC_ALL': 'C', 'TZ': 'UTC', 'PATH': '/usr/bin:/bin'}


def load(path):
    return json.loads((PRIOR/path).read_text())


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(executable, argv, stderr):
    timer=PRIOR/'evidence/benchmark/bench-timer'
    p=subprocess.run([str(timer),str(stderr),executable,*argv],env=ENV,capture_output=True,text=True,check=True)
    wall,user,system,rss,major,minor,status=p.stdout.split()
    return (float(wall),float(user),float(system),int(rss),int(major),int(minor)),int(status)


def balanced_order(rng, names, block_count):
    for _ in range(block_count//len(names)):
        order=list(names)
        shifts=list(range(len(names)))
        rng.shuffle(order)
        rng.shuffle(shifts)
        for n in shifts:
            yield order[n:]+order[:n]


def summarize(rows, seed):
    rng=random.Random(seed)
    rows_by_mode={mode:sorted((r for r in rows if r['mode']==mode), key=lambda r:r['block']) for mode in MODES}
    aggregate=[]
    for mode, series in rows_by_mode.items():
        for metric in METRICS:
            values=[r[metric] for r in series]
            base=[r[metric] for r in rows_by_mode['bfd']]
            control=[r[metric] for r in rows_by_mode['lld-default']]
            bfd_med=statistics.median(base)
            default_med=statistics.median(control)
            median=statistics.median(values)
            lo,hi=baseline.paired_ci(base,values,rng)
            d_lo,d_hi=baseline.paired_ci(control,values,rng)
            aggregate.append(dict(mode=mode,metric=metric,n=len(values),mean=statistics.mean(values),
                median=median,stddev=statistics.stdev(values),p95=baseline.quantile(values,.95),
                min=min(values),max=max(values),improvement_vs_bfd_pct=100*(bfd_med-median)/bfd_med if bfd_med else None,
                ci95_bfd_lo=lo,ci95_bfd_hi=hi,improvement_vs_default_pct=100*(default_med-median)/default_med if default_med else None,
                ci95_default_lo=d_lo,ci95_default_hi=d_hi))
    return aggregate


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--blocks', type=int, default=48)
    cli.add_argument('--cpus', default='0,1,2,3,4,5,6,7')
    cli.add_argument('--seed', type=int, default=20261127)
    args=cli.parse_args()
    if args.blocks<30 or args.blocks % len(MODES):
        cli.error('Blocks must be a multiple of 6 and at least 30')
    allowed=sorted(os.sched_getaffinity(0))
    cpus=sorted(set(map(int,args.cpus.split(','))))
    assert set(cpus)<=set(allowed)
    os.sched_setaffinity(0,cpus)
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=load('evidence/replay/frozen-inputs.json')
    build=load('evidence/build/controlled-builds.json')['groups']
    replay=load('evidence/replay/link-replay.json')
    frozen_files=frozen['ordered_response_and_objects']+frozen['sdk_resources']
    for row in frozen_files:
        assert baseline.sha(row['guest_path'])==row['sha256'],row['guest_path']
    cwd=Path('/boot/kernel/devel/kernel-devel-arm-rpi4')
    os.chdir(cwd)
    target=OUT/'timed-output.o'
    modes, warmup, diagnostics={}, [], {}
    for mode,(family,threads) in MODES.items():
        recipe=replay['commands'][family]['plain']
        executable=recipe['exec_path']
        checksum=baseline.sha(executable)
        assert checksum==build['A' if family=='bfd' else 'B']['intermediate']['executable_sha256']
        argv=recipe['argv'].copy()
        argv[argv.index('-o')+1]=str(target)
        if threads is not None:
            argv.append(f'--threads={threads}')
        stderr=OUT/f'{mode}.stderr'
        stderr.write_bytes(b'')
        expected=replay['products'][family]['intermediate']['sha256']
        trace=OUT/f'{mode}.thread-creation.strace'
        probe=['/usr/bin/strace','-f','-qq','-e','trace=clone,clone3','-o',str(trace),'/usr/bin/bash',
               '-c','exec -a "$1" "$2" "${@:3}"','bash',argv[0],executable,*argv[1:]]
        subprocess.run(probe,env=ENV,check=True)
        workers=len(re.findall(r'CLONE_THREAD.*?= [0-9]+\s*$',trace.read_text(),re.M))
        assert baseline.sha(target)==expected
        modes[mode]={'argv':argv,'executable':executable,'executable_sha256':checksum,'requested_threads':threads,
                     'observed_worker_creations':workers,'expected_output_sha256':expected,
                     'output_bytes':replay['products'][family]['intermediate']['size'],
                     'diagnostic_trace_argv':probe}
        diagnostics[mode]=trace.name
        for n in range(6):
            target.unlink(missing_ok=True)
            values,rc=run(executable,argv,stderr)
            output_sha=baseline.sha(target)
            assert rc==0 and output_sha==expected
            warmup.append(dict(mode=mode,n=n+1,wall_ms=values[0],output_sha256=output_sha))
        saved=OUT/f'{mode}.kdbus.o'
        target.replace(saved)
    rng=random.Random(args.seed)
    rows=[]
    for block, order in enumerate(balanced_order(rng,MODES,args.blocks),1):
        for place,mode in enumerate(order,1):
            meta=modes[mode]
            target.unlink(missing_ok=True)
            freq={}
            baseline.cpus(freq,cpus)
            load_1m=os.getloadavg()[0]
            values,rc=run(meta['executable'],meta['argv'],OUT/f'{mode}.stderr')
            size=target.stat().st_size if target.is_file() else None
            output_sha=baseline.sha(target) if target.is_file() else None
            row=dict(block=block,position=place,mode=mode,exit_status=rc,thread_creations_probe=meta['observed_worker_creations'],
                     affinity=','.join(map(str,cpus)),load_1m=load_1m,
                     median_khz=statistics.median(freq.values()) if freq else None,
                     output_sha256=output_sha,**dict(zip(METRICS,[*values,size],strict=True)))
            rows.append(row)
            if rc or size!=meta['output_bytes'] or output_sha!=meta['expected_output_sha256']:
                write_csv(OUT/'measurements.csv',rows)
                raise ValueError(f'Non-equivalent result: {row}')
    for row in frozen_files:
        assert baseline.sha(row['guest_path'])==row['sha256']
    counts=Counter((r['mode'],r['position']) for r in rows)
    assert set(counts.values())=={args.blocks//6}
    write_csv(OUT/'measurements.csv',rows)
    summary=summarize(rows,args.seed)
    write_csv(OUT/'summary.csv',summary)
    write_json(OUT/'design.json',{'cpus':cpus,'host_allowed_cpus':allowed,'seed':args.seed,
        'blocks':args.blocks,'warmup':warmup,'mode_details':modes,'diagnostic_trace_files':diagnostics,
        'timer_sha256':baseline.sha(PRIOR/'evidence/benchmark/bench-timer'),
        'block_design':'Each of six modes is run once per block. Each mode occupies each order position equally.',
        'confidence_method':'Pointwise 95% percentile bootstrap of block-paired ratios of medians, 4000 resamples.',
        'axis':'Percent improvement = (comparator - candidate) / comparator. Negative means regression.',
        'scope':'New equal-affinity test. Tracing, frequency reads, file stat and SHA256 occur outside native timer.'})
    print(f'{len(rows)} valid samples, {len(warmup)} warmups')
    for r in summary:
        if r['metric'] in ('wall_ms','peak_rss_kib'):
            print(r['mode'],r['metric'],r['median'],r['p95'],r['ci95_default_lo'],r['ci95_default_hi'])


if __name__=='__main__':
    main()
