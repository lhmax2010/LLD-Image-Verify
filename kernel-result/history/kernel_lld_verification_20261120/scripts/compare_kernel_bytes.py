#!/usr/bin/env python3
"""Bind the RPM devel ELF, debug sidecar, boot payload and runtime note."""
import argparse
import json
from pathlib import Path
import hashlib
import struct
import zlib

from analyze_artifacts import ROOT, dump, rel, sha

def parse_elf(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError(f'{path}: expected ELF32 little-endian')
    _, machine, _, _, phoff, shoff, _, _, phentsize, phnum, shentsize, shnum, shstr = struct.unpack_from(
        '<HHIIIIIHHHHHH', data, 16
    )
    if machine != 40 or phentsize != 32 or shentsize != 40:
        raise ValueError(f'{path}: expected standard ARM ELF program/section headers')
    programs = [struct.unpack_from('<8I', data, phoff+i*phentsize) for i in range(phnum)]
    shs = [struct.unpack_from('<10I', data, shoff+i*shentsize) for i in range(shnum)]
    names_offset, names_size = shs[shstr][4:6]
    names = data[names_offset:names_offset+names_size]
    sections = {}
    for nameoff, kind, flags, va, file_off, size, *_ in shs:
        name = names[nameoff:names.index(b'\x00', nameoff)].decode()
        hits = {va-vaddr+paddr for typ, offset, vaddr, paddr, filesz, memsz, pflags, align in programs
            if typ == 1 and vaddr <= va and va+size <= vaddr+memsz and
            (kind == 8 or offset <= file_off and file_off+size <= offset+filesz)}
        pa = next(iter(hits)) if len(hits)==1 else None
        sections[name] = dict(name=name, kind=kind, flags=flags, va=va, pa=pa, offset=file_off, size=size)
    return data, sections

def byte_differences(left, right):
    count = 0
    sample = []
    for offset, (a, b) in enumerate(zip(left, right)):
        if a != b:
            count += 1
            if len(sample) < 40:
                sample.append(offset)
    return count, sample

def alloc_comparison(elf_path, raw_path):
    data, sections = parse_elf(elf_path)
    raw = raw_path.read_bytes()
    sections = [s for s in sections.values() if s['flags'] & 2 and s['kind'] != 8 and s['size']]
    mapped = [s for s in sections if s['pa'] is not None]
    base = min(s['pa'] for s in mapped)
    records = []
    for section in sections:
        size, offset = section['size'], section['offset']
        raw_offset = section['pa']-base if section['pa'] is not None else None
        row = dict(section, raw_offset=raw_offset)
        if raw_offset is not None and 0 <= raw_offset <= (len(raw)-size):
            packaged = data[offset:offset+size]
            boot = raw[raw_offset:raw_offset+size]
            row['match'] = packaged == boot
            if not row['match']:
                count, differences = byte_differences(packaged, boot)
                row['different_bytes'] = count
                row['first_difference_offsets'] = differences
                if count <= 40:
                    lo, hi = differences[0], differences[-1]+1
                    row['difference_window'] = dict(section_offset=lo, raw_hex=boot[lo:hi].hex(),
                                                     elf_hex=packaged[lo:hi].hex())
        else:
            row['match'] = None
        records.append(row)
    aligned = bytearray(len(raw))
    for row in records:
        if row['raw_offset'] is not None and row['match'] is not None:
            start = row['raw_offset']
            aligned[start:start+row['size']] = b'\x01'*row['size']
    gap_count = 0
    gap_offsets = []
    for idx, (present, value) in enumerate(zip(aligned, raw)):
        if not present and value:
            gap_count += 1
            if len(gap_offsets) < 40:
                gap_offsets.append(idx)
    patched = bytearray(raw)
    for row in records:
        if row['match'] is False:
            start = row['raw_offset']
            src, size = row['offset'], row['size']
            patched[start:start+size] = data[src:src+size]
    return dict(elf=rel(elf_path), raw=rel(raw_path), elf_sha256=sha(elf_path), raw_sha256=sha(raw_path),
                raw_size=len(raw), lma_base=base, compared_sections=records,
                unmatched_nonzero_gap_count=gap_count, first_nonzero_gap_offsets=gap_offsets,
                raw_with_packaged_section_bytes_sha256=hashlib.sha256(patched).hexdigest())

def debug_link(elf_path, debug_path, binary_info, debug_info):
    data, sections = parse_elf(elf_path)
    sec = sections.get('.gnu_debuglink')
    if not sec:
        return dict(elf=rel(elf_path), debug=rel(debug_path), status='MISSING_GNU_DEBUGLINK')
    blob = data[sec['offset']:sec['offset']+sec['size']]
    name = blob.split(b'\x00',1)[0]
    offset = (len(name)+4)&~3
    crc = int.from_bytes(blob[offset:offset+4],'little')
    actual = 0
    with debug_path.open('rb') as stream:
        for block in iter(lambda:stream.read(2**20), b''):
            actual = zlib.crc32(block, actual)
    return dict(elf=rel(elf_path), debug=rel(debug_path), debug_sha256=sha(debug_path),
                filename=name.decode(), stored_crc32=f'{crc:08x}', actual_crc32=f'{actual:08x}',
                filename_matches=name.decode()==debug_path.name, crc32_matches=crc==actual,
                build_ids_match=binary_info.get('build_ids')==debug_info.get('build_ids') if binary_info.get('build_ids') else None,
                status='MATCH' if name.decode()==debug_path.name and crc==actual else 'MISMATCH')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static-json', type=Path, default=ROOT/'03_kernel_linker_evidence.json')
    opt = parser.parse_args()
    records = json.loads(opt.static_json.read_text())['binaries']
    boot = next(x for x in records if x['path']=='/boot/zImage')
    devel = next(x for x in records if x['path'].endswith('arm-rpi4/vmlinux'))
    devel_dbg = next(x for x in records if x['path'].endswith('arm-rpi4/vmlinux.debug'))
    wrap = next(x for x in records if x['path'].endswith('compressed/vmlinux'))
    wrap_dbg = next(x for x in records if x['path'].endswith('compressed/vmlinux.debug'))
    candidates = boot.get('raw_payloads', [])
    if len(candidates) != 1:
        raise ValueError(f'expected exactly one validated ARM gzip member, got {len(candidates)}')
    debug_links = [debug_link(ROOT/r['file'], ROOT/s['file'], r, s) for r,s in ((devel,devel_dbg),(wrap,wrap_dbg))]
    main_comparison = alloc_comparison(ROOT/devel['file'],ROOT/candidates[0]['file'])
    wrap_comparison = alloc_comparison(ROOT/wrap['file'],ROOT/boot['file'])
    notes = ROOT/'evidence/runtime/kernel-notes.bin'
    raw = (ROOT/candidates[0]['file']).read_bytes()
    live_notes = dict(evidence=rel(notes))
    if notes.is_file():
        note_data = notes.read_bytes()
        live_notes.update(size=len(note_data), sha256=sha(notes), raw_offset=raw.find(note_data), exact_bytes_in_raw=note_data in raw)
    result = dict(main_kernel=main_comparison, zimage_wrapper=wrap_comparison, debug_links=debug_links,
                  exact_runtime_notes=live_notes)
    dump('evidence/kernel_binary/byte-comparison.json', result)
    print(json.dumps({name:{'sections':len(result[name]['compared_sections']),
           'equal':sum(r['match'] is True for r in result[name]['compared_sections']),
           'nonzero_gaps':result[name]['unmatched_nonzero_gap_count'],
           'differences':[r for r in result[name]['compared_sections'] if r['match'] is not True]}
           for name in ('main_kernel','zimage_wrapper')} | {'debug_links':debug_links,'runtime_notes':live_notes},indent=2))

if __name__ == '__main__':
    main()
