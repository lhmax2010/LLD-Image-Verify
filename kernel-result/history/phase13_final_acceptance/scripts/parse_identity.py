#!/usr/bin/env python3
"""Recompute the read-only SDB identity and compare it to the pinned new QB."""
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'kernel_lld_verification_20261125'
sys.path.insert(0,str(PRIOR/'scripts'))
from parse_runtime import read_notes, SHA

OUT=ROOT/'evidence/runtime'
serial='private-address-02:26101'
wanted='tizen-unified-toolchain_20261125.130358'
summary=json.loads((PRIOR/'KDBUS_LLD_FIX_QB_VERIFICATION_SUMMARY.json').read_text())
abi=json.loads((PRIOR/'11F_MODULE_ABI_SUMMARY.json').read_text())
kdbus=abi['modules']['extra/kdbus/kdbus.ko']
record=json.loads((OUT/'device-identity.cmd.json').read_text())
lines=(OUT/'device-identity.out').read_text().splitlines()
fields={}
current=None
for line in lines:
    if re.fullmatch(r'\[[A-Z_]+\]',line):
        current=line[1:-1]
        fields[current]=[]
    elif current:
        fields[current].append(line)
if record['exit_status'] != 0 or 'END' not in fields:
    result={'device_identity':'UNVERIFIED','runtime_regression':'PENDING_DEVICE_IDENTITY'}
else:
    name,release,arch=fields['UNAME']
    build=fields['IMAGE_BUILD_ID'][0].split('=',1)[1].strip('"')
    model=fields['DEVICE_MODEL'][0]
    newest=build.startswith(wanted+'_')
    platform=arch=='armv7l' and model.startswith('Raspberry Pi 4') and release==summary['NEW_QB_KERNEL_RELEASE']
    expected_sha=summary['kdbus']['new_sha256']
    actual=[{'sha256':m[1],'path':m[2]} for line in fields['KDBUS_FILES'] if (m:=SHA.fullmatch(line))]
    matching_module=any(m['sha256']==expected_sha for m in actual)
    kernel=read_notes(fields['KERNEL_NOTES'])
    loaded=read_notes(fields['KDBUS_NOTE'])
    identity='MATCHED_NEW_QB' if newest and platform and matching_module else (
        'MISMATCH_IMAGE_AND_PLATFORM' if not newest and not platform else (
            'MISMATCH_PLATFORM' if not platform else ('MISMATCH_IMAGE' if not newest else 'MODULE_IDENTITY_UNCONFIRMED')
        ))
    pending='PENDING_NEW_IMAGE_DEPLOYMENT' if not newest or not platform else 'PENDING_RUNTIME_VERIFICATION'
    result={'device_identity':identity,'runtime_regression':pending,
        'observed':{'uname':name,'image_build_id':build,'release':release,'arch':arch,'model':model,
                    'proc_version':fields['PROC_VERSION'][0],'boot_banner':fields['BOOT_BANNER'][0] if fields['BOOT_BANNER'] else None,
                    'kernel_gnu_note':kernel,'kdbus_installed':actual,
                    'kdbus_loaded_line':fields['KDBUS_LOADED'],'kdbus_loaded_gnu_note':loaded},
        'target':{'qb':wanted,'release':summary['NEW_QB_KERNEL_RELEASE'],'platform':'Raspberry Pi 4 ARMv7l non-RT',
                  'kdbus_released_sha256':expected_sha,'kdbus_released_build_ids':kdbus['new']['build_ids']},
        'checks':{'image_build_id_match':newest,'platform_release_match':platform,'kdbus_sha256_match':matching_module},
        'd1_kernel_boot':'NOT_RUN_TARGET_IDENTITY_MISMATCH' if identity!='MATCHED_NEW_QB' else 'PENDING',
        'd2_module_inventory':'NOT_RUN_TARGET_IDENTITY_MISMATCH' if identity!='MATCHED_NEW_QB' else 'PENDING',
        'd3_module_runtime':'NOT_RUN_TARGET_IDENTITY_MISMATCH' if identity!='MATCHED_NEW_QB' else 'PENDING',
        'd4_kernel_errors':'NOT_RUN_TARGET_IDENTITY_MISMATCH' if identity!='MATCHED_NEW_QB' else 'PENDING',
        'd5_functional_regression':'NOT_RUN_TARGET_IDENTITY_MISMATCH' if identity!='MATCHED_NEW_QB' else 'PENDING'}
result.update(serial=serial,identity_read_only=True,device_mutation_performed=False,
              archive_stdout='evidence/runtime/device-identity.out',
              archive_stderr='evidence/runtime/device-identity.err',
              archive_command='evidence/runtime/device-identity.cmd.json')
(OUT/'identity.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(result['device_identity'],result['runtime_regression'])
