#!/usr/bin/env python3
"""Probe Base Clang's default and generate known-linker ARM ELF controls."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
import config
from verify import fetch


def package_index(base, out):
    area = base.rstrip('/') + '/repos/standard/packages/'
    repomd = fetch(area + 'repodata/repomd.xml', out / 'repomd.xml')
    meta = ET.parse(repomd).find(".//{*}data[@type='primary']")
    xml = fetch(urljoin(area, meta.find('{*}location').get('href')), out / 'primary.xml.gz',
                meta.findtext('{*}checksum'))
    names = {'clang', 'llvm', 'libllvm', 'binutils', 'binutils-libs'}
    result = {}
    with gzip.open(xml) as f:
        for _, p in ET.iterparse(f, events=['end']):
            if not p.tag.endswith('}package'):
                continue
            name, arch = p.findtext('{*}name'), p.findtext('{*}arch')
            if name in names and arch in ('aarch64', 'armv7l'):
                result[name, arch] = (
                    urljoin(area, p.find('{*}location').get('href')), p.findtext('{*}checksum'),
                    p.find('{*}version').get('vcs'))
            p.clear()
    return result


def checked_log(path, argv, check=True):
    result = subprocess.run([str(v) for v in argv], text=True, capture_output=True)
    path.write_text('\n'.join([json.dumps([str(v) for v in argv]), result.stdout, result.stderr]))
    if check:
        result.check_returncode()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=config.BASE)
    parser.add_argument('--image-audit', type=Path, required=True,
                        help='Workspace with extracted headed rootfs for the same Base')
    parser.add_argument('--out', type=Path, required=True)
    options = parser.parse_args()
    out = options.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    packages = package_index(options.base, out)
    for arch, lib, qemu, triple, emulation, interpreter in (
        ('aarch64', 'lib64', 'qemu-arm64-static', 'aarch64-tizen-linux-gnu', 'aarch64linux',
         'ld-linux-aarch64.so.1'),
        ('armv7l', 'lib', 'qemu-arm-static', 'armv7l-tizen-linux-gnueabi', 'armelf_linux_eabi',
         'ld-linux.so.3'),
    ):
        dest = out / arch
        dest.mkdir(exist_ok=True)
        qemu = shutil.which(qemu) or (shutil.which('qemu-aarch64-static') if arch == 'aarch64' else None)
        if not qemu:
            raise ValueError(f'Missing static QEMU for {arch}')
        rootfs = options.image_audit.resolve() / 'extracted' / f'tizen-headed-{arch}' / 'rootfs'
        if not rootfs.is_dir():
            raise ValueError(f'Missing {rootfs}')
        selection, rpms = {}, []
        tools = dest / 'tools'
        tools.mkdir(exist_ok=True)
        for name in ('clang', 'llvm', 'libllvm', 'binutils', 'binutils-libs'):
            url, digest, vcs = packages[name, arch]
            rpms.append(fetch(url, dest / Path(url).name, digest))
            selection[name] = dict(url=url, sha256=digest, vcs=vcs)
        executable = tools / 'usr' / 'bin'
        # The image's /lib interpreter symlink can be absolute inside the guest.
        loader = tools / 'lib' / interpreter
        receipt = dest / 'inputs.json'
        if not (receipt.exists() and json.loads(receipt.read_text()) == selection
                and loader.is_symlink() and (executable / 'clang').is_file()
                and (executable / 'ld.lld').is_file() and (executable / 'ld.bfd').is_file()):
            members = [
                './usr/bin/clang*', './usr/bin/ld.lld', './usr/bin/lld',
                f'./usr/{lib}/libLLVM.so*', f'./usr/{lib}/libclang-cpp.so*',
                f'./usr/{lib}/lib*bfd*.so*', f'./usr/{lib}/libctf*.so*',
                f'./usr/{lib}/lib*sframe*.so*', './usr/bin/ld', './usr/bin/ld.bfd',
                f'./usr/{triple}/bin/ld*',
            ]
            for rpm in rpms:
                with subprocess.Popen(['rpm2cpio', rpm], stdout=subprocess.PIPE) as payload:
                    subprocess.run(['cpio', '--quiet', '-idmu', '--no-absolute-filenames', *members],
                                   cwd=tools, stdin=payload.stdout, check=True)
                    if payload.wait():
                        raise ValueError(f'RPM extraction failed: {rpm}')
        interpreter_path = rootfs / 'usr' / lib / interpreter
        if not loader.is_symlink() or loader.readlink() != interpreter_path:
            loader.parent.mkdir(exist_ok=True)
            pending_loader = loader.with_suffix('.audit-link')
            pending_loader.unlink(missing_ok=True)
            pending_loader.symlink_to(interpreter_path)
            pending_loader.replace(loader)
        pending_receipt = receipt.with_suffix('.partial')
        pending_receipt.write_text(json.dumps(selection, indent=2) + '\n')
        pending_receipt.replace(receipt)
        runner = [qemu, '-L', tools, '-E',
                  'LD_LIBRARY_PATH=' + ':'.join(str(p) for p in
                                            (tools / 'usr' / lib, rootfs / 'usr' / lib))]
        source = dest / 'control.c'
        source.write_text('int probe_a(void) { return 1; }\nint probe_b(void) { return 2; }\n')
        version_map = dest / 'control.map'
        version_map.write_text('VERS_1 { global: probe_a; local: *; };\n'
                               'VERS_2 { global: probe_b; } VERS_1;\n')
        obj = dest / 'control.o'
        clang = executable / (triple + '-clang')
        if not clang.is_file():
            clang = executable / 'clang'
        checked_log(dest / 'clang-default.txt',
                    runner + [clang, f'--target={triple}', '-###', '-fPIC', '-shared',
                              '-nostdlib', source, '-o', dest / 'default.so'])
        checked_log(dest / 'clang-default-no-config.txt',
                    runner + [clang, '--no-default-config', f'--target={triple}', '-###',
                              '-fPIC', '-shared', '-nostdlib', source, '-o', dest / 'default.so'])
        (dest / 'linker-paths.txt').write_text('\n'.join(
            f'{name} -> {path.readlink() if path.is_symlink() else "(regular file)" if path.is_file() else "(missing)"}'
            for name in ('ld', 'ld.bfd', 'ld.lld', 'lld')
            if (path := executable / name)) + '\n')
        checked_log(dest / 'compile.txt',
                    runner + [clang, '--no-default-config', f'--target={triple}', '-c', '-fPIC',
                              source, '-o', obj])
        for linker, name in [('ld.lld', 'lld'), ('ld.bfd', 'bfd')]:
            actual = executable / linker
            if actual.is_symlink() and actual.readlink().is_absolute():
                actual = tools / str(actual.readlink()).lstrip('/')
            checked_log(dest / f'{name}-version.txt', runner + [actual, '--version'])
            elf = dest / f'{name}.so'
            checked_log(dest / f'{name}-link.txt', runner + [actual, '-shared', '-m', emulation,
                        '-z', 'relro', '--version-script', version_map, '-o', elf, obj])
            checked_log(dest / f'{name}-readelf.txt', ['readelf', '-WVl', elf])
            checked_log(dest / f'{name}-comment.txt', ['readelf', '-p', '.comment', elf], check=False)
        checked_log(dest / 'readelf-version.txt', [shutil.which('readelf'), '--version'])
        print(f'{arch}: complete, evidence in {dest}', flush=True)


if __name__ == '__main__':
    main()
