#!/usr/bin/env python3
"""Extract and compare old/new pinned QB ARMv7l non-RT module ELF files."""
import argparse
from collections import Counter, defaultdict
import csv
import datetime
import gzip
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time
import xml.etree.ElementTree as ET

from elf32_module import digest, need, parse_module, readelf_arm_names

ROOT=Path(__file__).resolve().parent.parent
OLD=ROOT.parent/"kernel_lld_verification_20261120"
E=ROOT/"evidence/binary"
REPO=ROOT/"evidence/repository"
MODULE_RE=re.compile(r"\.ko(?:\.(?:gz|xz|zst))?$")
NON_RT_RELEASE=re.compile(r"[^/]+-arm-rpi4-v7l")
RPM_EXPECTED={"arm-rpi4-linux-kernel-modules","linux-tizen-modules-rpi4"}
SDK_NAME="arm-rpi4-linux-kernel-devel"
SDK_MEMBER_ROOT="/boot/kernel/devel/kernel-devel-arm-rpi4/"
SELECTED_SECTIONS={".text",".rodata",".data",".bss",".init.text",".exit.text",".modinfo",".symtab",".strtab",
                   "__versions","__version_ext_crcs","__version_ext_names",".BTF",".BTF.base",".ARM.attributes"}

def release_path(path):
    parts=PurePosixPath(path).parts
    if len(parts)>=5 and parts[:3]==("/","lib","modules") and MODULE_RE.search(parts[-1]) and NON_RT_RELEASE.fullmatch(parts[3]):
        return parts[3]
    return None

def stable_name(path):
    parts=PurePosixPath(path).parts
    return "/".join(parts[4:])

def arm_path(path):
    return path if path.startswith("/") else "/"+path.removeprefix("./")

def safe_rel(path):
    candidate=PurePosixPath(path)
    need(not candidate.is_absolute() and candidate.parts and all(p not in ("..",".") for p in candidate.parts),
         f"Unexpected relative archive path {path}")
    return candidate

def rel_path(path):
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file,"sha256").hexdigest()

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")

def write_csv(path,rows,fields):
    with path.open("w",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)

def cmd(stem,argv,check=True):
    base=E/stem
    base.parent.mkdir(parents=True,exist_ok=True)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    clock=time.monotonic()
    actual=[str(arg) for arg in argv]
    result=subprocess.run(actual,cwd=ROOT,capture_output=True,check=False,timeout=120)
    Path(str(base)+".out").write_bytes(result.stdout)
    Path(str(base)+".err").write_bytes(result.stderr)
    write_json(Path(str(base)+".cmd.json"),dict(argv=actual,cwd=str(ROOT),started_utc=started,
        elapsed_seconds=round(time.monotonic()-clock,3),exit_status=result.returncode))
    if check:
        result.check_returncode()
    return result

def xml_package_rows(path):
    with gzip.open(path,"rb") as stream:
        for _,elem in ET.iterparse(stream,events=("end",)):
            if elem.tag.endswith("}package"):
                yield elem
                elem.clear()

def verify_metadata():
    repomd=ET.parse(REPO/"packages-repomd.out").getroot()
    checks={}
    for kind in ("filelists","primary"):
        node=next(elem for elem in repomd.findall("{*}data") if elem.attrib["type"]==kind)
        item=REPO/f"packages-{kind}.out"
        expected=node.find("{*}checksum")
        need(expected.attrib["type"]=="sha256" and sha(item)==expected.text,
             f"Compressed metadata digest mismatch ({kind})")
        uncompressed_expected=node.find("{*}open-checksum")
        with gzip.open(item,"rb") as f:
            opened=hashlib.file_digest(f,"sha256").hexdigest()
        need(uncompressed_expected.attrib["type"]=="sha256" and opened==uncompressed_expected.text,
             f"Open metadata digest mismatch ({kind})")
        checks[kind]=dict(file=rel_path(item),compressed_sha256=expected.text,open_sha256=opened)
    return checks

