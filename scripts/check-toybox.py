#!/usr/bin/env python3
"""Check the published Base toybox RPM bytes and their copies in the LLVM images."""
import argparse
import csv
from pathlib import Path
import subprocess
import sys
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
import config
import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-audit', type=Path, required=True)
    parser.add_argument('--build-xml', type=Path, help='Override the workspace raw/build.xml')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    images, out = args.image_audit.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build = ET.parse(args.build_xml or images / 'raw/build.xml')
    base = build.find('base_id')
    config.SOURCES = {'base': urljoin(base.get('url').replace('http:', 'https:', 1), base.text + '/')}
    config.WORK = out
    verify.fetch_metadata('base', 'packages', ('primary',))
    records = []
    for arch in ('aarch64', 'armv7l'):
        profile = f'tizen-headed-{arch}'
        manifest = next((images / 'images' / profile).glob('*.packages'))
        version, vcs = verify.installed_rpms(manifest, arch)['toybox']
        _, url, rpm_sha = verify.find_runtime_rpm('toybox', arch, version, vcs)
        rpm = verify.fetch(url, out / Path(url).name, rpm_sha)
        exe = out / f'{arch}-toybox.elf'
        verify.extract_one(rpm, '/usr/bin/toybox', exe)
        elf_sha = verify.sha256(exe)
        elf = verify.inspect_elf(exe)
        for section, args in [('sections', ['-SW']), ('notes', ['-nW']), ('comment', ['-p', '.comment'])]:
            cmd = ['readelf', *args, str(exe)]
            info = subprocess.run(cmd, capture_output=True, text=True)
            (out / f'{arch}-{section}.txt').write_text(info.stdout + info.stderr)
        for profile in ('headed', 'headless'):
            image = f'tizen-{profile}-{arch}'
            for part in ('rootfs', 'ramdisk', 'ramdisk-recovery'):
                path = images / 'extracted' / image / part / 'usr/bin/toybox'
                actual = verify.sha256(path)
                if elf_sha != actual:
                    raise ValueError(f'Mismatched toybox SHA256: {path}')
                records.append(dict(arch=arch, image=image, partition=part, elf_sha256=actual,
                                    rpm_sha256=rpm_sha, rpm_url=url, source=vcs, linker=elf['linker'],
                                    build_id=elf['build_id'], debuglink=elf['debuglink']))
        print(f'{arch} {version} {elf_sha} linker={elf["linker"]}', flush=True)
    with (out / 'toybox-identities.tsv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(records)
    print(f'{len(records)} image files matched to {len({r["elf_sha256"] for r in records})} RPM ELF payloads')


if __name__ == '__main__':
    main()
