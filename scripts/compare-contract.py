#!/usr/bin/env python3
"""Compare selected exact-source GCC and LLVM RPMs without running their programs."""
import argparse
import fnmatch
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'share' / 'tizen-lld-verify'))
from verify import extract_one, fetch

ROOT = 'https://download.tizen.org/RBS/TIZEN/Tizen/'
GCC = ROOT + 'Tizen-Unified-Dev/tizen-unified-dev_20261120.082616/'
LLVM = ROOT + 'Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/'
PACKAGES = {
    'deviced': ['/usr/bin/deviced'],
    'libdeviced': ['/usr/{lib}/libdeviced.so*'],
    'wrtjs': ['/usr/bin/wrt-loader'],
    'app-installers': ['/usr/{lib}/libapp-installers.so.*'],
    'app-installers-devel': [],
    'dbus-libs': ['/usr/{lib}/libdbus-1.so.*'],
    'libsolv': ['/usr/{lib}/libsolv.so.*'],
    'lmdb': ['/usr/bin/mdb_stat'],
}
DYNSYM = re.compile(r'^\s*\d+:\s+[0-9a-f]+\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', re.M)
DYNAMIC = re.compile(r'\((NEEDED|SONAME|RPATH|RUNPATH)\).*?\[([^\]]+)\]')
VERDEF = re.compile(r'\bRev:.*?Name: (\S+)|\bParent \d+: (\S+)')
INSTALLER_HEADERS = ('/app_installer.h', '/plugins/plugin.h',
                     '/step/security/step_check_background_category.h', '/app-installers.pc')


def command(*args):
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


def indexes(root, directory):
    area = root + 'repos/standard/packages/'
    metadata = fetch(area + 'repodata/repomd.xml', directory / 'repomd.xml')
    primary = ET.parse(metadata).find(".//{*}data[@type='primary']")
    archive = fetch(urljoin(area, primary.find('{*}location').get('href')),
                    directory / 'primary.xml.gz', primary.findtext('{*}checksum'))
    found = {}
    with gzip.open(archive) as f:
        for _, node in ET.iterparse(f, events=['end']):
            if not node.tag.endswith('}package'):
                continue
            key = node.findtext('{*}name'), node.findtext('{*}arch')
            if key[0] in PACKAGES:
                version = node.find('{*}version')
                found[key] = dict(version=[version.get(k, '0') for k in ('epoch', 'ver', 'rel')],
                                  vcs=version.get('vcs'),
                                  url=urljoin(area, node.find('{*}location').get('href')),
                                  sha256=node.findtext('{*}checksum'))
            node.clear()
    return found


def rpm_contract(rpm):
    files = command('rpm', '-qp', '--qf', '[%{FILEMODES:perms}\t%{FILENAMES}\t%{FILELINKTOS}\n]', str(rpm))
    return dict(files=sorted(files.splitlines()),
                requires=sorted(command('rpm', '-qp', '--requires', str(rpm)).splitlines()),
                provides=sorted(command('rpm', '-qp', '--provides', str(rpm)).splitlines()))


def elf_contract(path, prefix):
    dynamic = command('readelf', '-dW', str(path))
    symbols = command('readelf', '--dyn-syms', '-W', str(path))
    versions = command('readelf', '--version-info', '-W', str(path))
    for label, text in [('dynamic', dynamic), ('dynsym', symbols), ('versions', versions)]:
        prefix.with_name(f'{prefix.name}.{label}.txt').write_text(text)
    definition = versions.partition('Version definition section')[2].partition('Version needs section')[0]
    nodes = {}
    current = ''
    for name, parent in VERDEF.findall(definition):
        if name:
            current = name
            nodes[current] = set()
        elif current and parent:
            nodes[current].add(parent)
    exports = set()
    for size, kind, binding, visibility, section, name in DYNSYM.findall(symbols):
        if section == 'UND' or binding not in {'GLOBAL', 'WEAK', 'UNIQUE'} or visibility not in {'DEFAULT', 'PROTECTED'}:
            continue
        # GNU ld may emit the version node name as a synthetic ABS symbol.
        if section == 'ABS' and size == '0' and kind == 'OBJECT' and name in nodes:
            continue
        exports.add(' '.join([kind, binding, visibility, name, size if kind in {'OBJECT', 'TLS'} else '']))
    return dict(dynamic=sorted(f'{key} {value}' for key, value in DYNAMIC.findall(dynamic)),
                exports=sorted(exports),
                version_definitions=sorted(name + ':' + ','.join(sorted(parents))
                                           for name, parents in nodes.items()))


