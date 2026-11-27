#!/usr/bin/env python3
"""Re-examine Phase 12 bytes and receipts without writing into its archive."""
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'phase12_controlled_benchmark'
OUT=ROOT/'evidence/review'
sys.path.insert(0,str(PRIOR/'scripts'))
import benchmark_linkers as bench
import compare_arm_elf as elf

EXEC=re.compile(r'^execve\((".*?"), (\[(?:"(?:[^"\\]|\\.)*"(?:, )?)*\]), .*\)\s+= 0$')
WORK='home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0'


def require(ok,message):
    if not ok:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def prior(path):
    return load(PRIOR/path)


def csv_rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def record_file(row):
    path=PRIOR/row['path']
    require(path.stat().st_size==row['size'] and bench.sha(path)==row['sha256'],f'SHA or size mismatch: {path}')
    return path


def review_source_exec():
    original=prior('evidence/build/controlled-builds.json')
    groups=original['groups']
    make={}
    for group in ('A','B'):
        tree=PRIOR/'work'/group/WORK
        files=groups[group]['source_files']
        require(len(files)==53,'Expected 53 prepared members per build')
        require(all(bench.sha(tree/name)==digest for name,digest in files.items()),f'{group} source identity')
        emitted={}
        for line in (PRIOR/f'evidence/build/{group}-build.out').read_text().splitlines():
            if re.fullmatch(r'[0-9a-f]{64}  kernel/.+',line):
                value,name=line.split('  ',1)
                emitted[name]=value
        require(emitted==files,f'{group} prepared source manifest mismatches log')
        require(prior(f'evidence/build/{group}-build.cmd.json')['exit_status']==0,f'{group} build exit')
        make[group]=(tree/'kernel/Makefile').read_bytes()
    a,b=(groups[g]['source_files'] for g in ('A','B'))
    require(a.keys()==b.keys() and [k for k in sorted(a) if a[k]!=b[k]]==['kernel/Makefile'],'Source difference scope')
    line=b'LD = ${CROSS_COMPILE}ld\n'
    require(make['A'].count(line)==1 and make['A'].replace(line,b'',1)==make['B'],'Assignment delta')
    records=[]
    for group in ('A','B'):
        entry=groups[group]
        for stage,output in (('intermediate','intermediate_object'),('final','unstripped_module')):
            link=entry[stage]
            artifact=record_file(entry[output])
            trace=record_file(link['exec_trace'])
            digest=bench.sha(PRIOR/'work/tool-overlays'/link['executable'].lstrip('/'))
            require(digest==link['executable_sha256'],f'{group}/{stage} executable hash')
            matches=[]
            for row in trace.read_text().splitlines():
                if (parsed:=EXEC.match(row)) and Path(json.loads(parsed[1])).as_posix()==link['executable']:
                    matches.append(json.loads(parsed[2]))
            require(matches==[link['argv']],f'{group}/{stage} successful exec argv identity')
            require(link['exit_status']==0 and re.search(r'^exit_group\(0\)',trace.read_text(),re.M), f'{group}/{stage} process exit')
            argv=link['argv']
            require(Path(argv[argv.index('-o')+1]).name==artifact.name, f'{group}/{stage} output association')
            require(artifact.relative_to(PRIOR/'work'/group).as_posix()==argv[argv.index('-o')+1].lstrip('/'),
                    f'{group}/{stage} guest output pathname mismatch')
            cmd=PRIOR/f'evidence/build/selected/{group}-{artifact.name}.cmd'
            saved=shlex.split(cmd.read_text().splitlines()[0].split(':=',1)[1])
            require(saved==argv,f'{group}/{stage} .cmd identity')
            records.append({'group':group,'stage':stage,'successful_exec':link,'artifact':entry[output]})
        record_file(entry['strip_debug_module'])
    require([r['successful_exec']['version'] for r in records]==['GNU BFD 2.43','LLVM LLD 22.1.8','LLVM LLD 22.1.8','LLVM LLD 22.1.8'],
            'Unexpected actual linker sequence')
    return groups,records


def review_frozen(groups):
    frozen=prior('evidence/replay/frozen-inputs.json')
    inputs=frozen['ordered_response_and_objects']
    require(len(inputs)==22 and len(frozen['sdk_resources'])==2,'Frozen input counts')
    for item in inputs+frozen['sdk_resources']:
        record_file(item)
    pairs={}
    for group in ('A','B'):
        entry=groups[group]
        obs=[entry['response'],*entry['ordered_inputs']]
        for row in obs:
            record_file(row)
        pairs[group]=[(item['guest_path'],item['sha256']) for item in obs]
    require(pairs['A']==pairs['B']==[(x['guest_path'],x['sha256']) for x in inputs[:20]],'Input digest/order mismatch')
    require(shlex.split(record_file(inputs[0]).read_text())==[x['guest_path'] for x in inputs[1:20]],'Response order mismatch')
    require([(x['guest_path'],x['sha256']) for x in groups['A']['final_common_inputs']]==
            [(x['guest_path'],x['sha256']) for x in inputs[20:]],'Frozen common final inputs mismatch')
    replay=prior('evidence/replay/link-replay.json')
    for label,group in (('bfd','A'),('lld','B')):
        products=replay['products'][label]
        for item in products.values():
            record_file(item)
        require(products['intermediate']['sha256']==groups[group]['intermediate_object']['sha256'],'Replay/AB composite mismatch')
        require(products['stripped']['size']==groups[group]['strip_debug_module']['size'],'Replay/AB final size mismatch')
        require(replay['commands'][label]['plain']['output']['sha256']==replay['commands'][label]['map']['output']['sha256'],
                'Diagnostic map invocation changed object')
    return frozen,replay


