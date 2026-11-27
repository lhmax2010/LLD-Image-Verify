#!/usr/bin/env python3
"""Independently compare the raw boot image, shipped ARM ELF and debug notes."""
import argparse
import hashlib
import mmap
from pathlib import Path
import re
import struct
import subprocess
import zlib

from review_common import BASE, HERE, dump, load, need, sha, sha_bytes

HIST_RPM = 'evidence/build/historical-base/rpm-4.14.1.1-1.8.armv7l.rpm'
HIST_BUILD = 'evidence/build/historical-base/rpm-build-4.14.1.1-1.8.armv7l.rpm'
HIST_FIND = 'evidence/build/historical-base/rpm-build/usr/lib/rpm/find-debuginfo.sh'
OLD = '99ba05b664f7ece7686ab5f087bf54680bb172e6'
NEW = 'bac659039ce25486da3473a6da562dc0e7fd1eea'
SECTION_ALLOC = 2
SECTION_NOBITS = 8
SEGMENT_LOAD = 1

def rpm_query(base, pkg, members):
    command = ['rpm','-qp','--qf','%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]',pkg]
    result = subprocess.run(command,cwd=base,capture_output=True,check=True)
    algo,*lines = result.stdout.decode().splitlines()
    need(algo=='8',f'Expected RPM SHA256 digests: {pkg}')
    raw = dict(line.split('\t',1) for line in lines)
    return {path:raw[path] for path in members}, dict(argv=command,exit_status=result.returncode,selected_file_digests={path:raw[path] for path in members})

def cpio_file(base, pkg, name):
    pipe = subprocess.run(['rpm2cpio',pkg],cwd=base,capture_output=True,check=True)
    file = subprocess.run(['cpio','--extract','--to-stdout','--quiet','.'+name],input=pipe.stdout,capture_output=True,check=True)
    need(file.stdout,f'empty cpio member {name}')
    return file.stdout

def notes(data):
    items, offset = [], 0
    while offset < len(data):
        start = offset
        owner_size, desc_size, typ = struct.unpack_from('<III',data,offset)
        offset += 12
        owner = data[offset:offset+owner_size].rstrip(b'\0').decode()
        offset += (owner_size+3)&~3
        desc = data[offset:offset+desc_size].hex()
        offset += (desc_size+3)&~3
        need(offset<=len(data),'truncated ELF note')
        items.append(dict(offset=start, owner=owner, typ=typ, description=desc))
    return items

def read_elf(path):
    with path.open('rb') as source, mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as raw:
        need(raw[:6]==b'\x7fELF\x01\x01',f'Unexpected ELF class/data {path}')
        _,machine,_,_,po,so,_,_,pes,pn,ses,sn,si = struct.unpack_from('<HHIIIIIHHHHHH',raw,16)
        need(machine==40 and pes==32 and ses==40,'Expected ARM ELF32 program/section tables')
        segments = [struct.unpack_from('<8I',raw,po+i*pes) for i in range(pn)]
        hdr = [struct.unpack_from('<10I',raw,so+i*ses) for i in range(sn)]
        n_off,n_len = hdr[si][4:6]
        names = raw[n_off:n_off+n_len]
        rows = {}
        for index,section in enumerate(hdr):
            name_idx,st,flags,vma,off,size,*_ = section
            name = names[name_idx:names.index(b'\0',name_idx)].decode()
            hosts = [(j,paddr+vma-vaddr) for j,(pt,p_off,vaddr,paddr,fs,ms,_,_) in enumerate(segments)
                     if pt==SEGMENT_LOAD and vaddr<=vma and vma+size<=vaddr+ms and p_off<=off and off+size<=p_off+fs
                     and vma-vaddr==off-p_off]
            display = dict(index=index,name=name,section_type=st,flags=flags,vma=vma,file_offset=off,size=size,
                           load_segments=hosts)
            if name:
                need(name not in rows,f'duplicate ELF section name {name}')
                if st!=SECTION_NOBITS and ((flags&SECTION_ALLOC) or name in ('.comment','.gnu_debuglink')):
                    display['bytes']=raw[off:off+size]
                rows[name]=display
    return rows

