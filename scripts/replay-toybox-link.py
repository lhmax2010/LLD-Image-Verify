#!/usr/bin/env python3
"""Replay the Toybox build in a read-only saved GBS root without sudo."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
from verify import sha256

BUILD_DIR = '/home/abuild/rpmbuild/BUILD/toybox-0.8.14'
LINK = 'do_loudly $BUILD $LNKFILES $LINK -o "$UNSTRIPPED" || exit 1'
MACROS = {'CC', 'CXX', 'AR', 'RANLIB', 'LDFLAGS', 'CFLAGS', 'CXXFLAGS'}
LOG_PREFIX = re.compile(r'^\[\s*\d+s\]\s*\+ ')
LINKER = re.compile(r'\b(LLD [\d.]+|GNU ld \(GNU Binutils\) [\d.]+)')


def build_settings(log):
    values = {}
    with log.open(errors='replace') as f:
        in_build = False
        for line in f:
            if 'Executing(%build):' in line:
                in_build = True
            if not in_build or not (match := LOG_PREFIX.match(line)):
                continue
            tail = line[match.end():].strip()
            if tail.startswith('make ') and 'LDOPTIMIZE=' in tail:
                command = [arg for arg in shlex.split(tail) if arg != 'V=1']
                if '-Wl,-v' not in ' '.join(command):
                    raise ValueError(f'Stage missing linker version probe: {log}')
                return values, command
            if not re.match(r'^(?:export )?(?:CC|CXX|AR|RANLIB|LDFLAGS|CFLAGS|CXXFLAGS)=', tail):
                continue
            for arg in shlex.split(tail):
                key, eq, val = arg.partition('=')
                if eq and key in MACROS:
                    values[key] = val
    raise ValueError(f'Could not recover the Toybox build command from {log}')


def bfd_control(prefix, link, source, output, arch, expected):
    args = shlex.split(link)
    raw = 'generated/unstripped/toybox-bfd'
    args[args.index('-o') + 1] = raw
    args.append('-fuse-ld=bfd')
    strip = ['strip', '-s', '-R', '.note*', '-R', '.comment', raw, '-o', 'toybox-bfd']
    log = output / f'{arch}-bfd-control.log'
    with log.open('w') as stream:
        stream.write(json.dumps(prefix + args) + '\n' + json.dumps(prefix + strip) + '\n')
        stream.flush()
        status = subprocess.run(prefix + args, stdout=stream, stderr=subprocess.STDOUT).returncode
        if status == 0:
            status = subprocess.run(prefix + strip, stdout=stream, stderr=subprocess.STDOUT).returncode
    banner = LINKER.search('\n'.join(log.read_text(errors='replace').splitlines()[2:]))
    result = dict(exit=status, log=log.name, linker=banner[1] if banner else '')
    if status == 0:
        exe = source / 'toybox-bfd'
        shutil.copyfile(exe, output / f'{arch}-toybox-bfd.elf')
        digest = sha256(exe)
        result.update(sha256=digest, historical_byte_match=digest == expected)
    return result


def replay(work, arch, expected, output, with_bfd_control, fixed_mtime):
    log = work / f'gbs-{arch}.log'
    values, make = build_settings(log)
    chroot_path = (work / f'gbs-{arch}' / f'local/BUILD-ROOTS/scratch.{arch}.0')
    if not chroot_path.is_dir():
        raise ValueError(f'Missing build root: {chroot_path}')
    cpus = ','.join(map(str, sorted(os.sched_getaffinity(0))[:2]))
    with tempfile.TemporaryDirectory(prefix='toybox-link-replay-', dir='/tmp') as temp:
        source = Path(temp) / 'source'
        shutil.copytree(chroot_path / BUILD_DIR.lstrip('/'), source, symlinks=True)
        recipe = source / 'scripts/make.sh'
        original = recipe.read_text()
        if original.count(LINK) != 1:
            raise ValueError(f'Could not identify the final link in {recipe}')
        trace = 'printf "\\nTOYBOX_FINAL_LINK %s\\n" "$BUILD $LNKFILES $LINK -o $UNSTRIPPED" >&2'
        content = original.replace(LINK, trace + '\n' + LINK)
        if fixed_mtime is not None:
            gzip_pipe = 'gzip -9 |'
            if content.count(gzip_pipe) != 1:
                raise ValueError(f'Could not identify the embedded help gzip in {recipe}')
            mtime_bytes = ''.join(f'\\{byte:03o}' for byte in fixed_mtime.to_bytes(4, 'little'))
            # Emit the original mtime while generating zhelp.h, before compiling any object.
            gzip_with_mtime = ('gzip -9 | { dd bs=1 count=4 2>/dev/null; '
                               'dd bs=1 count=4 of=/dev/null 2>/dev/null; '
                               f"printf '{mtime_bytes}'; cat; }} |")
            content = content.replace(gzip_pipe, gzip_with_mtime)
        recipe.write_text(content)
        command = ['taskset', '-c', cpus, 'bwrap', '--unshare-all', '--new-session',
                   '--die-with-parent', '--clearenv', '--ro-bind', str(chroot_path), '/',
                   '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                   '--bind', str(source), BUILD_DIR, '--chdir', BUILD_DIR,
                   '--setenv', 'PATH', '/usr/bin:/usr/sbin:/bin:/sbin',
                   '--setenv', 'LC_ALL', 'C', '--setenv', 'CPUS', '2']
        for key, value in values.items():
            command += ['--setenv', key, value]
        output.mkdir(parents=True, exist_ok=True)
        outputlog = output / f'{arch}-replay.log'
        with outputlog.open('w') as stream:
            stream.write(json.dumps(command + make) + '\n')
            stream.flush()
            status = subprocess.run(command + make, stdout=stream, stderr=subprocess.STDOUT).returncode
        lines = outputlog.read_text(errors='replace').splitlines()
        last_link = next((i for i, line in enumerate(lines) if 'TOYBOX_FINAL_LINK ' in line), None)
        trace = LINKER.search('\n'.join(lines[last_link + 1:])) if last_link is not None else None
        record = dict(architecture=arch, build_exit=status, expected_elf_sha256=expected,
                      original_gbs_log=str(log), replay_log=outputlog.name,
                      linker=trace[1] if trace else '',
                      final_link=lines[last_link].partition('TOYBOX_FINAL_LINK ')[2] if last_link is not None else '',
                      library_probes=[])
        if fixed_mtime is not None:
            record['gzip_mtime_set_before_compilation'] = fixed_mtime
        generated = source / 'generated/build.sh'
        if generated.is_file():
            record['library_probes'] = [line[10:].strip("'") for line in generated.read_text().splitlines()
                                        if line.startswith('LIBRARIES=') and line != "LIBRARIES=''"]
        if status == 0:
            for name, path in [('unstripped', source / 'generated/unstripped/toybox'),
                               ('stripped', source / 'toybox')]:
                shutil.copyfile(path, output / f'{arch}-toybox-{name}.elf')
                record[f'{name}_sha256'] = sha256(path)
                for probe, flags in [('comment', ('-p', '.comment')), ('header', ('-hW',))]:
                    with (output / f'{arch}-{name}-{probe}.txt').open('w') as f:
                        subprocess.run(['readelf', *flags, path], stdout=f, stderr=subprocess.STDOUT)
            record['historical_byte_match'] = record['stripped_sha256'] == expected
            if with_bfd_control and record['final_link']:
                record['bfd_control'] = bfd_control(command, record['final_link'], source, output, arch, expected)
        print(arch, record['linker'] or 'linker unknown', 'exit', status,
              'image hash match', record.get('historical_byte_match', 'unavailable'), flush=True)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bfd-control', action='store_true',
                        help='Relink the same objects explicitly with GNU ld.bfd for comparison')
    parser.add_argument('--gzip-mtime', type=Path, help='Validated historical mtime receipt')
    args = parser.parse_args()
    with args.expected.open(newline='') as f:
        expected = {r['arch']: r['elf_sha256'] for r in csv.DictReader(f, delimiter='\t')}
    times = json.loads(args.gzip_mtime.read_text()) if args.gzip_mtime else {}
    for arch, entry in times.items():
        if entry['original_sha256'] != expected[arch]:
            raise ValueError(f'Mtime receipt refers to the wrong historical ELF for {arch}')
    rows = [replay(args.work.resolve(), arch, expected[arch], args.output.resolve(), args.bfd_control,
                   times.get(arch, {}).get('mtime'))
            for arch in ('aarch64', 'armv7l')]
    (args.output / 'summary.json').write_text(json.dumps(rows, indent=2) + '\n')
    return int(any(record['build_exit'] or not record['linker'] for record in rows))


if __name__ == '__main__':
    sys.exit(main())