def review_benchmark():
    raw=csv_rows(PRIOR/'LINKER_BENCHMARK_RAW.csv')
    archived=csv_rows(PRIOR/'LINKER_BENCHMARK_SUMMARY.csv')
    design=prior('evidence/benchmark/design.json')
    profiles={k:design['profiles'][k] for k in ('default_threads','one_cpu_one_thread')}
    require(len(raw)==160 and len(archived)==28,'Unexpected original publication counts')
    require(all(r['status']=='0' for r in raw),'Nonzero original measurement status')
    cooked=[]
    blocks={}
    for row in raw:
        profile=row['profile']
        pair=int(row['pair'])
        key=(profile,pair)
        blocks.setdefault(key,[]).append((row['linker'],int(row['order'])))
        require(row['affinity']==','.join(map(str,profiles[profile][0])),f'Wrong affinity for {profile}')
        cooked.append({**row,**{k:(float(row[k]) if k.endswith('_ms') else int(row[k])) for k in bench.FIELDS}})
    for profile in profiles:
        require({pair for p,pair in blocks if p==profile}==set(range(1,41)),f'{profile} pair membership')
        keys={k for k in blocks if k[0]==profile}
        require(all({r[0] for r in blocks[k]}=={'bfd','lld'} and {r[1] for r in blocks[k]}=={1,2}
                    and len(blocks[k])==2 for k in keys),f'{profile} unbalanced pair data')
        for tool in bench.TOOLS:
            require([int(x['pair']) for x in cooked if x['profile']==profile and x['linker']==tool]==list(range(1,41)),
                    f'{profile} samples misaligned with paired bootstrap')
    regenerated=bench.summary(cooked,profiles,40,design['seed'])
    require(len(regenerated)==len(archived),'Summary row missing')
    for derived,old in zip(regenerated,archived,strict=True):
        require(derived.keys()==old.keys(),'Original summary schema mismatch')
        for col,value in derived.items():
            if isinstance(value,(int,float)):
                require(math.isclose(float(old[col]),value,abs_tol=1e-12,rel_tol=1e-12),f'Summary mismatch {col}')
            else:
                require(old[col]==('' if value is None else value),f'Summary mismatch {col}')
    details=[]
    for profile in profiles:
        for linker in bench.TOOLS:
            actual=prior(f'evidence/benchmark/{profile}-{linker}.json')
            require(actual['affinity']==profiles[profile][0],'Thread diagnostic affinity differs')
            trace=(PRIOR/f'evidence/benchmark/{profile}-{linker}.threads.strace').read_text()
            count=len(re.findall(r'CLONE_THREAD.*?= [0-9]+\s*$',trace,re.M))
            require(count==actual['successful_thread_clones_untimed'],'Archived clone count mismatch')
            details.append({'profile':profile,'linker':linker,'affinity':actual['affinity'],'observed_worker_creations':count,
                            'argv':actual['argv'],'tool_sha256':actual['tool_sha256']})
    return {'samples':len(raw),'summary_rows_recomputed':len(regenerated),'pair_blocks':len(blocks),
            'seed':design['seed'],'bootstrap_resamples_per_effect':4000,'profiles':details,
            'summary_headline':[row for row in regenerated if row['metric'] in ('wall_ms','peak_rss_kib')]}


def elf_model(path, with_relocations=False):
    data=path.read_bytes()
    header,sections=elf.parse_sections(data)
    tables=elf.parse_symbols(sections)
    symbols=[]
    for sec_index,table in tables.items():
        for symbol in table:
            related=elf.symbol_section_index(sections[sec_index],sections,symbol)
            symbol['section_index']=related
            symbol['section_key']=elf.section_key(sections[related]) if related else (symbol['section'],1)
        symbols.extend(table[1:])
    result={'path':path,'sha256':bench.sha(path),'sections':sections,'mapping':elf.mapping_model(sections,symbols)}
    if with_relocations:
        readelf=subprocess.check_output(['readelf','-Wr',str(path)],text=True)
        result['relocations']=list(elf.relocation_model(sections,tables,elf.readelf_arm_names(readelf)))
    return result


