#!/usr/bin/env python3
"""Cross-check published Phase 11 RPMs, SDK configuration and successful job logs."""
import csv
import difflib
import json
from pathlib import Path
import re

from qb_repo import OLD, PROJECTS, REPO, ROOT, TARGET_RELEASE, URL, digest, dump, line_find, relative

IDENTITY = ROOT / '11A_QB_IDENTITY.json'
EXTERNAL = 'platform/kernel/linux-tizen-modules'
IMPLEMENTATION = 'platform/kernel/linux-tizen-modules-source'
KERNEL = 'platform/kernel/linux-rpi'
SUBMISSION = ROOT.parent / 'phase10_kdbus_sandbox/KDBUS_LD_FIX_SUBMISSION_SUMMARY.json'
SDK_SUFFIX = 'boot/kernel/devel/kernel-devel-arm-rpi4'
CONFIG_KEYS = ('CC_VERSION_TEXT', 'CC_IS_CLANG', 'CLANG_VERSION', 'LD_IS_LLD', 'LLD_VERSION',
               'LOCALVERSION', 'ARM', 'ARM64', 'PREEMPT_RT', 'MODVERSIONS', 'LTO_NONE',
               'LTO_CLANG', 'CFI_CLANG', 'DEBUG_INFO_BTF_MODULES', 'MODULE_SIG')
TOOL_NAMES = ('clang', 'llvm', 'clang-accel-x86_64-armv7l', 'qemu-accel-x86_64-armv7l',
              'binutils', 'make', 'gcc', 'glibc', 'rpm', 'rpm-build')
TIME_PREFIX = r'^\[\s*\d+s\]\s*'
BUILD_PARAMS = re.compile(TIME_PREFIX + r"(?:\+ (?:export (?:LLVM=|CC=|AR=|'MAKEFLAGS|BUILD_kdbus=|THREAD_GROUP_CPUTIME_SUPPORT=)|(?:CFLAGS|CXXFLAGS|LDFLAGS)=|find kernel -name Makefile|make -C kernel .*KERNELDIR=/boot/kernel/devel/kernel-devel-arm-rpi4(?:\s|$))|make -C /boot/kernel/devel/kernel-devel-arm-rpi4 .* modules\s*$)")


def file_identity(path):
    return {'path': relative(path), 'sha256': digest(path), 'bytes': path.stat().st_size}


def config_values(text):
    values = dict(re.findall(r'^CONFIG_(\w+)=(.*)$', text, re.M))
    values.update(dict.fromkeys(re.findall(r'^# CONFIG_(\w+) is not set$', text, re.M), 'n'))
    return {name: values.get(name) for name in CONFIG_KEYS}


def sdk_identity(sdk):
    config = sdk / '.config'
    compile_header = sdk / 'include/generated/compile.h'
    uts_header = sdk / 'include/generated/utsrelease.h'
    compiler_line = line_find(compile_header, r'^#define LINUX_COMPILER\b')[0]
    clang, lld = re.search(r'clang version ([\d.]+), LLD ([\d.]+)', compiler_line['raw']).groups()
    release = re.search(r'UTS_RELEASE\s+"([^\"]+)"', uts_header.read_text()).group(1)
    return {
        'kernel_release': release,
        'clang_version': clang,
        'lld_version': lld,
        'config': file_identity(config),
        'config_keys': config_values(config.read_text()),
        'utsrelease_header': file_identity(uts_header),
        'compile_header': file_identity(compile_header),
        'compiler_line': compiler_line,
        'compile_host_line': line_find(compile_header, r'^#define LINUX_COMPILE_HOST\b')[0],
    }


def build_job(path):
    tool_lines = line_find(path, r'\bkeeping (?:' + '|'.join(TOOL_NAMES) + r')-\d')
    tools = {}
    for item in tool_lines:
        pkg, evr = re.search(r'\bkeeping ([a-z0-9_+-]+?)-(\d[^\s]+)', item['raw']).groups()
        tools[pkg] = {'version_release': evr, **item}
    started = line_find(path, r'\bstarted "build .*\.spec" at ')
    finished = line_find(path, r'\bfinished "build .*\.spec" at ')
    build_root = line_find(path, r'\bUsing BUILD_ROOT=')
    wrote = line_find(path, r'\bWrote:\s+/[^\s]+\.rpm\s*$')
    return {**file_identity(path), 'root': build_root[0], 'started': started[0],
            'finished': finished[0], 'packages_in_log': tools, 'wrote': wrote}


def parameter_lines(path):
    lines = path.read_text(errors='replace').splitlines()
    result = []
    for number, line in enumerate(lines, start=1):
        if re.search(r'\bCC \[M\] ', line):
            break
        if BUILD_PARAMS.search(line):
            result.append({'line': number, 'raw': line, 'shell_text': re.sub(TIME_PREFIX, '', line)})
    return result


