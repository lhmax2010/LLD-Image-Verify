#!/usr/bin/env python3
"""Summarize verified raw configuration and quiet build provenance for Phase 4."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path('evidence/build')
DEVEL = BUILD / 'devel/boot/kernel/devel/kernel-devel-arm-rpi4'
REPO = Path('evidence/repository/rpms')
EXTRACTION = Path('evidence/kernel_binary/analysis/arm-rpi4-linux-kernel-6.12.80-0.armv7l/boot/zImage-extract-ikconfig')
REVISION = '42aeefac58edeb081aff440f0b60be71cbe49755'

def read_json(path):
    return json.loads((ROOT / path).read_text())

def input_stats(path):
    with (ROOT / path).open('rb') as f:
        sha256 = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': sha256, 'bytes': (ROOT / path).stat().st_size}

def main():
    log_index = BUILD / 'kernel-build-log-events.json'
    module_index = BUILD / 'module-final-commands.json'
    entries = read_json(log_index)
    modules = read_json(module_index)
    config = read_json(BUILD / 'packaged-config-values.json')
    embed_command = read_json(EXTRACTION.with_suffix('.cmd.json'))
    embed_result = (ROOT / EXTRACTION.with_suffix('.err')).read_text().strip()
    runtime_banner_path = Path('evidence/runtime/banner.out')
    runtime_banner = (ROOT / runtime_banner_path).read_text()
    expected = [
        '6.12.80-arm-rpi4-v7l', 'abuild@qb-build-host-01',
        'clang version 22.1.8, LLD 22.1.8', 'Fri Nov 20 09:22:45 UTC 2026',
    ]
    if not all(value in runtime_banner for value in expected):
        raise ValueError('Independent runtime banner does not match expected Phase 4 identity fields')
    src_and_devel = [
        REPO / 'arm-rpi4-linux-kernel-devel-6.12.80-0.armv7l.rpm',
        REPO / 'rpi4-linux-kernel-6.12.80-0.src.rpm',
        REPO / 'linux-tizen-modules-11.0.0-0.src.rpm',
    ]
    flags = config['actual_config']['keys']
    required = {'CONFIG_CC_IS_CLANG': 'y', 'CONFIG_CLANG_VERSION': '220108', 'CONFIG_LD_IS_LLD': 'y', 'CONFIG_LLD_VERSION': '220108'}
    if any(flags[key]['value'] != value for key, value in required.items()):
        raise ValueError('Packaged configuration differs from the toolchain values cited in the Phase 4 report')
    report = {
        'snapshot': 'tizen-unified-toolchain_20261120.082536',
        'target': 'ARMv7l RPi4 non-RT, 6.12.80-arm-rpi4-v7l',
        'source_revision': REVISION,
        'status': 'CONDITIONAL_PASS',
        'config_status': 'PASS',
        'configured_compiler': {'name': 'Clang', 'version': '22.1.8'},
        'configured_linker': {'name': 'LLD', 'version': '22.1.8', 'kbuild_default_command_name': 'ld.lld'},
        'configuration': config,
        'config_source_availability': {
            'runtime_proc_config': {'status': 'absent', 'evidence': 'evidence/runtime/files.out'},
            'runtime_boot': {'status': 'absent', 'evidence': 'evidence/runtime/files.out'},
            'image_modules_debug_rpm': {'status': 'no_generated_config_member', 'evidence': 'evidence/build/rpm-config-member-index.out'},
            'devel_rpm': {'status': 'observed_generated_config', 'evidence': 'evidence/build/devel-build-filelist.out'},
            'source_rpm': {'status': 'build_intent_only', 'evidence': 'evidence/build/source/linux-rpi.spec'},
            'embedded': {
                'status': 'no_config_found' if embed_command['exit_status'] == 1 and embed_result == 'extract-ikconfig: Cannot find kernel config.' else 'see_command',
                'exit_status': embed_command['exit_status'],
                'raw_stderr': embed_result,
                'evidence': str(EXTRACTION.with_suffix('.err')),
                'command_record': str(EXTRACTION.with_suffix('.cmd.json')),
            },
            'matching_gbs_local': {'status': 'not_found', 'evidence': 'evidence/build/builder-root-local.err'},
        },
        'input_files': [
            input_stats(path) for path in (
                *src_and_devel, BUILD / 'linux-rpi-armv7l.out',
                BUILD / 'linux-tizen-modules-armv7l.out', runtime_banner_path,
            )
        ],
        'build_log_index': str(log_index),
        'normal_target_link_steps': {
            key: entries[key] for key in ('quiet_partial_link', 'quiet_final_link', 'quiet_arm_decompressor_link')
        },
        'module_link_steps': {
            'evidence': str(module_index),
            'unique_package_and_payload_path_observations': sum(modules['observations_by_rpm'].values()),
            'observations_by_rpm': modules['observations_by_rpm'],
            'exact_argv_count': len(modules['actual_final_link_commands']),
        },
        'source_intent': {
            'main_spec': 'evidence/build/source/linux-rpi.spec',
            'external_spec': 'evidence/build/external-source/linux-tizen-modules.spec',
            'patched_build_rules': [
                str(DEVEL / path) for path in (
                    'Makefile', 'scripts/Makefile.vmlinux', 'scripts/link-vmlinux.sh',
                    'scripts/Makefile.modfinal', 'scripts/Makefile.vmlinux_o', 'scripts/Makefile.lib',
                    'scripts/Kconfig.include', 'arch/arm/boot/compressed/Makefile',
                )
            ],
        },
        'historical_builder_dependencies': {
            'base_snapshot': 'tizen-base-toolchain_20261119.042539',
            'checked_packages': 'evidence/build/historical-base-package-checks.out',
            'llvm_rpm_ld_lld': {
                'declared_path': '/usr/bin/ld.lld',
                'symlink_target': 'lld',
                'evidence': 'evidence/build/historical-base-llvm-payload.out',
            },
            'accelerator_package_ld_lld': {
                'declared_path': '/emul/usr/bin/ld.lld',
                'evidence': 'evidence/build/historical-base-accelerator.out',
                'basis': 'Repository primary metadata',
            },
        },
        'debug_package_stage': {
            'evidence': 'evidence/build/debuginfo-id-staging.out',
            'original_build_find_debuginfo_recipe': 'evidence/build/historical-base/rpm-build/usr/lib/rpm/find-debuginfo.sh',
            'debugedit_option_identification': 'evidence/build/historical-base-debugedit-text.out',
            'effect': 'The historical find-debuginfo implementation passes -i and the seed to debugedit to recalculate the Build ID note.',
        },
        'local_search': {
            'bounded_search_command': 'evidence/build/bounded-local-paths.cmd.json',
            'bounded_search_output': 'evidence/build/bounded-local-paths.out',
            'gbs_build_folders': 'evidence/build/selected-gbs-build-dirs.out',
            'explicit_rejection': {
                'evidence': 'evidence/build/rejected-local-gbs-candidate.out',
                'kernel_release': '6.12.80-arm-rpi4-v7l',
                'banner_builder': 'local-review-host',
                'build_timestamp_utc': '2026-08-26T09:44:20Z',
                'gnu_build_id': '38a689c0c4913f5e22c3c2366d25de2526016478',
                'reason': 'Builder, timestamp and GNU Build ID differ from the target November build.',
            },
        },
        'same_build_actual_vmlinux_final_link_command': None,
        'same_build_actual_linker_absolute_path': None,
        'same_build_kbuild_cmd_files': [],
        'evidence_gaps': [
            'The published logs record quiet LD target operations and do not reveal executed linker argv.',
            'RPM packaging excluded *.cmd files and the remote historical build directory is unavailable locally.',
            'No retained original build environment path resolution proves the ld.lld executable absolute path.',
        ],
    }
    (ROOT / '04_build_evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Configuration and build commands summarized for Phase 4.')

if __name__ == '__main__':
    main()
