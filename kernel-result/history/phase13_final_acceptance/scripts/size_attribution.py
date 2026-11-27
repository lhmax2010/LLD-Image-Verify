#!/usr/bin/env python3
"""Account for the entire physical ARM ELF file without counting NOBITS."""
from collections import Counter
import csv
import struct

from review_phase12 import OUT, ROOT, bench, elf, prior, record_file, require, save


def inspect(path):
    payload=path.read_bytes()
    header,sections=elf.parse_sections(payload)
    phoff,shoff=struct.unpack_from('<II',payload,28)
    ehsize,phentsize,phnum,shentsize=struct.unpack_from('<HHHH',payload,40)
    require(phoff==phnum==0,'Unexpected program header range')
    table_size=shentsize*len(sections)
    ranges=[(0,ehsize,'ELF header',1),(shoff,shoff+table_size,'Section header table',4)]
    ranges.extend((s['offset'],s['offset']+s['file_size'],elf.key_label(elf.section_key(s)),s['alignment'])
                  for s in sections if s['file_size'])
    gaps=[]
    cursor=0
    for begin,end,label,alignment in sorted(ranges):
        require(begin>=cursor and end<=len(payload),f'Overlapping or invalid ELF file ranges in {path}')
        if begin>cursor:
            smallest=(-cursor)%(alignment or 1)
            fragment=payload[cursor:begin]
            gaps.append({'start':cursor,'end':begin,'bytes':begin-cursor,'before':label,'alignment':alignment or 1,
                         'minimum_alignment_padding':smallest,'all_zero':not any(fragment),
                         'classification':'ALIGNMENT_PADDING' if smallest==len(fragment) and not any(fragment)
                         else 'OTHER_LAYOUT_BYTES'})
        cursor=end
    if cursor<len(payload):
        gaps.append({'start':cursor,'end':len(payload),'bytes':len(payload)-cursor,'before':'EOF',
                     'all_zero':not any(payload[cursor:]),'classification':'OTHER_LAYOUT_BYTES'})
    occupied=sum(end-begin for begin,end,_,_ in ranges)
    require(occupied+sum(g['bytes'] for g in gaps)==len(payload),'Uncovered file bytes')
    return {'path':path,'sha256':bench.sha(path),'size':len(payload),'header':header,'sections':sections[1:],
            'elf_header_bytes':ehsize,'section_headers_bytes':table_size,'gaps':gaps}


def group(section):
    if section.startswith(('.rel.debug_','.rela.debug_')):
        return 'DEBUG_RELOCATION_TABLE'
    if section.startswith(('.rel.','.rela.')):
        return 'RELOCATION_TABLE'
    if section=='.debug_str':
        return 'DEBUG_MERGEABLE_STRINGS'
    if section.startswith('.debug_'):
        return 'OTHER_DEBUG_SECTION'
    if section in ('.symtab','.strtab','.shstrtab'):
        return 'SYMBOL_AND_NAME_TABLES'
    return 'SECTION'


def classify_hex(a,b):
    data_a,data_b=a['bytes'],b['bytes']
    physical=lambda content: [piece for piece in content.split(b'\x00') if piece]
    entries_a,entries_b=physical(data_a),physical(data_b)
    unique_a,unique_b=set(entries_a),set(entries_b)
    require(not unique_b-unique_a,'Unexpected new physical debug string entries')
    missing=[item for item in unique_a if data_b.find(item+b'\x00')<0]
    require(not missing,'A BFD debug string cannot be represented by the LLD string data')
    return {'bfd_bytes':len(data_a),'lld_bytes':len(data_b),'delta_bytes':len(data_b)-len(data_a),
            'bfd_flags':a['flag_names'],'lld_flags':b['flag_names'],'bfd_entry_size':a['entry_size'],'lld_entry_size':b['entry_size'],
            'bfd_nonempty_physical_entries':len(entries_a),'lld_nonempty_physical_entries':len(entries_b),
            'bfd_distinct_physical_entries':len(unique_a),'lld_distinct_physical_entries':len(unique_b),
            'bfd_strings_present_as_lld_suffix_only':len(unique_a-unique_b),
            'all_bfd_nonempty_strings_remain_representable':True,
            'raw_bfd_duplicate_bytes':sum(len(s)+1 for s in entries_a)-sum(len(s)+1 for s in unique_a)}


