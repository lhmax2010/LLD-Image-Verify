#!/usr/bin/env python3
"""Parse bounded ELF32 ARM ET_REL tables, metadata and appended module signature."""
from collections import Counter, defaultdict
import hashlib
import re
import struct

ELF_MAGIC = b"\x7fELF\x01\x01\x01"
EM_ARM = 40
SHT_SYMTAB = 2
SHT_RELA = 4
SHT_NOTE = 7
SHT_NOBITS = 8
SHT_REL = 9
SHT_DYNSYM = 11
SHT_SYMTAB_SHNDX = 18
SIGNATURE_MAGIC = b"~Module signature appended~\n"
BINDINGS = {0: "LOCAL", 1: "GLOBAL", 2: "WEAK", 10: "GNU_UNIQUE"}
TYPES = {0: "NOTYPE", 1: "OBJECT", 2: "FUNC", 3: "SECTION", 4: "FILE", 5: "COMMON", 6: "TLS", 10: "GNU_IFUNC"}
VISIBILITIES = ("DEFAULT", "INTERNAL", "HIDDEN", "PROTECTED")
FLAGS = {1: "WRITE", 2: "ALLOC", 4: "EXECINSTR", 16: "MERGE", 32: "STRINGS", 64: "INFO_LINK",
         128: "LINK_ORDER", 256: "OS_NONCONFORMING", 512: "GROUP", 1024: "TLS", 2048: "COMPRESSED"}

def need(condition, message):
    if not condition:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unpack(fmt, data, offset):
    need(0 <= offset <= len(data)-struct.calcsize(fmt), f"Out-of-range {fmt} at {offset}")
    return struct.unpack_from(fmt, data, offset)

def data_slice(data, offset, length):
    need(0 <= offset <= offset+length <= len(data), f"Out-of-range data {offset}:{offset+length}")
    return data[offset:offset+length]

def string(data, offset):
    need(0 <= offset < len(data), f"Out-of-range string index {offset}")
    stop = data.find(b"\0", offset)
    need(stop >= 0, f"Unterminated string index {offset}")
    return data[offset:stop].decode("utf-8", errors="backslashreplace")

def flags_repr(flags):
    return "|".join(name for bit,name in FLAGS.items() if flags&bit)

def module_signature(data):
    if not data.endswith(SIGNATURE_MAGIC):
        return {"present":False, "status":"ABSENT"}
    footer = len(data)-len(SIGNATURE_MAGIC)-12
    header = unpack(">5B3xI",data,footer)
    algo, hash_algo, id_type, signer_len, keyid_len, sig_len = header
    start = footer-sig_len-signer_len-keyid_len
    need(sig_len and 0 <= start <= footer,"Malformed appended module signature")
    return {"present":True, "status":"PRESENT_NOT_CRYPTOGRAPHICALLY_VALIDATED","algorithm":algo,"hash_algorithm":hash_algo,
            "identifier_type":id_type,"signer_length":signer_len,"key_id_length":keyid_len,
            "signature_length":sig_len,"signature_offset":start}

def human_sections(sections):
    return [{name:value for name,value in section.items() if name!="bytes"} for section in sections[1:]]

