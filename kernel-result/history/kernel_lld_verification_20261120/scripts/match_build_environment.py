#!/usr/bin/env python3
"""Find historical original builder dependencies in the pinned Base metadata."""
import argparse
import gzip
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

directory = Path('evidence/build')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('packages', nargs='*', default=['rpm', 'rpm-build', 'llvm'])
names = set(parser.parse_args().packages)
repomd = ET.parse(directory / 'historical-base-index.out')
meta = repomd.find("./{*}data[@type='primary']")
data = (directory / 'historical-base-primary.out').read_bytes()
assert hashlib.sha256(data).hexdigest() == meta.findtext('{*}checksum')
xml = gzip.decompress(data)
assert hashlib.sha256(xml).hexdigest() == meta.findtext('{*}open-checksum')
for package in ET.fromstring(xml).findall('{*}package'):
    name = package.findtext('{*}name')
    arch = package.findtext('{*}arch')
    if name not in names or arch != 'armv7l':
        continue
    version = package.find('{*}version')
    info = package.find('{*}format')
    location = package.find('{*}location')
    size = package.find('{*}size')
    print(name, arch, version.get('ver'), version.get('rel'), location.get('href'), package.findtext('{*}checksum'), size.get('package'), sep='\t')
    for file in info.findall('{*}file'):
        if 'ld.lld' in file.text or 'find-debuginfo' in file.text or 'debugedit' in file.text:
            print(file.text)