def alloc_compare(table, raw):
    rows = [item for item in table.values()
            if item['flags']&SECTION_ALLOC and item['section_type']!=SECTION_NOBITS and item['size']]
    need(all(len(set(lma for _,lma in item['load_segments']))==1 for item in rows),'unmappable alloc section')
    base = min(item['load_segments'][0][1] for item in rows)
    rows.sort(key=lambda row: row['load_segments'][0][1])
    result, gaps, cursor = [], [], 0
    for row in rows:
        loads=row['load_segments']
        lma=loads[0][1]
        start=lma-base
        size=row['size']
        stop=start+size
        need(cursor<=start<=stop<=len(raw),f'out-of-bounds or overlapping raw interval {row["name"]}')
        if start>cursor:
            gaps.append([cursor,start])
        equal=row['bytes']==raw[start:stop]
        details={k:v for k,v in row.items() if k!='bytes'}
        details.update(raw_offset=start,lma=lma,equals=equal)
        if not equal:
            delta=[j for j,(a,b) in enumerate(zip(row['bytes'],raw[start:stop])) if a!=b]
            need(len(delta)<=40,f'large byte drift in {row["name"]}')
            cut=slice(delta[0],delta[-1]+1)
            details.update(difference_count=len(delta),section_offsets=delta,
                           raw_hex=raw[start:stop][cut].hex(),elf_hex=row['bytes'][cut].hex(),
                           difference_raw_file_offset=start+delta[0],difference_elf_file_offset=row['file_offset']+delta[0])
        result.append(details)
        cursor=stop
    if cursor<len(raw):
        gaps.append([cursor,len(raw)])
    need(all(not any(raw[start:stop]) for start,stop in gaps),'raw non-section interval contains nonzero bytes')
    return dict(lma_base=base,sections=result,section_total=len(rows),equal_sections=sum(r['equals'] for r in result),
                covered_bytes=sum(r['size'] for r in result),unrepresented_zero_ranges=gaps,raw_size=len(raw))

def debug_binding(elf, debug, path):
    raw = elf['.gnu_debuglink']['bytes']
    name = raw.split(b'\0',1)[0].decode()
    crc_pos = (len(name)+4)&~3
    crc, = struct.unpack_from('<I',raw,crc_pos)
    actual = 0
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for payload in iter(lambda: stream.read(2**20),b''):
            actual = zlib.crc32(payload,actual)
            checksum.update(payload)
    need(name==path.name and crc==actual,f'.gnu_debuglink mismatch {path}')
    comment=debug['.comment']
    markers=[part.decode() for part in comment['bytes'].split(b'\0') if part]
    need('.comment' not in elf and 'Linker: LLD 22.1.8' in markers,'unexpected linker marker placement')
    return dict(filename=name,stored_crc32=f'{crc:08x}',actual_crc32=f'{actual:08x}',debug_sha256=checksum.hexdigest(),
                stripped_comment_present=False,debug_comment_file_offset=comment['file_offset'],
                debug_comment_alloc=bool(comment['flags']&SECTION_ALLOC),debug_comment=markers)

def output_binding(base):
    binary = load(base,'03_kernel_linker_evidence.json')['binaries']
    items = [next(item for item in binary if predicate(item['path'])) for predicate in (
         lambda s:s=='/boot/zImage', lambda s:s.endswith('arm-rpi4/vmlinux'),
         lambda s:s.endswith('arm-rpi4/vmlinux.debug'), lambda s:s.endswith('compressed/vmlinux'),
         lambda s:s.endswith('compressed/vmlinux.debug'))]
    rpm = {Path(r['rpm_path']).name.removesuffix('.rpm'):r['rpm_path']
           for r in load(base,'02_repository_identity.json')['selected_rpms']}
    groups = {}
    for item in items:
        groups.setdefault(item['rpm'],[]).append(item['path'])
    dos = {key:rpm_query(base,rpm[key],members) for key,members in groups.items()}
    content = {}
    for item in items:
        source=base/item['file']
        digest=sha(source)
        need(digest==dos[item['rpm']][0][item['path']]==item['raw_sha256'],f'RPM file-digest mismatch {item["path"]}')
        content[item['path']] = dict(file='round1/'+item['file'],member=item['path'],
                                     rpm='round1/'+rpm[item['rpm']],sha256=digest)
    return items,content,[receipt for _,receipt in dos.values()]