def diff(left, right):
    return {k: {'gcc_only': sorted(set(left[k]) - set(right[k])),
                'llvm_only': sorted(set(right[k]) - set(left[k]))}
            for k in left
            if set(left[k]) != set(right[k])}


def header_matches(rpms, paths, out, arch):
    records = []
    for name in INSTALLER_HEADERS:
        for path in sorted(p for p in paths['gcc'] & paths['llvm'] if p.endswith(name)):
            digests = {}
            for side, rpm in rpms.items():
                saved = out / side / (arch + '-' + path.lstrip('/').replace('/', '_'))
                extract_one(rpm, path, saved)
                with saved.open('rb') as f:
                    digests[side] = hashlib.file_digest(f, 'sha256').hexdigest()
            records.append(dict(file=path, sha256=digests, identical=digests['gcc'] == digests['llvm']))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gcc', default=GCC)
    parser.add_argument('--llvm', default=LLVM)
    options = parser.parse_args()
    out = options.output.resolve()
    roots = {'gcc': options.gcc.rstrip('/') + '/', 'llvm': options.llvm.rstrip('/') + '/'}
    selection = {side: indexes(url, out / side) for side, url in roots.items()}
    result = []
    for arch, lib in (('aarch64', 'lib64'), ('armv7l', 'lib')):
        for name, targets in PACKAGES.items():
            pair = {side: sources.get((name, arch)) for side, sources in selection.items()}
            record = dict(package=name, arch=arch, rpm=pair)
            result.append(record)
            if not all(pair.values()):
                record['status'] = 'RPM absent on ' + ', '.join(side for side, rpm in pair.items() if not rpm)
                continue
            gcc, llvm = pair['gcc'], pair['llvm']
            if not gcc['vcs'] or gcc['vcs'] != llvm['vcs'] or gcc['version'] != llvm['version']:
                record['status'] = 'source revision or EVR differs'
                continue
            record['status'] = 'compared'
            rpms = {side: fetch(r['url'], out / side / PurePosixPath(r['url']).name, r['sha256'])
                    for side, r in pair.items()}
            metadata = {side: rpm_contract(rpm) for side, rpm in rpms.items()}
            record['rpm_differences'] = diff(metadata['gcc'], metadata['llvm'])
            paths = {side: {line.split('\t')[1] for line in attrs['files'] if line.startswith('-')}
                     for side, attrs in metadata.items()}
            if name == 'app-installers-devel':
                record['headers_and_pc'] = header_matches(rpms, paths, out, arch)
            record['targets'] = {}
            for target in targets:
                glob = target.format(lib=lib)
                common = sorted(p for p in paths['gcc'] & paths['llvm'] if fnmatch.fnmatchcase(p, glob))
                if not common:
                    record['targets'][glob] = {'status': 'no common regular payload path'}
                for path in common:
                    parsed = {}
                    for side, rpm in rpms.items():
                        prefix = out / side / f'{arch}-{name}-{PurePosixPath(path).name}'
                        elf = prefix.with_suffix(prefix.suffix + '.elf')
                        extract_one(rpm, path, elf)
                        parsed[side] = elf_contract(elf, prefix)
                    record['targets'][path] = {'status': 'compared',
                                               'differences': diff(parsed['gcc'], parsed['llvm']),
                                               'counts': {side: {k: len(v) for k, v in fields.items()}
                                                          for side, fields in parsed.items()}}
            print(arch, name, record['status'], flush=True)
    (out / 'contracts.json').write_text(json.dumps({'roots': roots, 'packages': result}, indent=2) + '\n')


if __name__ == '__main__':
    main()
