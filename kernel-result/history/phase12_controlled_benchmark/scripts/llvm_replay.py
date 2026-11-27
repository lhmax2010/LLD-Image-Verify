#!/usr/bin/env python3
"""Audit controlled exec records and replay the captured links on frozen real objects."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GUEST = Path('/home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0')
SDK = Path('/boot/kernel/devel/kernel-devel-arm-rpi4')
STRIPPED = GUEST / 'lib/modules/6.12.80-arm-rpi4-v7l/extra/kdbus/kdbus.ko'
INTERMEDIATE = GUEST / 'kernel/kdbus/kdbus.o'
FINAL = INTERMEDIATE.with_suffix('.ko')
EXEC = re.compile(r'^execve\((".*?"), (\[(?:"(?:[^"\\]|\\.)*"(?:, )?)*\]), .*\)\s+= 0$')
SELECTED = ROOT / 'evidence/build/selected'
REPLAY = ROOT / 'evidence/replay'
WORK = ROOT / 'work'
DRIVER = ['bash', 'scripts/tizen_run.sh']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def data(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def host(group, guest):
    return WORK / group / 'home' / Path(guest).relative_to('/home')


def reference(path):
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': sha(path), 'size': path.stat().st_size}


def process(group, name, argument_ok, executable_ok):
    matches = []
    for path in sorted((ROOT/'evidence/build').glob(f'{group}.exec.*')):
        payload = path.read_text(errors='replace')
        if not re.search(r'^exit_group\(0\)', payload, re.M):
            continue
        for line in payload.splitlines():
            match = EXEC.match(line)
            if match is None:
                continue
            argv = json.loads(match[2])
            exe = Path(json.loads(match[1])).as_posix()
            if executable_ok(exe) and argument_ok(argv):
                matches.append((path, argv, exe, payload))
    if len(matches) != 1:
        raise ValueError(f'Expected one {group} {name} successful exec, got {[(m[0],m[2]) for m in matches]}')
    path, argv, exe, payload = matches[0]
    proof = SELECTED / f'{group}-{name}.strace'
    proof.write_text(payload)
    return {'executable': exe, 'argv': argv, 'exit_status': 0, 'exec_trace': reference(proof), 'pid': int(path.suffix[1:])}


def linking(group, name, target, allowed):
    def has_output(cmd):
        return '-o' in cmd and cmd[cmd.index('-o')+1] == str(target)

    record = process(group, name, has_output, lambda executable: executable in allowed)
    path = WORK / 'tool-overlays' / record['executable'].lstrip('/')
    record['executable_sha256'] = sha(path)
    version = 'GNU BFD 2.43' if record['executable'].endswith('/ld') else 'LLVM LLD 22.1.8'
    record['version'] = version
    record['version_probe'] = 'evidence/build/probe-ready.out'
    return record


def audit():
    SELECTED.mkdir(parents=True, exist_ok=True)
    REPLAY.mkdir(parents=True, exist_ok=True)
    builds = {}
    for group in ('A', 'B'):
        rc = json.loads((ROOT / f'evidence/build/{group}-build.cmd.json').read_text())
        if rc['exit_status'] != 0:
            raise ValueError(f'Build {group} did not finish')
        intermediate = linking(group, 'intermediate', INTERMEDIATE, {'/emul/usr/bin/ld', '/emul/usr/bin/lld'})
        final = linking(group, 'final', FINAL, {'/emul/usr/bin/lld'})
        response = [Path(arg[1:]) for arg in intermediate['argv'] if arg.startswith('@')]
        if len(response) != 1:
            raise ValueError('Expected the single captured kdbus.mod response')
        ordered = shlex.split(host(group, response[0]).read_text())
        constituents = [{'guest_path': p, **reference(host(group, p))} for p in ordered]
        meta_parts = [Path(p) for p in final['argv'] if p.endswith('.o') and p != str(INTERMEDIATE)]
        meta = [{'guest_path': str(p), **reference(host(group, p))} for p in meta_parts]
        post = {}
        for name, path in (('pahole', '/mnt/entry/pahole'),
                           ('resolve', 'tools/bpf/resolve_btfids/resolve_btfids'),
                           ('strip', '/emul/usr/bin/llvm-objcopy')):
            def module(argv):
                return (bool(argv) and Path(argv[-1]).name == 'kdbus.ko' and
                        ('--strip-debug' in argv if name == 'strip' else argv[-1] == str(FINAL)))
            post[name] = process(group, name, module, lambda exe: exe == path)
        manifest = [line for line in (ROOT/f'evidence/build/{group}-build.out').read_text().splitlines()
                    if re.fullmatch(r'[0-9a-f]{64}  kernel/.+', line)]
        if not manifest:
            raise ValueError('No prepared source file manifest')
        builds[group] = {'successful_build': True, 'source_files': dict(line.split('  ',1)[::-1] for line in manifest),
                         'intermediate': intermediate, 'final': final, 'postprocessing': post,
                         'response': {'guest_path': str(response[0]), **reference(host(group, response[0]))},
                         'ordered_inputs': constituents, 'final_common_inputs': meta,
                         'intermediate_object': reference(host(group, INTERMEDIATE)),
                         'unstripped_module': reference(host(group, FINAL)), 'strip_debug_module': reference(host(group, STRIPPED))}
        for p in (INTERMEDIATE, FINAL):
            original = host(group, p).with_name('.' + p.name + '.cmd')
            shutil.copyfile(original, SELECTED / f'{group}-{p.name}.cmd')
    a, b = builds['A'], builds['B']
    diffs = [key for key in sorted(set(a['source_files']) | set(b['source_files']))
             if a['source_files'].get(key) != b['source_files'].get(key)]
    assert diffs == ['kernel/Makefile']
    a_make, b_make = (host(g, GUEST/'kernel/Makefile').read_bytes() for g in ('A', 'B'))
    assignment = b'LD = ${CROSS_COMPILE}ld\n'
    assert a_make.count(assignment) == 1 and a_make.replace(assignment, b'', 1) == b_make
    assert [(r['guest_path'],r['sha256']) for r in a['ordered_inputs']] == [(r['guest_path'],r['sha256']) for r in b['ordered_inputs']]
    final_diffs = [left['guest_path'] for left,right in zip(a['final_common_inputs'],b['final_common_inputs'],strict=True)
                   if left['sha256'] != right['sha256']]
    assert final_diffs == [str(INTERMEDIATE.with_suffix('.mod.o'))]
    modpost_sources = [host(g, INTERMEDIATE.with_suffix('.mod.c')).read_text().splitlines() for g in ('A','B')]
    classify = lambda lines: sorted(line for line in lines if re.match(r'\s*\{ 0x[0-9a-f]+, "',line))
    assert len(classify(modpost_sources[0])) == 154
    assert classify(modpost_sources[0]) == classify(modpost_sources[1])
    assert [line for line in modpost_sources[0] if line not in classify(modpost_sources[0])] == [line for line in modpost_sources[1] if line not in classify(modpost_sources[1])]
    assert a['response']['sha256'] == b['response']['sha256']
    assert a['intermediate']['argv'][1:] == b['intermediate']['argv'][1:]
    assert a['final']['argv'] == b['final']['argv']
    for step in a['postprocessing']:
        assert a['postprocessing'][step]['argv'] == b['postprocessing'][step]['argv'], step
    assert a['intermediate']['version'].startswith('GNU') and b['intermediate']['version'].startswith('LLVM')
    assert all(builds[g]['final']['version'].startswith('LLVM') for g in builds)
    data(ROOT/'evidence/build/controlled-builds.json', {'groups': builds, 'source_delta': diffs,
         'response_and_ordered_inputs_byte_identical': True, 'final_input_differences': final_diffs,
         'modpost_c_source_difference': 'Ordering of the same 154 __versions entries',
         'exec_observation_scope': 'PHASE12_LOCAL_CONTROLLED_MODULE_BUILD_ONLY'})
    return builds


def freeze(builds):
    source = builds['A']
    paths = [source['response'], *source['ordered_inputs'], *source['final_common_inputs']]
    records = []
    for row in paths:
        dest = host('replay', row['guest_path'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row['path'], dest)
        assert sha(dest) == row['sha256']
        records.append({'guest_path': row['guest_path'], **reference(dest)})
    resources = [SDK/'scripts/module.lds', SDK/'vmlinux']
    sdk_records = [{'guest_path': str(p), **reference(WORK/'sdk'/p.relative_to('/'))} for p in resources]
    data(REPLAY/'frozen-inputs.json', {'ordered_response_and_objects': records, 'sdk_resources': sdk_records})
    return records


def call(record, argv, cwd, env='', prefix=''):
    return ('cd ' + shlex.quote(str(cwd)) + '\n' + env
            + prefix + shlex.join(['exec', '-a', argv[0], record['executable'], *argv[1:]]) + '\n')


def replay(builds):
    frozen = freeze(builds)
    commands, products = {}, {}
    def inplace(record, argv):
        return shlex.join(argv if record['executable'][0] != '/' else [record['executable'], *argv[1:]])
    for group, label in (('A','bfd'), ('B','lld')):
        current = builds[group]
        output = GUEST/'replayed'/label
        out_host = host('replay', output)
        out_host.mkdir(parents=True, exist_ok=True)
        stages = {}
        for stage, with_map in (('plain', False), ('map', True)):
            outfile = str(output/('kdbus.o' if not with_map else 'mapped/kdbus.o'))
            (out_host/'mapped').mkdir(exist_ok=True)
            argv = current['intermediate']['argv'].copy()
            argv[argv.index('-o')+1] = outfile
            if with_map:
                argv.append('-Map=' + str(output/'link.map'))
            command = call(current['intermediate'], argv, SDK)
            subprocess.run([*DRIVER, 'replay', '/bin/bash', '-ec', command], cwd=ROOT, check=True)
            stages[stage] = {'argv': argv, 'exec_path': current['intermediate']['executable'],
                             'output': reference(host('replay', outfile))}
        assert stages['plain']['output']['sha256'] == stages['map']['output']['sha256'] == current['intermediate_object']['sha256']
        final = current['final']['argv'].copy()
        final[final.index('-o')+1] = str(output/'kdbus.ko')
        final[final.index(str(INTERMEDIATE))] = str(output/'kdbus.o')
        bound = current['postprocessing']
        pahole = [*bound['pahole']['argv'][:-1], str(output/'kdbus.ko')]
        resolve = [*bound['resolve']['argv'][:-1], str(output/'kdbus.ko')]
        stripped = output/'stripped/kdbus.ko'
        (out_host/'stripped').mkdir(exist_ok=True)
        strip = [*bound['strip']['argv'][:-1], str(stripped)]
        command = 'set -eu\ncd '+str(SDK)+'\n' + '( ' + call(current['final'], final, SDK).strip() + '\n)\n'
        command += 'LLVM_OBJCOPY=llvm-objcopy ' + inplace(bound['pahole'],pahole) + '\n'
        command += inplace(bound['resolve'],resolve) + '\n' + shlex.join(['cp', str(output/'kdbus.ko'), str(stripped)]) + '\n'
        command += call(bound['strip'],strip,SDK)
        script = REPLAY/f'{label}-final.sh'
        script.write_text(command)
        subprocess.run([*DRIVER, 'replay', '/bin/bash', '-ec', command], cwd=ROOT, check=True)
        products[label] = {'intermediate': stages['plain']['output'], 'map': reference(out_host/'link.map'),
            'unstripped': reference(out_host/'kdbus.ko'), 'stripped': reference(host('replay', stripped))}
        commands[label] = stages | {'final_argv': final, 'final_postprocessing_script': reference(script)}
    for row in frozen:
        assert sha(ROOT/row['path']) == row['sha256']
    assert commands['bfd']['plain']['argv'][1:commands['bfd']['plain']['argv'].index('-o')+1] == commands['lld']['plain']['argv'][1:commands['lld']['plain']['argv'].index('-o')+1]
    data(REPLAY/'link-replay.json', {'status':'PASS','commands':commands,'products':products,
         'same_input_object_hash_and_order': True, 'common_final_metadata_objects_from': 'A for both replay links', 'intermediate_extra_options': 'Only separate output pathname. Diagnostic map output is byte-compared and excluded from timings.',
         'replay_matches_controlled_final': {
             label:{'unstripped': products[label]['unstripped']['sha256']==builds[g]['unstripped_module']['sha256'],
                    'stripped': products[label]['stripped']['sha256']==builds[g]['strip_debug_module']['sha256']}
             for g,label in (('A','bfd'),('B','lld'))}})
    print(json.dumps(products, indent=2))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('stage', choices=('audit', 'replay'))
    opt = cli.parse_args()
    builds = audit()
    if opt.stage == 'replay':
        replay(builds)


if __name__ == '__main__':
    main()