def review_mapping(groups,frozen,replay):
    paths={}
    for where,entry in groups.items():
        for stage in ('intermediate_object','unstripped_module','strip_debug_module'):
            paths[f'{where}/{stage}']=record_file(entry[stage])
    for where in ('bfd','lld'):
        for stage in ('intermediate','unstripped','stripped'):
            paths[f'{where}/{stage}']=record_file(replay['products'][where][stage])
    mapping={}
    for name,path in paths.items():
        mapping[name]=elf_model(path, name in ('bfd/intermediate','bfd/stripped'))
        require(not mapping[name]['mapping']['findings'],f'{name} has invalid ARM map')
    for x,y,wanted in (('bfd/intermediate','lld/intermediate',101),('bfd/stripped','lld/stripped',81),
                       ('A/strip_debug_module','B/strip_debug_module',81)):
        left,right=mapping[x],mapping[y]
        a,b=left['mapping']['counts'],right['mapping']['counts']
        require(a['a']==b['a']==122 and a.get('t',0)==b.get('t',0)==0 and a['d']-b['d']==wanted,
                'Mapping symbol count mismatch')
        exec_spans=lambda m:{k:v['spans'] for k,v in m['mapping']['sections'].items() if v['executable']}
        require(exec_spans(left)==exec_spans(right),'Changed executable mapping intervals')
    raw=[elf_model(record_file(x)) for x in frozen['ordered_response_and_objects'][1:20]]
    bfd_map=record_file(replay['products']['bfd']['map'])
    origins={}
    for stage,count in (('intermediate',101),('stripped',81)):
        left,right=(mapping[f'{name}/{stage}'] for name in ('bfd','lld'))
        comparator=elf.compare_maps(left,right)
        elf.attach_map_sources(comparator,raw,bfd_map,mapping['bfd/intermediate'],left)
        lost=[marker for section in comparator for marker in section['removed']]
        require(len(lost)==count and all(m['kind']=='d' and m.get('input_origin_candidates') for m in lost), 'Lost markers unaccounted')
        require(all(all(o['source_type']=='BFD_SYNTHESIZED_AT_DATA_CONTRIBUTION' for o in m['input_origin_candidates'])
                    for m in lost), 'Lost marker failed BFD synthesis attribution')
        origins[stage]=dict(Counter(m['origin_status'] for m in lost))
        save(OUT/f'mapping-{stage}-review.json',comparator)
    require(origins=={'intermediate':{'LINK_MAP_UNIQUE':101},'stripped':{'LINK_MAP_UNIQUE':75,'LINK_MAP_MULTIPLE':6}},
            'Marker origin counts differ from Phase 12')
    for pair in (('bfd/stripped','lld/stripped'),('A/strip_debug_module','B/strip_debug_module')):
        left,right=(mapping[x] for x in pair)
        require(all(ch['effective_spans_equal'] for ch in elf.compare_maps(left,right)),f'{pair} mapping boundaries differ')
    return {'input_objects':len(raw),'counts':{k:v['mapping']['counts'] for k,v in mapping.items()},
            'origin_counts':origins,'executable_mapping_spans_equal':True,'final_effective_spans_equal':True}


def review_gcc():
    gcc=prior('evidence/gcc/status.json')
    require(gcc['gcc_compatibility']==gcc['gcc_real_build']=='PASS' and gcc['architecture']=='ARMv7l non-RT',
            'GCC scope or aggregate status')
    require(len(gcc['runs'])==3 and gcc['kernel_release']=='6.12.80-arm-rpi4-v7l','GCC lane count/release')
    for lane,run in gcc['runs'].items():
        require(all(run['compared'].values()) and run['module_count']==7 and run['module_import_crcs_each']==345, f'{lane} GCC outcome')
        for href in run['linker_execution_receipts']:
            receipt=prior(href)
            for stage,digest in (('kdbus.o',run['kdbus_intermediate_sha256']),('kdbus.ko',run['kdbus_unstripped_sha256'])):
                row=receipt[stage]
                require(row['exit_status']==0 and row['output_sha256']==digest and
                        'execve(' in row['exec_trace'] and 'exit_group(0)' in row['exit_trace'],f'{lane} process evidence')
            installed=PRIOR/Path(href).parent/'kdbus.installed.ko'
            require(bench.sha(installed)==run['kdbus_installed_sha256'],f'{lane} installed artifact identity')
    return gcc


def main():
    require(load(OUT/'phase12-bundle.cmd.json')['exit_status']==0,'Phase 12 original archive integrity failed')
    groups,execs=review_source_exec()
    frozen,replay=review_frozen(groups)
    evidence={'status':'PASS','prepared_member_count_each':53,'only_changed_prepared_source':'kernel/Makefile',
              'frozen_ordered_intermediate_objects':19,'frozen_common_final_objects':2,
              'frozen_sdk_resources':2,'linker_execs':execs,
              'benchmark':review_benchmark(),'mapping':review_mapping(groups,frozen,replay),'gcc':review_gcc(),
              'historical_qb_ratings':'UNCHANGED'}
    save(OUT/'audit.json',evidence)
    print('PASS: source, frozen inputs, four actual linker execs, 160 benchmark rows, ARM map lineage, three GCC pairs')


if __name__=='__main__':
    main()