def parse_sections(data):
    need(data.startswith(ELF_MAGIC),"Expected ELF32 little endian with ELF version 1")
    e_type, machine, ver, entry, phoff, shoff, flags, ehsz, phesz, phnum, shesz, shnum, shstr = unpack("<HHIIIIIHHHHHH",data,16)
    need((e_type,machine,ver,ehsz,shesz)==(1,EM_ARM,1,52,40),"Expected canonical ARM ELF32 ET_REL layout")
    need(shoff >= ehsz,"Missing section table")
    zero=unpack("<10I",data,shoff)
    total=shnum or zero[5]
    table_idx=zero[6] if shstr==0xffff else shstr
    need(total>0 and 0 < table_idx < total and shoff+total*shesz<=len(data),"Invalid section header geometry")
    headers=[unpack("<10I",data,shoff+idx*shesz) for idx in range(total)]
    names=data_slice(data,*headers[table_idx][4:6])
    counts=Counter()
    sections=[]
    for idx,(name_idx,typ,sec_flags,address,offset,size,link,info,align,ent) in enumerate(headers):
        name=string(names,name_idx)
        content = b"" if idx==0 or typ==SHT_NOBITS else data_slice(data,offset,size)
        counts[name]+=1
        sections.append(dict(index=idx,name=name,occurrence=counts[name],type=typ,flags=sec_flags,
            flag_names=flags_repr(sec_flags),address=address,offset=offset,size=size,alignment=align,entry_size=ent,
            link=link,info=info,file_size=len(content),bytes=content,
            content_sha256=digest(content) if typ!=SHT_NOBITS else None))
    header=dict(elf_class="ELF32",machine="ARM",endianness="little",type="ET_REL",
        elf_flags=f"0x{flags:x}",elf_flags_value=flags,arm_eabi_version=(flags>>24)&0xff,
        arm_float_abi="hard" if flags&0x400 else "soft" if flags&0x200 else "unspecified",
        osabi=data[7],abi_version=data[8],section_count=len(sections)-1)
    return header,sections

def parse_build_ids(sections):
    build_ids=[]
    for row in sections:
        if row["type"]!=SHT_NOTE:
            continue
        data=row["bytes"]
        pos=0
        while pos<len(data):
            if not any(data[pos:]):
                break
            name_size, desc_size, typ = unpack("<III",data,pos)
            name=data_slice(data,pos+12,name_size)
            desc_offset=pos+12+((name_size+3)&~3)
            desc=data_slice(data,desc_offset,desc_size)
            if name.rstrip(b"\0")==b"GNU" and typ==3:
                build_ids.append(desc.hex())
            pos=desc_offset+((desc_size+3)&~3)
    return build_ids

def parse_symbol_versions(sections):
    found={x["name"]:x["bytes"] for x in sections if x["name"] in
           ("__versions","__version_ext_crcs","__version_ext_names")}
    by_symbol={}
    for name,content in found.items():
        if name!="__versions":
            continue
        # Tizen Linux ABI uses the 64-byte basic modversion entry. The first
        # four bytes contain the ARM unsigned long CRC; the rest is the name.
        need(len(content)%64==0,"Basic modversion section has an invalid entry length")
        for pos in range(0,len(content),64):
            crc,=unpack("<I",content,pos)
            symbol=string(content[pos+4:pos+64],0)
            need(symbol and symbol not in by_symbol,"Empty or duplicate basic modversion symbol")
            by_symbol[symbol]=f"0x{crc:08x}"
    ext_crcs=found.get("__version_ext_crcs",b"")
    ext_names=found.get("__version_ext_names",b"")
    if "__version_ext_crcs" in found or "__version_ext_names" in found:
        names=[x.decode("ascii") for x in ext_names.rstrip(b"\0").split(b"\0")] if ext_names else []
        need(len(ext_crcs)==4*len(names),"Extended CRC/name pair length mismatch")
        for index,name in enumerate(names):
            need(name and name not in by_symbol,"Empty or duplicate extended modversion symbol")
            crc,=unpack("<I",ext_crcs,4*index)
            by_symbol[name]=f"0x{crc:08x}"
    return dict(encoding="both" if "__versions" in found and ext_crcs else "extended" if ext_crcs else
        "basic" if "__versions" in found else "absent", imports=by_symbol)