def job_for_package(row, jobs):
    project = (row['source_revision'] or '').partition('#')[0]
    if project not in jobs or row['arch'] not in {'armv7l', 'src'}:
        return {'build_log_association': 'OUTSIDE_TARGET_JOB'}
    job = jobs[project]
    wrote = next((line for line in job['wrote'] if line['raw'].endswith('/' + row['filename'])), None)
    if not wrote:
        return {'build_log_association': 'TARGET_JOB_NO_MATCHING_WROTE_RECORD'}
    basis = 'PINNED_JOB_WROTE_FILENAME_AND_PRIMARY_VCS'
    if row['arch'] == 'src':
        basis = 'ARMV7L_JOB_WROTE_SAME_SRPM_FILENAME_AND_PRIMARY_VCS_NO_JOB_DIGEST'
    return {
        'build_log_association': basis, 'build_log_path': job['path'],
        'build_log_sha256': job['sha256'], 'job_wrote_line': wrote['line'], 'job_wrote_raw': wrote['raw'],
        'build_root': job['root']['raw'].partition('BUILD_ROOT=')[2],
        'job_started_raw': job['started']['raw'], 'job_finished_raw': job['finished']['raw'],
    }


def base_packages(data, new_job):
    path = ROOT / 'evidence/build/base/matched-metadata.json'
    if not path.exists():
        return []
    packages = json.loads(path.read_text())
    if packages['primary_checksum_status'] != 'PASS':
        raise ValueError('Base Primary metadata failed verification')
    base = data['new']['base_id']
    base_url = f'https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/{base}/repos/standard/packages/'
    rows = []
    for rpm in packages['packages']:
        name = rpm['name']
        ver = rpm['version']
        installed = new_job['packages_in_log'][name]
        if installed['version_release'] != f"{ver['ver']}-{ver['rel']}":
            raise ValueError(f'Wrong base RPM metadata for {name}')
        local = ROOT / 'evidence/build/base/rpms' / Path(rpm['href']).name
        sha = digest(local) if local.exists() else None
        if sha and sha != rpm['sha256']:
            raise ValueError(f'Base RPM checksum mismatch for {local.name}')
        rows.append({
            'role': 'BUILD_DEP_TOOLCHAIN', 'area': 'base/packages', 'name': name, 'epoch': ver['epoch'],
            'version': ver['ver'], 'release': ver['rel'], 'arch': rpm['arch'],
            'nevra': f"{name}-{ver['epoch']}:{ver['ver']}-{ver['rel']}.{rpm['arch']}",
            'filename': Path(rpm['href']).name, 'source_rpm': rpm['source_rpm'], 'source_revision': ver.get('vcs'),
            'download_url': base_url + rpm['href'], 'published_bytes': int(rpm['size']),
            'checksum_algorithm': 'sha256', 'published_checksum': rpm['sha256'], 'local_sha256': sha,
            'repository_checksum_verification': 'PASS' if sha else 'METADATA_ONLY',
            'artifact_path': relative(local) if sha else None,
            'build_log_association': 'PINNED_JOB_KEEPING_EXACT_VERSION_RELEASE',
            'build_log_path': new_job['path'], 'build_log_sha256': new_job['sha256'],
            'build_dependency_line': installed['line'], 'build_dependency_raw': installed['raw'],
        })
    return rows


