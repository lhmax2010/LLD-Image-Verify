#!/usr/bin/env python3
"""Measure the same real ARM relocatable link with the two observed native linkers."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'evidence/benchmark'
SDK = '/boot/kernel/devel/kernel-devel-arm-rpi4'
TOOLS = ('bfd','lld')
FIELDS = ['wall_ms','user_ms','system_ms','peak_rss_kib','major_faults','minor_faults','output_bytes']
ENV = {'LC_ALL':'C','TZ':'UTC','PATH':'/usr/bin:/bin'}
RAW_FIELDS = ['profile','pair','order','linker','status','threads_hint','affinity','load1','median_cpu_khz',
              *FIELDS]


def sha(path):
    with open(path, 'rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def quantile(values, pct):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered)*pct)-1)]


def cpus(frequencies, affinity):
    for cpu in affinity:
        path = Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq')
        try:
            frequencies[cpu] = int(path.read_text())
        except (OSError, ValueError):
            continue


def run_one(executable, argv, stderr):
    timer = EVIDENCE / 'bench-timer'
    result = subprocess.run([str(timer), str(stderr), executable, *argv], env=ENV,
                            capture_output=True, text=True, check=True)
    wall, user, system, rss, major, minor, status = result.stdout.split()
    return [float(wall), float(user), float(system), int(rss), int(major), int(minor)], int(status)


def paired_ci(a, b, prng, resamples=4000):
    n = len(a)
    improvements = []
    for _ in range(resamples):
        ix = prng.choices(range(n), k=n)
        left, right = statistics.median(a[i] for i in ix), statistics.median(b[i] for i in ix)
        if left > 0:
            improvements.append(100*(left-right)/left)
    return (quantile(improvements,.025), quantile(improvements,.975)) if improvements else (None,None)


def summary(raw, profiles, samples, seed):
    rows = []
    rng = random.Random(seed)
    for profile in profiles:
        for metric in FIELDS:
            series = {tool: [row[metric] for row in raw if row['profile']==profile and row['linker']==tool]
                      for tool in TOOLS}
            assert all(len(values)==samples for values in series.values())
            left, right = (statistics.median(series[t]) for t in TOOLS)
            improvement = (100*(left-right)/left) if left else None
            low, high = paired_ci(*series.values(),rng)
            if low is None:
                verdict = 'NOT_APPLICABLE_ZERO_BASELINE'
            elif low>0:
                verdict = 'MEASURED_AND_ATTRIBUTED'
            elif high<0:
                verdict = 'REGRESSION'
            else:
                verdict = 'NO_SIGNIFICANT_BENEFIT'
            for linker, values in series.items():
                rows.append(dict(profile=profile,metric=metric,linker=linker,samples=samples,mean=statistics.mean(values),
                                 median=statistics.median(values),stddev=statistics.stdev(values),p95=quantile(values,.95),
                                 min=min(values),max=max(values),improvement_pct=improvement,ci95_lower=low,
                                 ci95_upper=high,classification=verdict,
                                 method='BFD-relative ratio of medians; paired percentile bootstrap, 4000 resamples'))
    return rows


def write_csv(path, rows, fields):
    with path.open('w', newline='') as file:
        writer=csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--pairs', type=int, default=40)
    cli.add_argument('--seed', type=int, default=20261126)
    cli.add_argument('--cpus', default='4,5,6,7')
    args=cli.parse_args()
    if args.pairs<30:
        cli.error('At least 30 measured pairs are required')
    allocations = sorted(set(map(int,args.cpus.split(','))))
    if not set(allocations) <= os.sched_getaffinity(0):
        cli.error('All specified CPUs must be available to this process')

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT/'evidence/replay/link-replay.json').read_text())
    expected = {t: source['products'][t]['intermediate']['sha256'] for t in TOOLS}
    record = json.loads((ROOT/'evidence/replay/frozen-inputs.json').read_text())
    for member in record['ordered_response_and_objects']:
        assert sha(member['guest_path']) == member['sha256']
    plans = {t: source['commands'][t]['plain'] for t in TOOLS}
    profiles = {'default_threads':(allocations,False),'one_cpu_one_thread':([allocations[0]],True)}
    original = sorted(os.sched_getaffinity(0))
    raw, warmups = [],[]
    rng = random.Random(args.seed)
    os.chdir(SDK)
    for profile,(affinity, single) in profiles.items():
        os.sched_setaffinity(0,affinity)
        commands={}
        for tool,plan in plans.items():
            argv=plan['argv'].copy()
            out=EVIDENCE/f'{tool}-{profile}.o'
            argv[argv.index('-o')+1]=str(out)
            if single and tool=='lld':
                argv.append('--threads=1')
            commands[tool]=(plan['exec_path'],argv,out)

        for tool,(executable,argv,out) in commands.items():
            stderr=EVIDENCE/f'{profile}-{tool}.stderr'
            stderr.write_bytes(b'')
            for i in range(5):
                out.unlink(missing_ok=True)
                values, rc=run_one(executable,argv,stderr)
                if rc or sha(out)!=expected[tool]:
                    raise ValueError(f'Invalid warmup {profile}/{tool}/{i}: {rc}')
                warmups.append(dict(profile=profile,linker=tool,warmup=i+1,exit_status=rc,
                                    wall_ms=values[0],output_sha256=expected[tool]))
            thread_trace=EVIDENCE/f'{profile}-{tool}.threads.strace'
            shell_argv=['/usr/bin/bash','-c','exec -a "$1" "$2" "${@:3}"','bash',argv[0],executable,*argv[1:]]
            subprocess.run(['/usr/bin/strace','-f','-q','-e','trace=clone,clone3','-o',str(thread_trace),*shell_argv],
                           env=ENV,check=True)
            assert sha(out)==expected[tool]
        for pair in range(1,args.pairs+1):
            order=list(TOOLS)
            rng.shuffle(order)
            for place,tool in enumerate(order,1):
                executable,argv,out=commands[tool]
                out.unlink(missing_ok=True)
                freq={}
                cpus(freq,affinity)
                load=os.getloadavg()[0]
                values,rc=run_one(executable,argv,EVIDENCE/f'{profile}-{tool}.stderr')
                size=out.stat().st_size if out.exists() else None
                row=dict(profile=profile,pair=pair,order=place,linker=tool,status=rc,
                         threads_hint='1' if single else 'linker default',affinity=','.join(map(str,affinity)),
                         load1=load,median_cpu_khz=statistics.median(freq.values()) if freq else None)
                row.update(zip(FIELDS,[*values,size],strict=True))
                raw.append(row)
                if rc or size!=source['products'][tool]['intermediate']['size']:
                    write_csv(ROOT/'LINKER_BENCHMARK_RAW.csv',raw,RAW_FIELDS)
                    raise ValueError(f'Failed sample {profile}/{pair}/{tool}: {rc}, {size}')
        for tool,(_,_,out) in commands.items():
            assert sha(out)==expected[tool]
        for tool,(exe,argv,_) in commands.items():
            trace=(EVIDENCE/f'{profile}-{tool}.threads.strace').read_text()
            created=len(re.findall(r'CLONE_THREAD.*?= [0-9]+\s*$',trace,re.M))
            (EVIDENCE/f'{profile}-{tool}.json').write_text(json.dumps(
                dict(argv=argv,exec_path=exe,tool_sha256=sha(exe),successful_thread_clones_untimed=created,
                     affinity=affinity,measured_output_sha256=expected[tool],linker_options_unchanged=not(single and tool=='lld')),indent=2)+'\n')

    os.sched_setaffinity(0,original)
    for member in record['ordered_response_and_objects']:
        assert sha(member['guest_path'])==member['sha256']
    write_csv(ROOT/'LINKER_BENCHMARK_RAW.csv',raw,RAW_FIELDS)
    aggregate=summary(raw,profiles,args.pairs,args.seed)
    write_csv(ROOT/'LINKER_BENCHMARK_SUMMARY.csv',aggregate,list(aggregate[0]))
    (EVIDENCE/'design.json').write_text(json.dumps(dict(original_affinity=original,profiles=profiles,seed=args.seed,
            valid_pairs_per_profile=args.pairs,warmups=warmups,revision='low-RSS native fork/wait4 timer',
            clock='clock_gettime(CLOCK_MONOTONIC) in native timer',
            scope='One actual linker child per measurement. Tracing, hashing, warmups and ELF analysis outside timed region.',
            confidence_method='95% paired bootstrap ratio of medians. Local shared host; intervals omit between-host and between-day variation.'),
            indent=2)+'\n')
    print(f'PASS: {len(raw)} measurements and {len(warmups)} warmups')
    for r in aggregate:
        if r['linker']=='lld' and r['metric'] in ('wall_ms','peak_rss_kib'):
            print(r['profile'],r['metric'],r['improvement_pct'],r['ci95_lower'],r['ci95_upper'],r['classification'])


if __name__=='__main__':
    main()