def main():
    expected=prior('evidence/replay/link-replay.json')['products']
    original=prior('evidence/elf/frozen-intermediate.json')
    left,right=(inspect(record_file(expected[mode]['intermediate'])) for mode in ('bfd','lld'))
    indices=[{elf.section_key(s):s for s in obj['sections']} for obj in (left,right)]
    rows=[]
    def add(kind,label,old,new,old_n,new_n,old_offset=None,new_offset=None,explanation='',old_align=None,new_align=None):
        rows.append({'category':kind,'section_or_region':label,'bfd_logical_bytes':old_n,'lld_logical_bytes':new_n,
                     'logical_delta_bytes':new_n-old_n,'bfd_file_bytes':old,'lld_file_bytes':new,
                     'file_delta_bytes':new-old,'bfd_offset':old_offset,'lld_offset':new_offset,
                     'bfd_alignment':old_align,'lld_alignment':new_align,'note':explanation})
    add('ELF_HEADER','ELF header',52,52,52,52,0,0,'ARM ELF32 ET_REL, EABI5 flags differ in soft-float tagging')
    for key in sorted(indices[0].keys()|indices[1].keys()):
        a,b=(idx.get(key,{}) for idx in indices)
        note='SHT_NOBITS occupies no file bytes' if any(x.get('type')==8 for x in (a,b)) else (
             'Equal bytes' if a.get('content_sha256')==b.get('content_sha256') else
             'Payload or encoding differs, see Phase 12 semantic comparison')
        add('NOBITS' if any(x.get('type')==8 for x in (a,b)) else group(key[0]),elf.key_label(key),
            a.get('file_size',0),b.get('file_size',0),a.get('size',0),b.get('size',0),
            a.get('offset'),b.get('offset'),note,a.get('alignment'),b.get('alignment'))
    section_symbols=[]
    mapping_symbols=[]
    for artifact in (left,right):
        _,all_sections=elf.parse_sections(artifact['path'].read_bytes())
        tables=elf.parse_symbols(all_sections)
        symbols=[(i,s) for i,t in tables.items() for s in t[1:]]
        section_symbols.append(Counter(all_sections[elf.symbol_section_index(all_sections[i],all_sections,s)]['name']
                                       for i,s in symbols if s['type']=='SECTION'))
        mapping_symbols.append(sum(bool(elf.MAPPING.fullmatch(s['name'])) for _,s in symbols))
    removed_section_symbols=section_symbols[0]-section_symbols[1]
    require(removed_section_symbols=={'.note.GNU-stack':1} and not(section_symbols[1]-section_symbols[0])
            and mapping_symbols[0]-mapping_symbols[1]==101, 'Unexpected removed symbol composition')
    old_table,new_table=(item['section_headers_bytes'] for item in (left,right))
    add('SECTION_HEADERS','ELF section header table',old_table,new_table,old_table,new_table,
        explanation='40 Bytes per ARM ELF32 section header, including null section header')
    for kind in ('ALIGNMENT_PADDING','OTHER_LAYOUT_BYTES'):
        counts=[sum(g['bytes'] for g in item['gaps'] if g['classification']==kind) for item in (left,right)]
        add(kind,kind.replace('_',' ').lower(),*counts,*counts,
            explanation='Physical gaps tracked individually in evidence/review/intermediate-layout.json')
    require(sum(r['bfd_file_bytes'] for r in rows)==left['size'] and sum(r['lld_file_bytes'] for r in rows)==right['size'],
            'Rows do not account for total file sizes')
    add('TOTAL','Entire file',left['size'],right['size'],left['size'],right['size'],explanation='Sum of file bytes excluding this row')
    require(rows[-1]['file_delta_bytes']==-506628,'Unexpected net delta')
    require(original['left']['layout']['section_table_bytes']==old_table and
            original['right']['layout']['section_table_bytes']==new_table,'Mismatch against Phase 12 layout')
    strings=classify_hex(indices[0][('.debug_str',1)],indices[1][('.debug_str',1)])
    rel_rows=[row for row in rows if 'RELOCATION_TABLE' in row['category']]
    other_debug=[row for row in rows if row['category']=='OTHER_DEBUG_SECTION']
    categories={}
    for row in rows[:-1]:
        categories[row['category']]=categories.get(row['category'],0)+row['file_delta_bytes']
    rec={'status':'PASS_EXACT_FILE_DELTA','sha256':{mode:item['sha256'] for mode,item in zip(('bfd','lld'),(left,right),strict=True)},
         'total_bytes':{'bfd':left['size'],'lld':right['size'],'delta':-506628},
         'file_delta_by_category':categories,'debug_str':strings,
         'relocation_table_file_delta_bytes':sum(row['file_delta_bytes'] for row in rel_rows),
         'other_debug_section_file_delta_bytes':sum(row['file_delta_bytes'] for row in other_debug),
         'removed_intermediate_symbols':{'local_mapping_symbols':101,'local_section_symbols':dict(removed_section_symbols)},
         'physical_gaps':{'bfd':left['gaps'],'lld':right['gaps']}}
    save(OUT/'intermediate-layout.json',rec)
    with (ROOT/'INTERMEDIATE_SIZE_ATTRIBUTION.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(categories)
    print(strings)


if __name__=='__main__':
    main()
