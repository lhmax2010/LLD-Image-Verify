#!/usr/bin/env python3
"""Check Dart's direct ELF writer fingerprint against an image ELF and TPK."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from zipfile import ZipFile


def dart_hash32(data):
    multiplier = 0x5BD1E995
    mask = (1 << 32) - 1
    result = len(data)
    aligned = len(data) & ~3
    for (word,) in struct.iter_unpack('<I', data[:aligned]):
        word = (word * multiplier) & mask
        word ^= word >> 24
        result = ((result * multiplier) & mask) ^ ((word * multiplier) & mask)
    if aligned < len(data):
        result ^= int.from_bytes(data[aligned:], 'little')
        result = (result * multiplier) & mask
    result ^= result >> 13
    result = (result * multiplier) & mask
    return result ^ (result >> 15)


def readelf(mode, elf):
    return subprocess.check_output(['readelf', '-W', mode, elf], text=True)


def probe(elf, tpk):
    binary = elf.read_bytes()
    if binary[:4] != b'\x7fELF' or binary[5] != 1:
        raise ValueError('Expected a little-endian ELF')
    symbols = readelf('--dyn-syms', elf)
    sections = readelf('--sections', elf)
    notes = readelf('--notes', elf)
    section_names = ['.text', '.text', '.rodata', '.rodata']
    snapshot_symbols = ['_kDartVmSnapshotInstructions', '_kDartIsolateSnapshotInstructions',
                        '_kDartVmSnapshotData', '_kDartIsolateSnapshotData']
    machine = struct.unpack_from('<H', binary, 18)[0]
    filler = {183: bytes.fromhex('000020d4000020d4'), 40: bytes.fromhex('700020e1')}[machine]
    computed = []
    for section, symbol in zip(section_names, snapshot_symbols, strict=True):
        address, offset, section_size = (int(v, 16) for v in re.search(
            r'\s' + re.escape(section) + r'\s+PROGBITS\s+(\w+)\s+(\w+)\s+(\w+)', sections).groups())
        start, size = re.search(
            r'^\s*\d+:\s+(\w+)\s+(\w+)\s+OBJECT\s+GLOBAL\s+DEFAULT\s+\d+\s+'
            + re.escape(symbol) + r'$', symbols, re.M).groups()
        relative, size = int(start, 16) - address, int(size, 0)
        if not 0 <= relative <= relative + size <= section_size:
            raise ValueError(f'{symbol} is outside {section}')
        data = binary[offset + relative:offset + relative + size]
        if section == '.text':
            # The hash is taken before the three relocations in InstructionsSection.
            # The image header itself stores the offset to that section.
            width = len(filler)
            header_size = int.from_bytes(data[width:2 * width], 'little')
            if header_size != 64:
                raise ValueError(f'Unexpected Dart image header size: {header_size}')
            index = header_size + 2 * width
            data = data[:index] + filler * 3 + data[index + 3 * width:]
        computed.append(dart_hash32(data) or 1)
    reported = re.search(r'Build ID: ([a-f\d]+)', notes).group(1)
    build_id = struct.pack('<IIII', *computed).hex()
    with ZipFile(tpk) as package:
        packaged = package.read('lib/libapp.so')
    markers = all(marker in symbols for marker in
                  ('_kDartSnapshotBuildId', '_kDartVmSnapshotInstructions', '_kDartVmSnapshotData'))
    return {'elf': str(elf), 'tpk': str(tpk), 'elf_sha256': hashlib.sha256(binary).hexdigest(),
            'tpk_member_sha256': hashlib.sha256(packaged).hexdigest(),
            'tpk_member_matches': binary == packaged, 'dart_symbols': markers,
            'build_id': reported, 'calculated_build_id': build_id, 'build_id_matches': build_id == reported}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('tpk', type=Path)
    args = parser.parse_args()
    evidence = probe(args.elf, args.tpk)
    print(json.dumps(evidence, indent=2))
    if not all(evidence[key] for key in ('dart_symbols', 'build_id_matches', 'tpk_member_matches')):
        raise SystemExit(1)