def write_inventory(rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (ROOT / '11A_RPM_INVENTORY.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def main():
    data = json.loads(IDENTITY.read_text())
    old_sdk = OLD / 'evidence/build/devel' / SDK_SUFFIX
    new_sdk = REPO / 'sdk' / SDK_SUFFIX
    submission = json.loads(SUBMISSION.read_text())
    old = sdk_identity(old_sdk)
    new = sdk_identity(new_sdk)
    if old['kernel_release'] != TARGET_RELEASE or new['kernel_release'] != TARGET_RELEASE:
        raise ValueError('ARMv7l non-RT SDK release mismatch')
    config_diff = list(difflib.unified_diff((old_sdk / '.config').read_text().splitlines(),
                        (new_sdk / '.config').read_text().splitlines(), fromfile='old/.config', tofile='new/.config', lineterm=''))
    tool_rows = {}
    jobs = {project: build_job(ROOT / 'evidence/build' / f'{stem}.out') for project, stem in PROJECTS.items()}
    old_job_path = OLD / 'evidence/build' / f'{PROJECTS[EXTERNAL]}.out'
    new_job_path = ROOT / 'evidence/build' / f'{PROJECTS[EXTERNAL]}.out'
    old_job = build_job(old_job_path)
    ext_job = jobs[EXTERNAL]
    for name in TOOL_NAMES:
        earlier = old_job['packages_in_log'].get(name)
        later = ext_job['packages_in_log'].get(name)
        tool_rows[name] = {'old': earlier, 'new': later, 'changed': bool(earlier and later and earlier['version_release'] != later['version_release'])}
    old_params = parameter_lines(old_job_path)
    new_params = parameter_lines(new_job_path)
    params_equal = [r['shell_text'] for r in old_params] == [r['shell_text'] for r in new_params]
    changed_projects = {p: {'old': data['old']['project_revisions'][p], 'new': data['new']['project_revisions'][p]}
                        for p in PROJECTS if data['old']['project_revisions'][p] != data['new']['project_revisions'][p]}
    patch_matches = (submission['repository'] == IMPLEMENTATION and
                     data['new']['project_revisions'][IMPLEMENTATION] == submission['new_commit_sha'] and
                     data['old']['project_revisions'][IMPLEMENTATION] == submission['historical_image_source_commit'])
    for row in data['rpm_rows']:
        row.update(job_for_package(row, jobs))
        project, _, revision = (row['source_revision'] or '').partition('#')
        expected_revision = data['new']['project_revisions'].get(project)
        row['vcs_matches_manifest'] = revision == expected_revision if expected_revision else None
        if row['vcs_matches_manifest'] is False:
            raise ValueError(f"RPM VCS differs from the snapshot manifest: {row['filename']}")
    module = next(row for row in data['rpm_rows'] if row['role'] == 'OUT_OF_TREE_MODULES')
    old_module_path = OLD / 'evidence/repository/rpms' / module['filename']
    old_module = file_identity(old_module_path)
    wrote_earlier = next((r for r in old_job['wrote'] if r['raw'].endswith('/' + module['filename'])), None)
    rebuilt = bool(module['repository_checksum_verification'] == 'PASS' and
                   module['published_checksum'] != old_module['sha256'] == module['old_metadata_checksum'] and
                   module.get('job_wrote_line') and wrote_earlier and ext_job['started']['raw'] != old_job['started']['raw'])
    image = next(row for row in data['rpm_rows'] if row['role'] == 'KERNEL_IMAGE')
    debuginfo = next(row for row in data['rpm_rows'] if row['role'] == 'KERNEL_DEBUGINFO')
    data.update({
        'sdk_identity': {'old': old, 'new': new,
                         'new_kernel_release_file': file_identity(new_sdk / 'include/config/kernel.release'),
                         'new_module_symvers': file_identity(new_sdk / 'Module.symvers')},
        'kernel_release': TARGET_RELEASE,
        'clang_version': {'old': old['clang_version'], 'new': new['clang_version']},
        'lld_version': {'old': old['lld_version'], 'new': new['lld_version']},
        'config_comparison': {'byte_identical': old['config']['sha256'] == new['config']['sha256'],
                              'unified_diff': config_diff, 'scope': 'Packaged ARMv7l non-RT development SDK'},
        'toolchain_job_package_comparison': tool_rows,
        'visible_build_parameter_comparison': {'equal_in_selected_shell_trace': params_equal,
                                               'old': old_params, 'new': new_params},
        'manifest_revision_changes': changed_projects,
        'new_manifest_matches_phase10_fix': patch_matches,
        'phase10_submission': {**file_identity(SUBMISSION), 'sandbox_ref': submission['branch_ref'],
                               'commit': submission['new_commit_sha'], 'change_id': submission['gerrit_change_id']},
        'successful_job_details': jobs,
        'target_wrapper_rebuilt': rebuilt,
        'target_wrapper_rebuild_evidence': {'old_sha256': module['old_metadata_checksum'],
                                           'old_local_rpm': old_module,
                                           'new_sha256': module['published_checksum'], 'old_wrote': wrote_earlier,
                                           'old_job': old_job, 'new_wrote_line': module.get('job_wrote_line')},
        'toolchain_rpm_rows': base_packages(data, ext_job),
        'confounders': ['Base snapshot ID differs.', 'Installed compiler, linker, accelerator, binutils and make RPM revisions differ.',
                        'Builder hostname, scratch build root and timestamps differ.',
                        'Quiet build logs do not capture all effective per-object options or the selected historical executable.'],
        'evidence_gaps': [f'{image["filename"]} and {debuginfo["filename"]} recorded in published metadata without payload acquisition.',
                          'No exact target kdbus.ko.debug or intermediate kdbus.o/.kdbus.o.cmd in published filelists.',
                          'No detached repomd.xml.asc at the three published repository metadata paths.',
                          'Target RPM header Build Time is zero. Successful job times are separately reported.'],
    })
    if not rebuilt or not patch_matches or not data['toolchain_rpm_rows']:
        raise ValueError('Missing expected Phase 11A identity evidence')
    dump(IDENTITY, data)
    write_inventory(data['rpm_rows'] + data['toolchain_rpm_rows'])
    print(f"Preflight {data['preflight_status']}; same release {TARGET_RELEASE}; config byte-identical {data['config_comparison']['byte_identical']}; external rebuilt {rebuilt}.")
    print(f"Compared {len(tool_rows)} tool packages; selected build parameters match {params_equal}.")


if __name__ == '__main__':
    main()