def new_inventory_metadata():
    selected={}
    for pkg in xml_package_rows(REPO/"packages-filelists.out"):
        if pkg.attrib.get("arch")!="armv7l":
            continue
        paths=[f.text for f in pkg.findall("{*}file") if f.text and release_path(f.text)]
        if paths:
            selected[pkg.attrib["pkgid"]]=dict(name=pkg.attrib["name"],paths=paths)
    need(selected,"No ARMv7l non-RT RPi4 module carrier in package filelists")
    need(set(v["name"] for v in selected.values())==RPM_EXPECTED,f"Unexpected module carriers: {selected}")
    need(len(selected)==len(RPM_EXPECTED),"Multiple candidate versions found in the pinned package filelists")
    for pkg in xml_package_rows(REPO/"packages-primary.out"):
        checksum=pkg.find("{*}checksum")
        if checksum is None or checksum.text not in selected:
            continue
        need(checksum.attrib["type"]=="sha256","RPM metadata checksum is not SHA256")
        row=selected[checksum.text]
        version=pkg.find("{*}version").attrib
        row.update(location=pkg.find("{*}location").attrib["href"],
                   version=version["ver"],release=version["rel"],epoch=version["epoch"],
                   arch=pkg.findtext("{*}arch"),sha256=checksum.text)
    need(all("location" in row for row in selected.values()),"Filelists candidate absent in primary")
    releases={release_path(path) for row in selected.values() for path in row["paths"]}
    need(len(releases)==1,f"Ambiguous target kernel releases: {releases}")
    return next(iter(releases)), selected

def new_sdk_digests():
    candidates=[(pkg.find("{*}checksum"),pkg.find("{*}location").attrib["href"])
                for pkg in xml_package_rows(REPO/"packages-primary.out")
                if pkg.findtext("{*}name")==SDK_NAME and pkg.findtext("{*}arch")=="armv7l"]
    need(len(candidates)==1,"Expected exactly one matching new RPi4 development RPM")
    checksum,location=candidates[0]
    path=REPO/"rpms"/Path(location).name
    need(checksum.attrib["type"]=="sha256" and sha(path)==checksum.text,"New SDK RPM checksum mismatch")
    result=cmd("rpm/new-sdk-digests",["rpm","-qp","--qf",'[%{FILENAMES}\t%{FILEDIGESTS}\n]',path])
    return path,checksum.text,dict(line.split("\t",1) for line in result.stdout.decode().splitlines())

