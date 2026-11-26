#!/usr/bin/env python3
"""List startup dependencies using each published ARM image's own loader."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-audit', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    report = []
    args.out.mkdir(parents=True, exist_ok=True)
    for arch, lib, qemu, loader in (
        ('aarch64', 'lib64', 'qemu-arm64-static', 'ld-linux-aarch64.so.1'),
        ('armv7l', 'lib', 'qemu-arm-static', 'ld-linux.so.3'),
    ):
        qemu = shutil.which(qemu) or (shutil.which('qemu-aarch64-static') if arch == 'aarch64' else None)
        if not qemu:
            raise ValueError(f'Missing static QEMU for {arch}')
        root = args.image_audit.resolve() / 'extracted' / f'tizen-headed-{arch}' / 'rootfs'
        if not root.is_dir():
            raise ValueError(f'Missing {root}')
        locations = [f'/usr/{lib}', f'/{lib}']
        for path in [root / 'etc/ld.so.conf', *sorted((root / 'etc/ld.so.conf.d').glob('*.conf'))]:
            for line in path.read_text().splitlines():
                entry = line.partition('#')[0].strip()
                if entry.startswith('/') and ' ' not in entry and entry not in locations:
                    locations.append(entry)
        binding = ['bwrap', '--unshare-all', '--new-session', '--die-with-parent',
                   '--clearenv', '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
                   '--ro-bind', str(root / 'usr'), '/usr', '--ro-bind', str(root / 'etc'), '/etc',
                   '--ro-bind', qemu, '/audit-qemu', '--symlink', '/usr/lib', '/lib']
        if lib == 'lib64':
            binding += ['--symlink', '/usr/lib64', '/lib64']
        common = binding + ['/audit-qemu', f'/usr/{lib}/{loader}', '--inhibit-cache',
                            '--library-path', ':'.join(locations), '--list']
        paths = ['/usr/bin/deviced', '/usr/sbin/deviced-request-shutdown',
                 '/usr/bin/wrt-loader', f'/usr/{lib}/libdeviced.so.0.1.0',
                 f'/usr/{lib}/libapp-installers.so.1']
        for path in paths:
            logfile = args.out / (arch + '-' + Path(path).name + '.txt')
            local = root / path.lstrip('/')
            if not (local.exists() or local.is_symlink()):
                report.append(dict(arch=arch, file=path, status='artifact absent'))
                continue
            argv = common + [path]
            result = subprocess.run(argv, text=True, capture_output=True, timeout=30)
            logfile.write_text(json.dumps(argv) + '\n' + result.stdout + result.stderr)
            print(arch, path, result.returncode, flush=True)
            report.append(dict(arch=arch, file=path,
                               status='dependencies resolved' if result.returncode == 0 else 'loader error',
                               exit_code=result.returncode, evidence=logfile.name))
    (args.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(any(r['status'] == 'loader error' for r in report))


if __name__ == '__main__':
    sys.exit(main())
