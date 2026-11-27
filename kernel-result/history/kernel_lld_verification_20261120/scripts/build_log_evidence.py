#!/usr/bin/env python3
"""Index the target ARMv7l non-RT link steps in the pinned Tizen build logs."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path('evidence/build')
KERNEL = BUILD / 'linux-rpi-armv7l.out'
EXTERNAL = BUILD / 'linux-tizen-modules-armv7l.out'
RELEASE = '6.12.80-arm-rpi4-v7l'
KERNEL_RPM = 'arm-rpi4-linux-kernel-modules-6.12.80-0.armv7l.rpm'
EXTERNAL_RPM = 'linux-tizen-modules-rpi4-11.0.0-0.armv7l.rpm'
PREFIX = f'/lib/modules/{RELEASE}/'

def read_log(path):
    return list(enumerate((ROOT / path).read_text(errors='replace').splitlines(), 1))

def record(path, line, raw):
    return {'evidence': str(path), 'line': line, 'raw': raw}

def unique(lines, path, predicate):
    return unique_match([record(path, line, raw) for line, raw in lines if predicate(raw)])

def unique_match(matches):
    if len(matches) != 1:
        raise ValueError(f'Expected one matching log event, found {len(matches)}: {matches}')
    return matches[0]

def module_events(path, lines, target_range, payload_subdir, rpm, package_write):
    selected = [pair for pair in lines if target_range[0]['line'] <= pair[0] < target_range[1]['line']]
    install_pattern = re.compile(r'\sINSTALL\s+\S*(' + re.escape(PREFIX) + r'\S+\.ko)$')
    installations = {}
    for index, raw in lines:
        match = install_pattern.search(raw)
        if match:
            payload = match[1]
            if payload in installations:
                raise ValueError(f'Duplicate install event for {payload}')
            installations[payload] = record(path, index, raw)

    prerequisites = [pair for pair in lines if pair[0] < target_range[0]['line']]
    selector = unique(prerequisites, path, lambda raw: '+ export LLVM=1' in raw)
    build_done = unique(lines, path, lambda raw: ' finished "build ' in raw)
    result = []
    for index, raw in selected:
        match = re.search(r'\sLD \[M\]\s+(\S+\.ko)$', raw)
        if not match:
            continue
        build_path = match[1]
        relative_path = build_path.split('/kernel/', 1)[1] if payload_subdir == 'extra' else build_path
        payload_path = PREFIX + payload_subdir + '/' + relative_path
        installed = installations.pop(payload_path, None)
        result.append({
            'module_basename': PurePosixPath(relative_path).name,
            'package_rpm': rpm,
            'payload_path': payload_path,
            'build_output': build_path,
            'event': record(path, index, raw),
            'install_event': installed,
            'llvm_selection': selector,
            'rpm_write': package_write,
            'build_completion': build_done,
            'observed_successful_install_and_packaging': bool(installed),
            'exact_final_link_command': None,
            'actual_linker_path': None,
            'proves_final_linker_identity': False,
        })
    return result, sorted(installations)

def write_json(name, data):
    (ROOT / BUILD / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def main():
    kernel = read_log(KERNEL)
    external = read_log(EXTERNAL)
    kernel_scope = [
        unique(kernel, KERNEL, lambda raw: bool(re.search(r'\+ make O=build/arm-rpi4 -j\d+$', raw))),
        unique(kernel, KERNEL, lambda raw: '+ echo -arm-rpi4-rt' in raw),
    ]
    external_scope = [
        unique(external, EXTERNAL, lambda raw: '+ make -C kernel KERNELDIR=/boot/kernel/devel/kernel-devel-arm-rpi4' == raw.split('] ', 1)[-1]),
        unique(external, EXTERNAL, lambda raw: '+ make -C kernel clean KERNELDIR=/boot/kernel/devel/kernel-devel-arm-rpi4-rt' in raw),
    ]
    kernel_module_write = unique(kernel, KERNEL, lambda raw: 'Wrote:' in raw and raw.endswith('/' + KERNEL_RPM))
    external_module_write = unique(external, EXTERNAL, lambda raw: 'Wrote:' in raw and raw.endswith('/' + EXTERNAL_RPM))
    in_tree, in_tree_unmatched = module_events(KERNEL, kernel, kernel_scope, 'kernel', KERNEL_RPM, kernel_module_write)
    out_tree, out_tree_unmatched = module_events(EXTERNAL, external, external_scope, 'extra', EXTERNAL_RPM, external_module_write)
    observations = in_tree + out_tree
    counts = Counter(item['package_rpm'] for item in observations)
    write_json('module-final-commands.json', {
        'actual_final_link_commands': [],
        'quiet_link_observations': observations,
        'observations_by_rpm': dict(counts),
        'install_without_matching_link': in_tree_unmatched + out_tree_unmatched,
        'selection': 'ARMv7l non-RT target scope only',
        'limitations': 'Quiet Kbuild records completed LD [M] target steps under LLVM=1; final linker argv and executed ld.lld absolute path are unavailable.',
    })

    scoped = [pair for pair in kernel if kernel_scope[0]['line'] <= pair[0] < kernel_scope[1]['line']]
    build_start = unique(kernel, KERNEL, lambda raw: ' started "build linux-rpi.spec"' in raw)
    build_time = datetime.strptime(build_start['raw'].split(' at ', 1)[1].rstrip('.'), '%a %b %d %H:%M:%S UTC %Y').replace(tzinfo=timezone.utc)
    uts = unique(scoped, KERNEL, lambda raw: 'UPD     include/generated/utsversion.h' in raw)
    marker = int(re.match(r'\[\s*(\d+)s\]', uts['raw'])[1])
    writes = [record(KERNEL, line, raw) for line, raw in kernel if 'Wrote:' in raw]
    explicit_ld_lld_lines = {
        str(path): [record(path, line, raw) for line, raw in lines if re.search(r'\bld\.(lld|bfd)\b', raw)]
        for path, lines in ((KERNEL, kernel), (EXTERNAL, external))
    }
    write_json('kernel-build-log-events.json', {
        'normal_target_scope': kernel_scope,
        'configured_target': unique(kernel, KERNEL, lambda raw: '+ make O=build/arm-rpi4 olddefconfig' in raw),
        'kernel_build_start': build_start,
        'kernel_compile_header_update': unique(scoped, KERNEL, lambda raw: 'UPD     include/generated/compile.h' in raw),
        'utsversion_update': uts,
        'derived_uts_update_utc': (build_time + timedelta(seconds=marker)).isoformat(),
        'quiet_partial_link': unique(scoped, KERNEL, lambda raw: bool(re.search(r'\bLD\s+vmlinux\.o$', raw))),
        'quiet_final_link': unique(scoped, KERNEL, lambda raw: bool(re.search(r'\bLD\s+vmlinux$', raw))),
        'quiet_arm_decompressor_link': unique(scoped, KERNEL, lambda raw: bool(re.search(r'\bLD\s+arch/arm/boot/compressed/vmlinux$', raw))),
        'kernel_image_ready': unique(scoped, KERNEL, lambda raw: raw.endswith('Kernel: arch/arm/boot/zImage is ready')),
        'kernel_llvm_selection': in_tree[0]['llvm_selection'],
        'external_llvm_selection': out_tree[0]['llvm_selection'],
        'devel_copy_cmd_exclusion': unique(kernel, KERNEL, lambda raw: "--exclude '*.cmd'" in raw and ' build/arm-rpi4/ ' in raw),
        'kernel_build_completion': in_tree[0]['build_completion'],
        'rpm_writes': writes,
        'linker_executable_mentions': explicit_ld_lld_lines,
        'exact_final_link_command': None,
    })
    print(f'Quiet final-module link observations: {len(observations)}')
    print(f'Observed matching installs: {sum(item["observed_successful_install_and_packaging"] for item in observations)}')

if __name__ == '__main__':
    main()