def iter_cpio(data):
    pos=0
    linked={}
    for _ in range(len(data)//110+1):
        header=data[pos:pos+110]
        need(len(header)==110 and header[:6] in (b"070701",b"070702"),"Malformed RPM cpio header")
        values=[int(header[6+i*8:14+i*8],16) for i in range(13)]
        inode,mode,_,_,nlink,_,size,devmaj,devmin,_,_,namesize,checksum=values
        first=pos+110
        filename=data[first:first+namesize]
        need(filename.endswith(b"\0"),"Malformed RPM cpio filename")
        name=filename[:-1].decode("utf-8")
        if name=="TRAILER!!!":
            return
        pos=(first+namesize+3)&~3
        payload=data[pos:pos+size]
        need(len(payload)==size,"Short RPM cpio payload")
        if header[:6]==b"070702":
            need(sum(payload)&0xffffffff==checksum,"Invalid RPM cpio CRC")
        key=(devmaj,devmin,inode)
        if payload and stat.S_ISREG(mode) and nlink>1:
            linked[key]=payload
        yield name,mode,payload,key if nlink>1 else None,linked
        pos=(pos+size+3)&~3
    raise ValueError("Missing RPM cpio trailer")

def extract_new(packages):
    inventory={}
    for checksum,row in sorted(packages.items(),key=lambda item:item[1]["name"]):
        path=REPO/"rpms"/Path(row["location"]).name
        need(path.is_file() and sha(path)==checksum,f"Missing or metadata checksum mismatch: {path}")
        header=cmd(f'rpm/{row["name"]}-digests',["rpm","-qp","--qf",'[%{FILENAMES}\t%{FILEDIGESTS}\n]',path]).stdout.decode()
        digests=dict(line.split("\t",1) for line in header.splitlines())
        cpio=cmd(f'rpm/{row["name"]}-cpio',["rpm2cpio",path]).stdout
        matches={}
        for arcname,mode,payload,inode,linked in iter_cpio(cpio):
            filename=arm_path(arcname)
            if not release_path(filename):
                continue
            need(filename not in matches and stat.S_ISREG(mode),f"Duplicate or non-regular .ko payload {filename}")
            matches[filename]=(payload,inode,linked)
        need(set(matches)==set(row["paths"]),f"cpio/filelists coverage mismatch: {row['name']}")
        for filename,(payload,inode,linked) in sorted(matches.items()):
            payload=payload or (linked.get(inode,b"") if inode is not None else b"")
            need(payload and digests.get(filename)==digest(payload),f"RPM file digest mismatch: {filename}")
            target=E/"modules/new"/safe_rel(filename.removeprefix("/"))
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(payload)
            key=stable_name(filename)
            need(key not in inventory,f"Multiple module carriers at {filename}")
            inventory[key]=dict(path=filename,file=rel_path(target),sha256=digest(payload),rpm=path.name,ignored=False)
        row["downloaded_path"]=rel_path(path)
    return inventory

def read_old():
    result={}
    with (OLD/"05_kernel_module_inventory.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["scope"]!="repository" or not release_path(row["path"]):
                continue
            file=OLD/row["file"]
            need(sha(file)==row["raw_sha256"],f"Old archived module checksum mismatch {row['path']}")
            key=stable_name(row["path"])
            need(key not in result,f"Duplicate old module path: {key}")
            result[key]=dict(path=row["path"],file=str(file),sha256=row["raw_sha256"],rpm=row["rpm"]+".rpm",
                             historic_old_coverage=row["classification"])
    need(result,"Old archive inventory is empty")
    return result

def uncompress(file,label):
    data=file.read_bytes()
    if file.suffix==".gz":
        return gzip.decompress(data)
    if file.suffix==".xz":
        return lzma.decompress(data)
    if file.suffix==".zst":
        return cmd(f"zstd/{label}",["zstd","-cd","--",file]).stdout
    return data

def arm_attributes(output):
    return dict(re.findall(r"^\s*(Tag_\w+):\s*(.*?)\s*$",output,re.M))

def inspect(side,key,row,detail):
    original=ROOT/row["file"]
    label=side+"/"+key
    try:
        data=uncompress(original,label)
        parsed_path=original
        if data!=original.read_bytes():
            parsed_path=E/"decompressed"/safe_rel(label.replace(".ko.gz",".ko").replace(".ko.xz",".ko").replace(".ko.zst",".ko"))
            parsed_path.parent.mkdir(parents=True,exist_ok=True)
            parsed_path.write_bytes(data)
        args=["readelf","-W","-h","-n","-A","-S","-p",".modinfo"]
        if detail:
            args+=["-s","-r","-p",".comment"]
        evidence=cmd("readelf/"+label,args+[parsed_path]).stdout.decode(errors="backslashreplace")
        parsed=parse_module(data,detail=detail,arm_relocations=readelf_arm_names(evidence))
        need("ELF32" in evidence and "ARM" in evidence and "Relocatable file" in evidence,"GNU readelf header agreement failed")
        need(parsed["module_release"]==release_path(row["path"]),f'Filelists path differs from vermagic: {row["path"]}')
        for buildid in parsed["build_ids"]:
            need(f"Build ID: {buildid}" in evidence,"Build ID readelf disagreement")
        parsed.update(arm_attributes=arm_attributes(evidence),elf_size=len(data),elf_sha256=digest(data),
                      artifact_size=original.stat().st_size,artifact_sha256=row["sha256"],
                      readelf=rel_path(E/"readelf"/(label+".out")),parse_status="PASS",artifact=rel_path(original))
        if detail:
            for section in ("__versions","__version_ext_crcs","__version_ext_names"):
                if any(s["name"]==section for s in parsed["sections"]):
                    cmd("readelf-versions/"+label+"."+section,["readelf","-W","-x",section,parsed_path])
        return parsed
    except (ValueError, OSError, subprocess.SubprocessError, IndexError, KeyError) as exc:
        return dict(parse_status="FAIL",error=str(exc),artifact=rel_path(original))

def module_group(key):
    return "out-of-tree" if key.startswith("extra/") else "in-tree"

def short_model(parsed):
    if not parsed or parsed["parse_status"]!="PASS":
        return parsed
    return {k:v for k,v in parsed.items() if k not in ("sections","symbols","relocations")}

def compare_sections(name,a,b):
    old={(r["name"],r["occurrence"]):r for r in a["sections"]}
    new={(r["name"],r["occurrence"]):r for r in b["sections"]}
    values=[]
    for key in sorted(old.keys()|new.keys()|{(n,1) for n in SELECTED_SECTIONS}):
        p,q=old.get(key,{}),new.get(key,{})
        sizep,sizeq=p.get("size"),q.get("size")
        offp,offq=p.get("offset"),q.get("offset")
        status="ABSENT_BOTH" if not p and not q else "ADDED" if not p else "REMOVED" if not q else (
            "SIZE_CHANGED" if sizep!=sizeq else "CONTENT_CHANGED" if p["content_sha256"]!=q["content_sha256"]
            else "ATTRIBUTES_CHANGED" if (p["alignment"],p["flags"],p["type"])!=(q["alignment"],q["flags"],q["type"])
            else "LAYOUT_ONLY" if offp!=offq else "UNCHANGED")
        values.append(dict(module=name,record="SECTION",section=key[0],occurrence=key[1],old_present=bool(p),new_present=bool(q),
            old_bytes=sizep,new_bytes=sizeq,delta_bytes=(sizeq or 0)-(sizep or 0),old_offset=offp,new_offset=offq,
            old_file_bytes=p.get("file_size"),new_file_bytes=q.get("file_size"),
            old_sha256=p.get("content_sha256"),new_sha256=q.get("content_sha256"),status=status))
    return values

def canonical_json(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True)

def symbol_groups(data):
    groups=defaultdict(list)
    for s in data["symbols"]:
        attrs=("table","name","section","type","binding","visibility","size","value","defined","other")
        groups[s["identity"]].append({key:s[key] for key in attrs})
    return {name:sorted(rows,key=canonical_json) for name,rows in groups.items()}

def symbol_attrs(rows,remove):
    return sorted(canonical_json({k:v for k,v in row.items() if k not in remove}) for row in rows)

def compare_symbols(name,a,b):
    left,right=symbol_groups(a),symbol_groups(b)
    values=[]
    for key in sorted(left.keys()|right.keys()):
        p,q=left.get(key,[]),right.get(key,[])
        if p==q:
            continue
        category="ADDED" if not p else "REMOVED" if not q else (
            "VALUE_LAYOUT_ONLY" if symbol_attrs(p,{"value"})==symbol_attrs(q,{"value"})
            else "SIZE_OR_VALUE_CHANGED" if symbol_attrs(p,{"value","size"})==symbol_attrs(q,{"value","size"})
            else "ATTRIBUTES_OR_MULTIPLICITY_CHANGED")
        values.append(dict(module=name,symbol=key,difference=category,old_count=len(p),new_count=len(q),
            old_attributes=canonical_json(p),new_attributes=canonical_json(q)))
    for kind,key in (("IMPORT_MODVERSION_CRC","imports"),("EXPORT_CRC_LABEL","export_crc_labels")):
        old,new=a["versions"][key],b["versions"][key]
        for symbol in sorted(old.keys()|new.keys()):
            if old.get(symbol)!=new.get(symbol):
                values.append(dict(module=name,symbol=symbol,difference=kind,
                    old_count=int(symbol in old),new_count=int(symbol in new),
                    old_attributes=old.get(symbol),new_attributes=new.get(symbol)))
    for symbol in sorted(set(a["exports"])^set(b["exports"])):
        values.append(dict(module=name,symbol=symbol,difference="KERNEL_EXPORT_MARKER_CHANGED",
                    old_count=int(symbol in a["exports"]),new_count=int(symbol in b["exports"]),
                    old_attributes="",new_attributes=""))
    return values

def reloc_groups(parsed):
    groups=defaultdict(list)
    for r in parsed["relocations"]:
        key=tuple(r[f] for f in ("relocation_section","origin_section","type","type_id","target_symbol","target_section","target_binding","target_defined"))
        groups[key].append((r["offset"],r["addend"],r["target_value"]))
    return {key:sorted(values,key=canonical_json) for key,values in groups.items()}

def compare_relocs(name,a,b):
    old,new=reloc_groups(a),reloc_groups(b)
    rows=[]
    for k in sorted(old.keys()|new.keys()):
        p,q=old.get(k,[]),new.get(k,[])
        if p==q:
            continue
        sec,origin,typ,kind,symbol,target_sec,bind,defined=k
        rows.append(dict(module=name,relocation_section=sec,origin_section=origin,relocation_type=typ,
            relocation_type_id=kind,target_symbol=symbol,target_section=target_sec,target_binding=bind,
            target_defined=defined,old_count=len(p),new_count=len(q),delta_count=len(q)-len(p),
            old_sites_and_target_values=canonical_json(p),new_sites_and_target_values=canonical_json(q),
            difference="TARGET_GROUP_ADDED" if not p else "TARGET_GROUP_REMOVED" if not q else
                "COUNT_CHANGED" if len(p)!=len(q) else "SITE_OR_TARGET_VALUE_CHANGED"))
    return rows

def imports(parsed):
    return sorted({(s["name"],s["type"],s["binding"],s["visibility"]) for s in parsed["symbols"] if not s["defined"] and s["name"]})

def defined_interface(parsed):
    return sorted({(s["name"],s["type"],s["binding"],s["visibility"],s["size"])
                   for s in parsed["symbols"] if s["defined"] and s["binding"] in ("GLOBAL","WEAK") and s["name"]})

def symvers(path):
    symbols=defaultdict(list)
    for line in path.read_text().splitlines():
        parts=line.split()
        if len(parts)<3:
            continue
        crc,name,kind=parts[:3]
        symbols[name].append(dict(crc=crc.lower(),origin=kind))
    return symbols

def import_crc_check(parsed, available, same_batch_labels):
    core=parsed["versions"]["imports"]
    results={}
    for name,crc in core.items():
        providers=available.get(name,[])
        if not providers:
            providers=same_batch_labels.get(name,[])
        results[name]=dict(expected=crc,providers=providers,result=
            "MATCH" if any(repr_["crc"]==crc for repr_ in providers) else
            "CRC_MISMATCH" if providers else "NO_VERIFIABLE_EXPORT_CRC")
    summary=Counter(r["result"] for r in results.values())
    return dict(imported_crc_count=len(core),summary=dict(summary),per_symbol=results)

def module_diff_summary(key,a,b,sections,symbols,relocs,old_symvers,new_symvers,batch_old,batch_new):
    headers=("elf_class","machine","endianness","type","elf_flags","arm_eabi_version","arm_float_abi")
    metadata_changed={k:dict(old=a["model"].get(k),new=b["model"].get(k))
                      for k in sorted(a["model"].keys()|b["model"].keys()) if a["model"].get(k)!=b["model"].get(k)}
    lcrc,rcrc=a["versions"]["imports"],b["versions"]["imports"]
    changed=[n for n in sorted(lcrc.keys()&rcrc.keys()) if lcrc[n]!=rcrc[n]]
    imports_a,imports_b=set(imports(a)),set(imports(b))
    a_relocs,b_relocs=Counter(r["type"] for r in a["relocations"]),Counter(r["type"] for r in b["relocations"])
    old_public,new_public=set(defined_interface(a)),set(defined_interface(b))
    origin_names={r["origin_section"] for d in (a,b) for r in d["relocations"]}
    origin_changes=[s["section"] for s in sections if s["section"] in origin_names and
                    (s["old_sha256"],s["old_bytes"])!=(s["new_sha256"],s["new_bytes"])]
    arm_a,arm_b=a["arm_attributes"],b["arm_attributes"]
    arm_deltas={k:{"old":arm_a.get(k),"new":arm_b.get(k)} for k in sorted(arm_a.keys()|arm_b.keys())
                if arm_a.get(k)!=arm_b.get(k)}
    return dict(path=key,module=b["model"]["name"][0],old=short_model(a),new=short_model(b),
        basic_header_equal=all(a["header"][k]==b["header"][k] for k in headers),
        arm_attributes_equal=not arm_deltas,arm_attribute_encoding_deltas=arm_deltas,
        module_release_equal=a["module_release"]==b["module_release"],
        vermagic_equal=a["model"]["vermagic"]==b["model"]["vermagic"],metadata_changed=metadata_changed,
        old_file_size=a["artifact_size"],new_file_size=b["artifact_size"],file_size_delta=b["artifact_size"]-a["artifact_size"],
        section_status_counts=dict(Counter(s["status"] for s in sections)),
        symbol_delta_status_counts=dict(Counter(s["difference"] for s in symbols)),
        old_symbol_counts=dict(Counter(("defined" if s["defined"] else "undefined")+"_"+s["binding"] for s in a["symbols"])),
        new_symbol_counts=dict(Counter(("defined" if s["defined"] else "undefined")+"_"+s["binding"] for s in b["symbols"])),
        imports_added=sorted(imports_b-imports_a),imports_removed=sorted(imports_a-imports_b),
        defined_global_weak_shapes_added=sorted(new_public-old_public),defined_global_weak_shapes_removed=sorted(old_public-new_public),
        old_exports=a["exports"],new_exports=b["exports"],kernel_exports_equal=a["exports"]==b["exports"],
        import_crc_changes={n:{"old":lcrc[n],"new":rcrc[n]} for n in changed},crc_imports_added=sorted(rcrc.keys()-lcrc.keys()),
        crc_imports_removed=sorted(lcrc.keys()-rcrc.keys()),crc_record_order_equal=list(lcrc)==list(rcrc),
        relocation_origins=sorted(origin_names),relocation_origin_payload_changes=origin_changes,
        signatures_equal=a["signature"]==b["signature"],old_reloc_total=len(a["relocations"]),new_reloc_total=len(b["relocations"]),
        old_reloc_by_type=dict(a_relocs),new_reloc_by_type=dict(b_relocs),new_reloc_types=sorted(b_relocs.keys()-a_relocs.keys()),
        removed_reloc_types=sorted(a_relocs.keys()-b_relocs.keys()),relocation_diff_rows=len(relocs),
        old_import_crc_validation=import_crc_check(a,old_symvers,batch_old),
        new_import_crc_validation=import_crc_check(b,new_symvers,batch_new))

def batch_exports(details):
    out=defaultdict(list)
    for key,d in details.items():
        for symbol,crc in d.get("versions",{}).get("export_crc_labels",{}).items():
            if symbol in d["exports"]:
                out[symbol].append(dict(crc=crc,origin=key))
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-symvers",type=Path,required=True)
    parser.add_argument("--old-symvers",type=Path,default=E/"old-sdk/Module.symvers.out")
    args=parser.parse_args()
    checks=verify_metadata()
    release,selected=new_inventory_metadata()
    new=extract_new(selected)
    old=read_old()
    in_scope=old.keys()|new.keys()
    details_old={key:inspect("old",key,row,True) for key,row in old.items() if module_group(key)=="out-of-tree"}
    details_new={key:inspect("new",key,row,module_group(key)=="out-of-tree") for key,row in new.items()}
    allrows=[]
    for key in sorted(in_scope):
        left,right=old.get(key),new.get(key)
        parsed=details_new.get(key,{})
        status="ADDED" if not left else "REMOVED" if not right else "IDENTICAL" if left["sha256"]==right["sha256"] else "CHANGED"
        allrows.append(dict(module_path=key,module_group=module_group(key),status=status,old_present=bool(left),new_present=bool(right),
            old_rpm=left["rpm"] if left else "",new_rpm=right["rpm"] if right else "",
            old_sha256=left["sha256"] if left else "",new_sha256=right["sha256"] if right else "",
            new_parse_status=parsed.get("parse_status","N/A"),new_vermagic=(parsed.get("model",{}).get("vermagic") or [""])[0],
            new_build_id=";".join(parsed.get("build_ids",[])),new_source_artifact=parsed.get("artifact",""),
            new_readelf=parsed.get("readelf",""),new_parse_error=parsed.get("error","")))
    fields=["module_path","module_group","status","old_present","new_present","old_rpm","new_rpm","old_sha256","new_sha256",
            "new_parse_status","new_vermagic","new_build_id","new_source_artifact","new_readelf","new_parse_error"]
    write_csv(ROOT/"11G_MODULE_INVENTORY_DIFF.csv",allrows,fields)
    write_json(E/"module-inventory-metadata.json",dict(checks=checks,selected=selected,release=release,
                                                       old=old,new=new,new_checks={k:short_model(v) for k,v in details_new.items()}))
    paths=dict(line.split("\t",1) for line in (E/"old-sdk/rpm-filedigests.out").read_text().splitlines())
    old_name=SDK_MEMBER_ROOT+"Module.symvers"
    need(sha(args.old_symvers)==paths[old_name],"Old Module.symvers does not match its sealed SDK RPM")
    new_sdk,new_sdk_sha,new_digests=new_sdk_digests()
    need(sha(args.new_symvers)==new_digests[old_name],"New Module.symvers does not match its sealed SDK RPM")
    old_kernel,new_kernel=symvers(args.old_symvers),symvers(args.new_symvers)
    need(old_kernel and new_kernel,"Missing usable verified SDK symbol version map")
    checked_sdk_rows=dict(old={"path":rel_path(args.old_symvers),"sha256":sha(args.old_symvers),"export_names":len(old_kernel)},
                          new={"path":rel_path(args.new_symvers),"sha256":sha(args.new_symvers),"export_names":len(new_kernel),
                               "provider_rpm":rel_path(new_sdk),"provider_rpm_sha256":new_sdk_sha})
    write_json(E/"sdk-symvers-inputs.json",checked_sdk_rows)
    section_rows,symbol_rows,reloc_rows=[],[],[]
    comparison={}
    failures={}
    exports_a,exports_b=batch_exports(details_old),batch_exports(details_new)
    for name in sorted(set(details_old)|{key for key in details_new if module_group(key)=="out-of-tree"}):
        a,b=details_old.get(name),details_new.get(name)
        if not a or not b or a["parse_status"]!="PASS" or b["parse_status"]!="PASS":
            failures[name]={"old":short_model(a),"new":short_model(b)}
            continue
        sections=compare_sections(name,a,b)
        sections.insert(0,dict(module=name,record="FILE",section="",occurrence="",old_present=True,new_present=True,
             old_bytes=a["artifact_size"],new_bytes=b["artifact_size"],delta_bytes=b["artifact_size"]-a["artifact_size"],
             old_offset=None,new_offset=None,old_file_bytes=a["artifact_size"],new_file_bytes=b["artifact_size"],
             old_sha256=a["artifact_sha256"],new_sha256=b["artifact_sha256"],status=
             "IDENTICAL" if a["artifact_sha256"]==b["artifact_sha256"] else "CONTENT_CHANGED"))
        symbols=compare_symbols(name,a,b)
        relocations=compare_relocs(name,a,b)
        section_rows.extend(sections)
        symbol_rows.extend(symbols)
        reloc_rows.extend(relocations)
        comparison[name]=module_diff_summary(name,a,b,sections,symbols,relocations,old_kernel,new_kernel,exports_a,exports_b)
        for side,detail in (("old",a),("new",b)):
            write_json(E/"parsed"/side/(name+".json"),detail)
    write_csv(ROOT/"11F_MODULE_SIZE_COMPARISON.csv",section_rows,list(section_rows[0].keys()) if section_rows else
              ["module","record","section","occurrence","old_present","new_present","old_bytes","new_bytes","delta_bytes",
               "old_offset","new_offset","old_file_bytes","new_file_bytes","old_sha256","new_sha256","status"])
    write_csv(ROOT/"11F_MODULE_SYMBOL_DIFF.csv",symbol_rows,["module","symbol","difference","old_count","new_count","old_attributes","new_attributes"])
    write_csv(ROOT/"11F_MODULE_RELOCATION_DIFF.csv",reloc_rows,
            ["module","relocation_section","origin_section","relocation_type","relocation_type_id","target_symbol",
             "target_section","target_binding","target_defined","old_count","new_count","delta_count",
             "old_sites_and_target_values","new_sites_and_target_values","difference"])
    counts=dict(old=dict(Counter(module_group(k) for k in old)),new=dict(Counter(module_group(k) for k in new)),
                old_total=len(old),new_total=len(new),new_parsed=sum(v["parse_status"]=="PASS" for v in details_new.values()),
                old_new_payload_status=dict(Counter(r["status"] for r in allrows)))
    summary=dict(status="MEASURED_PENDING_REVIEW",comparison_scope="Pinned ARMv7l non-RT RPi4; release-path-independent canonical module names",
                 new_release=release,counts=counts,packaged_module_rpms=list(selected.values()),sdk_symvers_inputs=checked_sdk_rows,
                 modules=comparison,failures=failures,
                 new_parser_failures={k:v for k,v in details_new.items() if v["parse_status"]!="PASS"},
                 limits=["Static comparison only. No new module load or runtime compatibility inference.",
                         "ARM REL implicit addends are not decoded. Exact relocation sites and resolved symbol identities are listed.",
                         "Linux appended module signatures, when present, are identified but not cryptographically validated."])
    write_json(ROOT/"11F_MODULE_ABI_SUMMARY.json",summary)
    print(json.dumps(dict(counts=counts,examined=len(comparison),failures=failures,
        section_rows=len(section_rows),symbol_rows=len(symbol_rows),relocation_rows=len(reloc_rows)),indent=2))

if __name__=="__main__":
    main()
