#!/usr/bin/env python3
"""Replay the historical libbz2 link and record bfd/LLD controls."""
import argparse
import gzip
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

BUILD = '/home/abuild/rpmbuild/BUILD/bzip2-1.0.8'


def command_log(path, folder):
    with gzip.open(path, 'rt', errors='replace') as log:
        commands = [re.sub(r'^\[.*?\]\s*', '', line).strip() for line in log]
    objects = ['blocksort', 'huffman', 'crctable', 'randtable', 'compress', 'decompress', 'bzlib']
    compiles = [next(line for line in commands if 'clang ' in line and
                     line.endswith(f' -c {obj}.c')) for obj in objects]
    link = [line for line in commands if 'clang ' in line and ' -o libbz2.so.1.0.8 ' in line][-1]
    driver, tail = link.split(' ', 1)
    lines = ['#!/bin/bash', 'set -eux', *compiles]
    for variant, flags in (('default', ''), ('bfd', '-fuse-ld=bfd'), ('lld', '-fuse-ld=lld')):
        lines.extend([f'mkdir -p {variant}', f'{driver} {flags} -Wl,-v {tail}',
                      f'mv libbz2.so.1.0.8 {variant}/',
                      f'cp {variant}/libbz2.so.1.0.8 {variant}/unstripped.so',
                      f'(cd {variant} && eu-strip --remove-comment -f libbz2.so.1.0.8.debug libbz2.so.1.0.8)'])
    (folder / 'replay.sh').write_text('\n'.join(lines) + '\n')


def read_runtime(path):
    binary = path.read_bytes()
    output = subprocess.check_output(['readelf', '-SW', path], text=True)
    offset, size = [int(match, 16) for match in re.search(
        r'\.gnu_debuglink\s+PROGBITS\s+\w+\s+(\w+)\s+(\w+)', output).groups()]
    section = binary[offset:offset + size]
    if size < 8 or b'\0' not in section or offset + size > len(binary):
        raise ValueError('Invalid .gnu_debuglink')
    return {
        'sha256': hashlib.sha256(binary).hexdigest(),
        'debug_crc_le_bytes': section[-4:].hex(),
        'sha256_without_debug_crc': hashlib.sha256(
            binary[:offset + size - 4] + b'\0' * 4 + binary[offset + size:]).hexdigest(),
    }


def replay(args):
    args.work.mkdir(parents=True, exist_ok=False)
    rpm_files = args.work / 'rpm-files'
    rpm_files.mkdir()
    with subprocess.Popen(['rpm2cpio', args.srpm.resolve()], stdout=subprocess.PIPE) as payload:
        subprocess.run(['cpio', '-id', '--quiet'], stdin=payload.stdout, cwd=rpm_files, check=True)
        if payload.wait():
            raise ValueError('SRPM extraction failed')
    subprocess.run(['tar', 'xf', rpm_files / 'bzip2-1.0.8.tar.gz', '-C', args.work], check=True)
    folder = args.work / 'bzip2-1.0.8'
    for patch in ('0001-Fixed-missed-compilation-flags-and-tests-library-pat.patch',
                  '0002-Add-PIE-security-build-option.patch', 'fix_link_makefile.patch'):
        subprocess.run(['patch', '-p1', '-i', rpm_files.resolve() / patch], cwd=folder, check=True)
    command_log(args.build_log, folder)
    args.output.mkdir(parents=True, exist_ok=True)
    cpus = ','.join(str(cpu) for cpu in sorted(os.sched_getaffinity(0))[:2])
    argv = ['taskset', '-c', cpus, 'bwrap', '--unshare-all', '--new-session', '--die-with-parent',
            '--clearenv', '--ro-bind', str(args.root.resolve()), '/', '--dev', '/dev', '--proc',
            '/proc', '--tmpfs', '/tmp', '--bind', str(args.work.resolve()), str(Path(BUILD).parent), '--chdir', BUILD,
            '--setenv', 'PATH', '/usr/bin:/usr/sbin:/bin:/sbin', '--setenv', 'LC_ALL', 'C',
            'bash', './replay.sh']
    with (args.output / 'build.log').open('w') as out:
        print(shlex.join(argv), file=out, flush=True)
        subprocess.run(argv, stdout=out, stderr=subprocess.STDOUT, check=True)
    (args.output / 'replay.sh').write_bytes((folder / 'replay.sh').read_bytes())
    results = {variant: read_runtime(folder / variant / 'libbz2.so.1.0.8')
               for variant in ('default', 'bfd', 'lld')}
    results['image'] = read_runtime(args.elf)
    results['srpm_sha256'] = hashlib.sha256(args.srpm.read_bytes()).hexdigest()
    results['strip_comparison'] = 'Ignoring only the 4-byte CRC at the end of .gnu_debuglink'
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ('root', 'srpm', 'build-log', 'elf', 'work', 'output'):
        parser.add_argument('--' + item, type=Path, required=True)
    replay(parser.parse_args())