def packaging(base, out):
    log = 'evidence/build/linux-rpi-armv7l.out'
    original=(base/log).read_text().splitlines()
    call = original[14458]
    need('/usr/lib/rpm/find-debuginfo.sh' in call and '--build-id-seed 6.12.80-0' in call,'historical invocation differs')
    macro = cpio_file(base,HIST_RPM,'/usr/lib/rpm/macros')
    historical = cpio_file(base,HIST_BUILD,'/usr/lib/rpm/find-debuginfo.sh')
    need(historical==(base/HIST_FIND).read_bytes(),'historic find-debuginfo recipe drift')
    need(b'%{?_unique_build_ids:--build-id-seed "%{VERSION}-%{RELEASE}"}' in macro and
         b'%_unique_build_ids\t1' in macro,'build-id-seed macro missing')
    (out/'evidence/build-id/historical-rpm-macros.out').write_bytes(macro)
    (out/'evidence/build-id/historical-find-debuginfo.sh.txt').write_bytes(historical)
    fields = (14011,14459,14579,14853)
    return dict(log='round1/'+log, log_sha256=sha(base/log), lines={str(n):original[n-1] for n in fields},
                macro_package='round1/'+HIST_RPM, macro_path='evidence/build-id/historical-rpm-macros.out',
                macro_sha256=sha_bytes(macro), macro_rule_lines=[182,189,556],
                version_release_seed='6.12.80-0', find_debuginfo_sha256=sha_bytes(historical),
                find_debuginfo='evidence/build-id/historical-find-debuginfo.sh.txt',
                reseed_lines=[445,447], stripping_lines=[248,281,495,503])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=BASE)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    (out/'evidence/build-id').mkdir(parents=True,exist_ok=True)
    items,members,receipts=output_binding(base)
    boot,main,debug,wrap,wdebug=items
    boot_bytes=(base/boot['file']).read_bytes()
    need(boot_bytes[36:40]==bytes.fromhex('18286f01'),'ARM zImage header magic mismatch')
    boot_meta=boot['raw_payloads'][0]
    offset=boot_meta['source_offset']
    gzip_member=zlib.decompressobj(wbits=31)
    linear=gzip_member.decompress(boot_bytes[offset:])+gzip_member.flush()
    need(gzip_member.eof and sha_bytes(linear)==boot_meta['sha256'] and linear==(base/boot_meta['file']).read_bytes(),'raw ARM image differs')
    table,dt,wt,wdt=(read_elf(base/member['file']) for member in (main,debug,wrap,wdebug))
    main_result=alloc_compare(table,linear)
    wrap_result=alloc_compare(wt,boot_bytes)
    mismatch=[row for row in main_result['sections'] if not row['equals']]
    need(main_result['section_total']==32 and len(mismatch)==1 and mismatch[0]['name']=='.notes'
         and mismatch[0]['difference_count']==20 and mismatch[0]['section_offsets']==list(range(64,84))
         and mismatch[0]['raw_hex']==OLD and mismatch[0]['elf_hex']==NEW,'unexpected main ELF change')
    need(wrap_result['section_total']==wrap_result['equal_sections']==6,'unexpected wrapper drift')
    raw_notes_line=(base/'evidence/runtime/notes.out').read_text().splitlines()
    raw_runtime=bytes.fromhex(' '.join(raw_notes_line[1:]))
    need(len(raw_runtime)==84 and sha_bytes(raw_runtime)==raw_notes_line[0].split()[0]
         and raw_runtime==(base/'evidence/runtime/kernel-notes.bin').read_bytes(),'runtime note transport differs')
    note_start=mismatch[0]['raw_offset']
    need(raw_runtime==linear[note_start:note_start+84],'raw runtime note bytes differ')
    published_notes=notes(table['.notes']['bytes'])
    need([n['description'] for n in published_notes if n['owner']=='GNU' and n['typ']==3]==[NEW],
         'no GNU Build ID in devel .notes')
    need(notes(dt['.notes']['bytes'])==published_notes,'debug ELF note bytes differ')
    data = dict(status='PASS', old_build_id=OLD, postprocessed_build_id=NEW, archived_rpm_members=members,
                rpm_query_receipts=receipts,
                comparison_scope='Non-empty file-backed SHF_ALLOC sections mapped through PT_LOAD. Header, non-ALLOC sections, NOBITS and debug data are outside this equality.',
                zimage_gzip=dict(member_offset=offset,compressed_member_size=len(boot_bytes)-offset-len(gzip_member.unused_data),raw_sha256=sha_bytes(linear),raw_size=len(linear)),
                main_kernel=main_result,arm_decompressor=wrap_result,
                exact_difference=mismatch[0], runtime=dict(note_size=len(raw_runtime),note_sha256=sha_bytes(raw_runtime),full_note_offset=note_start,
                     raw_hex=raw_runtime.hex(),parsed_notes=notes(raw_runtime),exact_equal=True,source='round1/evidence/runtime/notes.out'),
                debuglinks=dict(main=debug_binding(table,dt,base/debug['file']),decompressor=debug_binding(wt,wdt,base/wdebug['file'])),
                packaging=packaging(base,out), section_implication='debugedit recomputes notes and edits DWARF paths; stripping may remove or separate .comment. Retained sidecar .comment is hashed and debuglink matched.')
    dump(out/'BUILD_ID_COMPARISON.json',data)
    print('PASS: 31/32 main sections; only 20 GNU note description bytes differ; 6/6 decompressor; 84/84 live notes; both debuglink CRCs.')

if __name__=='__main__':
    main()
