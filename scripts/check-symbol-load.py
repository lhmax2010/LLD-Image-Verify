#!/usr/bin/env python3
"""Resolve representative symbols from exact GCC and LLVM RPM payloads in QEMU."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().with_name('symbol-probe.c')


def run(path, args, check=True):
    argv = [str(a) for a in args]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    path.write_text(json.dumps(argv) + '\n' + result.stdout + result.stderr)
    if check:
        result.check_returncode()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-audit', required=True, type=Path)
    parser.add_argument('--tool-probe', required=True, type=Path)
    parser.add_argument('--contracts', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    home = args.image_audit.resolve() / 'extracted'
    report = []
    for arch, lib, qemu, triple, emulation, interpreter in (
        ('aarch64', 'lib64', 'qemu-arm64-static', 'aarch64-tizen-linux-gnu',
         'aarch64linux', 'ld-linux-aarch64.so.1'),
        ('armv7l', 'lib', 'qemu-arm-static', 'armv7l-tizen-linux-gnueabi',
         'armelf_linux_eabi', 'ld-linux.so.3'),
    ):
        qemu = shutil.which(qemu) or (shutil.which('qemu-aarch64-static') if arch == 'aarch64' else None)
        if not qemu:
            raise ValueError(f'Missing static QEMU for {arch}')
        root = home / f'tizen-headed-{arch}' / 'rootfs'
        tools = args.tool_probe.resolve() / arch / 'tools'
        runner = [qemu, '-L', tools, '-E',
                  f'LD_LIBRARY_PATH={tools / "usr" / lib}:{root / "usr" / lib}']
        tool_bin = tools / 'usr' / 'bin'
        obj = output / f'{arch}.o'
        exe = output / f'{arch}.elf'
        run(output / f'{arch}-compile.txt',
            runner + [tool_bin / 'clang', '--no-default-config', f'--target={triple}',
                      '-fno-stack-protector', '-fPIC', '-c', SOURCE, '-o', obj])
        run(output / f'{arch}-link.txt', runner + [tool_bin / 'ld.lld', '-m', emulation,
            '--dynamic-linker', f'/lib/{interpreter}', '-e', '_start', obj,
            root / 'usr' / lib / 'libc.so.6', '-o', exe])
        for side in ('gcc', 'llvm'):
            rpm_payloads = args.contracts.resolve() / side
            solv = rpm_payloads / f'{arch}-libsolv-libsolv.so.1.elf'
            installer, = rpm_payloads.glob(f'{arch}-app-installers-libapp-installers.so.*.elf')
            sandbox = ['bwrap', '--unshare-all', '--new-session', '--die-with-parent',
                       '--clearenv', '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
                       '--ro-bind', root / 'usr', '/usr', '--ro-bind', root / 'etc', '/etc',
                       '--ro-bind', qemu, '/qemu', '--ro-bind', exe, '/probe',
                       '--ro-bind', solv, '/audit/libsolv.so.1',
                       '--ro-bind', installer, '/audit/libapp-installers.so.1',
                       '--symlink', '/usr/lib', '/lib']
            if lib == 'lib64':
                sandbox += ['--symlink', '/usr/lib64', '/lib64']
            search = ':'.join(f'/usr/{lib}{suffix}' for suffix in ('', '/hal', '/lwe', '/rustlib/dylib'))
            result = run(output / f'{arch}-{side}-symbols.txt',
                         sandbox + ['/qemu', f'/usr/{lib}/{interpreter}',
                                    '--inhibit-cache', '--library-path', search, '/probe'], check=False)
            report.append(dict(arch=arch, repository=side, exit_code=result.returncode,
                               symbols=result.stdout.splitlines(), stderr=result.stderr.strip()))
            print(arch, side, result.returncode, result.stdout.strip().replace('\n', '; '), flush=True)
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(any(r['exit_code'] for r in report))


if __name__ == '__main__':
    sys.exit(main())
