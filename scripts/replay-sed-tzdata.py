#!/usr/bin/env python3
"""Rebuild published sed or tzdata targets and compare BFD and LLD links."""
import argparse
import gzip
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

BUILD = '/home/abuild/rpmbuild/BUILD'
read_runtime = run_path(str(Path(__file__).with_name('replay-base-link-candidate.py')))['read_runtime']


def extract_rpm(rpm, dest):
    dest.mkdir(parents=True)
    with subprocess.Popen(['rpm2cpio', rpm.resolve()], stdout=subprocess.PIPE) as pipe:
        subprocess.run(['cpio', '-id', '--quiet'], cwd=dest, stdin=pipe.stdout, check=True)
        if pipe.wait():
            raise ValueError(f'Could not extract {rpm}')


def shell_line(archive, regex):
    line, = dict.fromkeys(re.findall(r'^\[.*?\]\s+\+ (' + regex + r')$', archive, re.M))
    return line


def with_jobs(line, *args):
    argv = shlex.split(line)
    return shlex.join([re.sub(r'^-j[0-9]+$', '-j2', arg) for arg in argv] + list(args))


def sed_build(folder, rpm_files, archive, training_linker):
    spec = (rpm_files / 'sed.spec').read_text()
    for patch in re.findall(r'^Patch\d+:\s+(\S+)', spec, re.M):
        subprocess.run(['patch', '--no-backup-if-mismatch', '-p1', '-i', rpm_files / patch],
                       cwd=folder, check=True)
    config_refresh = re.findall(r'^\[.*?\]\s+\+ (install -m 755 /usr/lib/rpm/config\.(?:guess|sub) .*?)$', archive, re.M)
    cflags = shell_line(archive, r"export 'CFLAGS=.*-fPIC'")
    ldflags = shell_line(archive, r"export 'LDFLAGS=.*-pie'")
    compiler = shell_line(archive, r'export CC=\S+ CXX=\S+')
    configure = shell_line(archive, r'\./configure .*')
    train = shell_line(archive, r"/bin/make -j\d+ 'CFLAGS=.*-fprofile-generate'")
    feedback = shell_line(archive, r"/bin/make -j\d+ 'CFLAGS=.*-fprofile-use=[^']+'")
    profile_env = shell_line(archive, r'export LLVM_PROFILE_FILE=.*')
    return [*config_refresh, 'export AR=llvm-ar RANLIB=llvm-ranlib', cflags, ldflags, compiler,
            configure, with_jobs(train, f'LDFLAGS= -pie -fuse-ld={training_linker}'),
            profile_env, '/bin/make -j2 check', 'profile_count=$(find . -maxdepth 1 -name "*.profraw" | wc -l)',
            'printf "Training raw profiles: %s\\n" "$profile_count"',
            'llvm-profdata merge -output="$PWD/sed.profdata" ./*.profraw',
            'sha256sum sed.profdata', '/bin/make clean', with_jobs(feedback), 'cd sed']


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(args):
    args.work.mkdir(parents=True)
    args.output.mkdir(parents=True, exist_ok=True)
    sources = args.work / 'sources'
    extract_rpm(args.srpm, sources)
    with gzip.open(args.build_log, 'rt') as stream:
        archive = stream.read()

    root = args.root.resolve()
    resource_mount = []
    archive_name, = sources.glob('*.tar.*')
    if args.package == 'sed':
        folder = args.work / 'sed-4.1c'
        subprocess.run(['tar', 'xf', archive_name, '-C', args.work], check=True)
        lines = sed_build(folder, sources, archive, args.training_linker)
        targets = {'sed': '/usr/bin/sed'}
        # Toybox's saved roots lack compiler-rt, required by sed's PGO training pass.
        extract_rpm(args.compiler_rt, args.work / 'compiler-rt')
        resource_dir, = (args.work / 'compiler-rt' / 'usr').glob('lib*/clang/22')
        resource = '/' + str(resource_dir.relative_to(args.work / 'compiler-rt'))
        shutil.copytree(root / resource.lstrip('/'), resource_dir, dirs_exist_ok=True, symlinks=True)
        resource_mount = ['--ro-bind', str(resource_dir), resource]
    else:
        folder = args.work / 'tzdata-2026d'
        folder.mkdir()
        subprocess.run(['tar', 'xf', archive_name, '-C', folder], check=True)
        make = shell_line(archive, r'/bin/make -j\d+ CC=.*TZDIR=/usr/share/zoneinfo .*')
        lines = ['export AR=llvm-ar RANLIB=llvm-ranlib', with_jobs(make, 'zdump', 'zic')]
        targets = {'zdump': '/usr/sbin/zdump', 'zic': '/usr/sbin/zic'}

    lines[:0] = ['#!/bin/bash', 'set -eux', 'umask 022']
    link_lines = {}
    for target in targets:
        commands = re.findall(r'^\[.*?\]\s+(\S+clang(?: .*?)? -o ' + target + r'\s+.*)$', archive, re.M)
        link_lines[target] = commands[-1].strip()
    for variant, linker in (('bfd', 'bfd'), ('lld', 'lld')):
        lines.append(f'mkdir {variant}')
        for target, link in link_lines.items():
            driver, rest = link.split(' ', 1)
            lines.extend([f'{driver} -fuse-ld={linker} -Wl,-v {rest}', f'mv {target} {variant}/',
                          f'(cd {variant} && eu-strip --remove-comment -f {target}.debug {target})'])
    recipe = folder / 'replay.sh'
    recipe.write_text('\n'.join(lines) + '\n')
    (args.output / 'replay.sh').write_bytes(recipe.read_bytes())
    cpus = ','.join(map(str, sorted(os.sched_getaffinity(0))[:2]))
    argv = ['taskset', '-c', cpus, 'bwrap', '--unshare-all', '--new-session', '--die-with-parent',
            '--clearenv', '--ro-bind', str(root), '/', '--dev', '/dev', '--proc', '/proc',
            '--tmpfs', '/tmp', '--bind', str(args.work.resolve()), BUILD, *resource_mount,
            '--chdir', f'{BUILD}/{folder.name}', '--setenv', 'PATH', '/usr/bin:/usr/sbin:/bin:/sbin',
            '--setenv', 'LC_ALL', 'C', 'bash', './replay.sh']
    with (args.output / 'build.log').open('w') as out:
        print(shlex.join(argv), file=out, flush=True)
        subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, check=True)
    install = args.work / 'rpm'
    extract_rpm(args.rpm, install)
    binaries = folder / 'sed' if args.package == 'sed' else folder
    result = {name: {'image': read_runtime(args.image_root / path.lstrip('/')),
                     'rpm': read_runtime(install / path.lstrip('/')),
                     'bfd': read_runtime(binaries / 'bfd' / name),
                     'lld': read_runtime(binaries / 'lld' / name)}
              for name, path in targets.items()}
    report = {'source_rpm': args.srpm.name, 'source_rpm_sha256': hash_file(args.srpm),
              'runtime_rpm': args.rpm.name, 'runtime_rpm_sha256': hash_file(args.rpm),
              'build_log_sha256': hash_file(args.build_log), 'targets': result}
    if args.package == 'sed':
        report.update(compiler_rt=args.compiler_rt.name, compiler_rt_sha256=hash_file(args.compiler_rt),
                      training_linker=args.training_linker, profile_sha256=hash_file(folder / 'sed.profdata'))
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', choices=('sed', 'tzdata'))
    for item in ('root', 'srpm', 'rpm', 'build-log', 'image-root', 'work', 'output'):
        parser.add_argument('--' + item, type=Path, required=True)
    parser.add_argument('--compiler-rt', type=Path)
    parser.add_argument('--training-linker', choices=('bfd', 'lld'), default='bfd')
    args = parser.parse_args()
    if args.package == 'sed' and args.compiler_rt is None:
        parser.error('sed requires --compiler-rt')
    replay(args)
