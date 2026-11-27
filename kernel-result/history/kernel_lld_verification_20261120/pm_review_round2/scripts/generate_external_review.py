#!/usr/bin/env python3
"""Render the external link matrix from verified module bindings."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT/'evidence/external'
KERNEL = ROOT/'evidence/kernel/source'

def load(name):
    return json.loads((EVID/name).read_text())

def main():
    bind=load('target-bindings.json')
    contents=load('source-content-inventory.json')
    kbuild=(KERNEL/'Makefile').read_text().splitlines()
    modfinal=(KERNEL/'scripts/Makefile.modfinal').read_text().splitlines()
    assert 'ld.lld' in kbuild[479] and '$(LD)' in modfinal[37]
    assert not contents['prebuilt_findings'] and len(bind['rows'])==7
    sdk='/boot/kernel/devel/kernel-devel-arm-rpi4'
    wrapper='evidence/external/linux-tizen-modules.spec'
    spec=(ROOT/wrapper).read_text().splitlines()
    final_rule='evidence/kernel/source/scripts/Makefile.modfinal:36–40,59–63'
    observed=next(line for line in (EVID/'external-buildlog-full.out').read_text().splitlines()
                 if 'M=/home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/kernel CFLAGS_MODULE=' in line
                 and 'kernel-devel-arm-rpi4 ' in line)
    make=observed.split('] ',1)[1]
    reasons=(
        'RPM log shows LLVM=1, the exact packaged SDK, each source compilation, final .ko link, '
        'strip/install and exact RPM write in the non-RT scope. '
        'The source Makefile LD assignment is confined to object-build and modpost descendants. '
        'The final modfinal sibling gets LD=ld.lld from the Kbuild parent, and both evidenced '
        'historical ld.lld executables are LLD 22.1.8. Exact executed path and argv are unavailable.'
    )
    rows=[]
    for item in bind['rows']:
        composite=item['name']=='kdbus'
        spec_line=next(i for i,line in enumerate(spec,1)
            if line.startswith('%{KMOD_PATH}/*rpi4-v7l/extra/') and
            line.split('/extra/',1)[1]==item['module_path'].split('/extra/',1)[1])
        source_desc = 'kdbus/Makefile L1–22，19 个源码对象' if composite else item['source_inputs'][0]
        source_make={
            'dm_bow':'Makefile L34','extcon_usb_fixed':'Makefile L35',
            'inform_reboot':'Makefile L36','logger':'Makefile L37','proc_tsm':'Makefile L38',
            'kdbus':'Makefile L39 → kdbus/Makefile L1–22',
            'zlogger':'Makefile L40 → zlogger/Makefile L2',
        }[item['name']]
        row=dict(module_name=item['name'],module_path=item['module_path'],device_path=item['device_path'],
            binary_rpm=item['binary_rpm'],source_rpm=item['binary_source_rpm'],
            source_provider_binary_rpm=item['provider_rpm'],source_provider_source_rpm=item['provider_source_rpm'],
            source_version='11.0.0-0',
            packaging_revision='458baad02d812098938663971d1b8560a4813375',
            implementation_revision='25797e8af7ed95a5783bbe84c11959560aaf7e92',
            build_spec=f'{wrapper}:159,245–268,331–335,{spec_line}',source_make_rule=source_make,
            build_entry_point=f'make -C kernel KERNELDIR={sdk} (historical log L574); external Makefile L42–43',
            kernel_build_directory=sdk,
            effective_llvm='LLVM=1 exported in external RPM build at log L565–566, inherited by Kbuild',
            effective_ld='ld.lld (static rule resolution for final .ko, expected LLD 22.1.8)',
            recursive_make_arguments=make,final_link_rule=final_rule,
            sources=source_desc,actual_compiled_sources=' | '.join(item['source_inputs']),
            object_build_log_lines=' '.join(str(x['line']) for x in item['build_log_cc']),
            prebuilt_object_presence='NONE_FOUND: exact source-provider payload and wrapper Source0; all source objects traced to CC',
            linker_override_risk=('Known external LD assignment applies to object-build descendants. '
                + ('GNU BFD plausible for intermediate kdbus.o (log L612). ' if composite else
                   'No composite object; disabled CONFIG_LTO_CLANG single-object relink. ')
                + 'Scope isolated from final modfinal sibling.'),
            build_link_line=item['build_log_final_link']['line'],build_install_line=item['build_log_install']['line'],
            intermediate_link_line=item['build_log_intermediate_link']['line'] if composite else None,
            build_log_evidence=f'evidence/external/external-buildlog-full.out#L{item["build_log_final_link"]["line"]}; '
                f'INSTALL L{item["build_log_install"]["line"]}; package write L853',
            payload_sha256=item['payload_sha256'],device_sha256=item['device_sha256'],
            evidence_level='E3',evidence_level_name='ENGINEERING_VERIFIED',
            final_verdict=item['round1_classification'],engineering_verdict='FINAL_LINK_ENGINEERING_VERIFIED',
            engineering_reason=reasons+(' kdbus.o is an intermediate BFD candidate outside this final-link numerator.' if composite else ''),
            direct_historical_execution=False)
        rows.append(row)
    with (ROOT/'08_05_out_of_tree_modules.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} external module verdicts and per-module engineering reasons')

if __name__=='__main__':
    main()
