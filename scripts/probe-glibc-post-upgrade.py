#!/usr/bin/env python3
"""Correlate the original upgrade-tool link log, pinned GCC and image RPM."""
import argparse
import gzip
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path


def sha256(binary):
    return hashlib.sha256(binary).hexdigest()


def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    patterns = (
        r'checking version of .*bin/ld\.\.\.',
        r'\+ .*gcc .* -o glibc_post_upgrade ',
        r'\+ install -m 0700 build/glibc_post_upgrade ',
        r'extracting debug info .*glibc_post_upgrade',
        r'Wrote: .*/RPMS/.*/glibc-[\d.]+-[\d.]+\.(?:aarch64|armv7l)\.rpm',
    )
    opener = gzip.open if args.log.suffix == '.gz' else open
    with opener(args.log, 'rt', errors='replace') as log:
        archive = list(enumerate(log, 1))
    selected = []
    for pattern in patterns:
        match, = [(n, line.strip()) for n, line in archive if re.search(pattern, line)]
        selected.append(match)
    (args.output / 'original-log-excerpt.txt').write_text(
        ''.join(f'{n}: {line}\n' for n, line in selected))
    argv = shlex.split(selected[1][1].partition(' + ')[2])
    box = ['bwrap', '--unshare-all', '--ro-bind', str(args.root.resolve()), '/', '--dev',
           '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--chdir', '/tmp']

    def run(cmd):
        return subprocess.check_output(box + cmd, text=True, stderr=subprocess.STDOUT)

    invocation = run([argv[0], '-###', *argv[1:]])
    ld = run([argv[0], '-print-prog-name=ld']).strip()
    ld_version = run([ld, '--version']).splitlines()[0]
    gcc = run([argv[0], '--version']).splitlines()[0]
    flags = [('/dev/null' if field.endswith('/glibc_post_upgrade.c') else field) for field in argv[1:]]
    direct = run([argv[0], '-x', 'c', '-Wl,--version', *flags])
    (args.output / 'driver.txt').write_text(
        f'{invocation}\n{ld}\n{ld_version}\n{gcc}\n\n{direct}')
    if ld_version not in direct:
        raise ValueError('GCC link probe and reported ld disagree')
    with subprocess.Popen(['rpm2cpio', args.rpm], stdout=subprocess.PIPE) as rpm:
        rpm_elf = subprocess.check_output(['cpio', '-i', '--quiet', '--to-stdout',
                                           './usr/sbin/glibc_post_upgrade'], stdin=rpm.stdout)
        if rpm.wait():
            raise ValueError('RPM extraction failed')
    image_digest = sha256(args.elf.read_bytes())
    rpm_digest = sha256(rpm_elf)
    result = {'image_sha256': image_digest, 'rpm_elf_sha256': rpm_digest,
              'rpm_url': args.rpm_url, 'rpm_sha256': sha256(args.rpm.read_bytes()), 'linker': ld_version}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    if image_digest != rpm_digest:
        raise ValueError('Image and RPM ELF differ')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ('log', 'root', 'rpm', 'elf', 'output'):
        parser.add_argument('--' + item, type=Path, required=True)
    parser.add_argument('--rpm-url', required=True)
    main(parser.parse_args())