def parse_symbols(sections):
    tables={}
    for row in sections:
        if row["type"] not in (SHT_SYMTAB,SHT_DYNSYM):
            continue
        content=row["bytes"]
        need(row["entry_size"]==16 and len(content)%16==0,"Invalid ARM symbol entry length")
        strings=sections[row["link"]]["bytes"]
        extended=next((x["bytes"] for x in sections if x["type"]==SHT_SYMTAB_SHNDX and x["link"]==row["index"]),None)
        symbols=[]
        for pos in range(0,len(content),16):
            name_idx,value,size,info,other,shndx=unpack("<IIIBBH",content,pos)
            if shndx==0xffff:
                need(extended is not None,"Symbol has missing extended section index")
                shndx,=unpack("<I",extended,pos//4)
            name=string(strings,name_idx)
            special={0:"UND",0xfff1:"ABS",0xfff2:"COMMON"}
            if shndx in special:
                sec=special[shndx]
            elif shndx<len(sections):
                sec=sections[shndx]["name"]
            else:
                need(shndx>=0xff00,"Symbol section index outside section table")
                sec=f"RESERVED_0x{shndx:x}"
            typ=TYPES.get(info&0xf,str(info&0xf))
            symbols.append(dict(index=pos//16,table=row["name"],name=name,type=typ,binding=BINDINGS.get(info>>4,str(info>>4)),
                visibility=VISIBILITIES[other&3],other=other,value=value,size=size,section=sec,
                defined=shndx!=0,identity=name or ("@section:"+sec if typ=="SECTION" else "")))
        tables[row["index"]]=symbols
    need(any(sections[index]["type"]==SHT_SYMTAB for index in tables),"No SHT_SYMTAB found")
    return tables

def parse_relocations(sections,tables,names):
    result=[]
    for row in sections:
        typ=row["type"]
        if typ not in (SHT_RELA,SHT_REL):
            continue
        data=row["bytes"]
        width=12 if typ==SHT_RELA else 8
        need(row["entry_size"]==width and len(data)%width==0,"Invalid ARM relocation entry width")
        symbols=tables[row["link"]]
        origin=sections[row["info"]]
        for pos in range(0,len(data),width):
            offset,info=unpack("<II",data,pos)
            kind=info&0xff
            symbol=symbols[info>>8]
            result.append(dict(relocation_section=row["name"],origin_section=origin["name"],offset=offset,
                type_id=kind,type=names.get(kind,f"R_ARM_UNKNOWN_{kind}"),target_symbol=symbol["identity"],
                target_section=symbol["section"],target_binding=symbol["binding"],
                target_defined=symbol["defined"],target_value=symbol["value"],
                addend=unpack("<i",data,pos+8)[0] if width==12 else None))
    return result

def readelf_arm_names(output):
    names={}
    for row in output.splitlines():
        match=re.match(r"\s*[0-9a-fA-F]{8}\s+([0-9a-fA-F]{8})\s+(R_ARM_\w+)\s*",row)
        if match:
            kind=int(match[1],16)&0xff
            need(kind not in names or names[kind]==match[2],"Conflicting relocation name map")
            names[kind]=match[2]
    return names

def parse_modinfo(data):
    result=defaultdict(list)
    for item in data.rstrip(b"\0").split(b"\0"):
        if not item:
            continue
        key,value=item.decode("utf-8",errors="backslashreplace").split("=",1)
        result[key].append(value)
    return dict(result)

def parse_module(data, *, detail=False, arm_relocations=None):
    header,sections=parse_sections(data)
    info=next((row["bytes"] for row in sections if row["name"]==".modinfo"),None)
    need(info is not None,"No .modinfo section")
    meta=parse_modinfo(info)
    need(len(meta.get("vermagic",[]))==1 and len(meta.get("name",[]))==1,"Missing or ambiguous module name/vermagic")
    result=dict(header=header, sections=human_sections(sections), model=meta, build_ids=parse_build_ids(sections),
                signature=module_signature(data), module_release=meta["vermagic"][0].split()[0])
    if detail:
        tables=parse_symbols(sections)
        symbols=[s for syms in tables.values() for s in syms if s["identity"]]
        exports=sorted({s["name"].removeprefix("__ksymtab_") for s in symbols if s["name"].startswith("__ksymtab_")}|
            {s["name"].split("+",1)[1] for s in sections if s["name"].startswith("___ksymtab") and "+" in s["name"]})
        versions=parse_symbol_versions(sections)
        versions["export_crc_labels"]={s["name"].removeprefix("__crc_"):f'0x{s["value"]:08x}'
            for s in symbols if s["name"].startswith("__crc_") and s["section"]=="ABS"}
        result.update(symbols=symbols,exports=exports,versions=versions,
            relocations=parse_relocations(sections,tables,arm_relocations or {}))
    return result
