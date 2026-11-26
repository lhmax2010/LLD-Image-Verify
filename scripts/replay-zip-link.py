#!/usr/bin/env python3
"""Replay the archived ZIP build with the two historical linker candidates."""
import argparse
import gzip
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

BUILD = '/home/abuild/rpmbuild/BUILD'


def replay(args):
    args.work.mkdir(parents=True, exist_ok=False)
    args.output.mkdir(parents=True, exist_ok=True)
    rpm_files = args.work / 'rpm-files'
    rpm_files.mkdir()
    with subprocess.Popen(['rpm2cpio', args.srpm.resolve()], stdout=subprocess.PIPE) as payload:
        subprocess.run(['cpio', '-id', '--quiet'], stdin=payload.stdout, cwd=rpm_files, check=True)
        if payload.wait():
            raise ValueError('SRPM extraction failed')
    subprocess.run(['tar', 'xf', rpm_files / 'zip-3.0.tar.bz2', '-C', args.work], check=True)
    folder = args.work / 'zip30'
    spec = (rpm_files / 'zip.spec').read_text()
    patches = re.findall(r'^(?:Patch\d+|Source1[01]):\s+([^\s]+\.patch)', spec, re.M)
    for patch in patches:
        subprocess.run(['patch', '--no-backup-if-mismatch', '-p1', '-i', rpm_files.resolve() / patch],
                       cwd=folder, check=True)
    with gzip.open(args.build_log, 'rt') as source:
        archive = source.read()
    make_line = re.search(r'\+ (make -j\d+ -f unix/Makefile generic .* prefix=/usr)', archive).group(1)
    make_command = shlex.split(make_line)
    make_command[1] = '-j2'
    link_commands = {}
    for name in ('zip', 'zipcloak', 'zipnote', 'zipsplit'):
        link_commands[name] = re.search(
            r'^\[.*?\]\s+(\S+clang [^\n]* -o ' + name + r' [^\n]+)$', archive, re.M).group(1)
    lines = ['#!/bin/bash', 'set -eux', shlex.join(make_command)]
    for variant, flag in (('bfd', '-fuse-ld=bfd'), ('lld', '-fuse-ld=lld')):
        lines.append(f'mkdir -p {variant}')
        for name, link in link_commands.items():
            driver, rest = link.split(' ', 1)
            lines += [f'{driver} {flag} -Wl,-v {rest}', f'mv {name} {variant}/',
                      f'(cd {variant} && eu-strip --remove-comment -f {name}.debug {name})']
    script = folder / 'replay.sh'
    script.write_text('\n'.join(lines) + '\n')
    (args.output / 'replay.sh').write_bytes(script.read_bytes())
    cpus = ','.join(str(cpu) for cpu in sorted(os.sched_getaffinity(0))[:2])
    argv = ['taskset', '-c', cpus, 'bwrap', '--unshare-all', '--new-session', '--die-with-parent',
            '--clearenv', '--ro-bind', str(args.root.resolve()), '/', '--dev', '/dev', '--proc',
            '/proc', '--tmpfs', '/tmp', '--bind', str(args.work.resolve()), BUILD,
            '--chdir', f'{BUILD}/zip30', '--setenv', 'PATH', '/usr/bin:/usr/sbin:/bin:/sbin',
            '--setenv', 'LC_ALL', 'C', 'bash', './replay.sh']
    with (args.output / 'build.log').open('w') as out:
        print(shlex.join(argv), file=out, flush=True)
        subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, check=True)
    # Use the same .gnu_debuglink checksum comparison as the libbz2 replay.
    from runpy import run_path
    read_runtime = run_path(str(Path(__file__).with_name('replay-base-link-candidate.py')))['read_runtime']
    results = {name: {which: read_runtime(path) for which, path in (
        ('image', args.image_bin / name), ('bfd', folder / 'bfd' / name),
        ('lld', folder / 'lld' / name))} for name in link_commands}
    results['srpm_sha256'] = hashlib.sha256(args.srpm.read_bytes()).hexdigest()
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ('root', 'srpm', 'build-log', 'image-bin', 'work', 'output'):
        parser.add_argument('--' + item, type=Path, required=True)
    replay(parser.parse_args())
