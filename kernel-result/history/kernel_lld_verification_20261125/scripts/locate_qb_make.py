#!/usr/bin/env python3
"""Find the host-architecture GNU Make companion from the new QB Base metadata."""
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parent.parent
e=root/"evidence"
base=e/"build/base"
raw=(base/"primary.xml.gz").read_bytes()
plain=gzip.decompress(raw)
entries=ET.parse(base/"repomd.out").getroot().findall("{*}data")
record=next(element for element in entries if element.get("type")=="primary")
for tag,content in (("checksum",raw),("open-checksum",plain)):
    n=record.find("{*}"+tag)
    if hashlib.new(n.get("type"),content).hexdigest()!=n.text:
        raise ValueError("Base metadata checksum mismatch")
tree=ET.fromstring(plain)
choices=[]
arm_sources=[]
for package in tree.findall("{*}package"):
    if package.findtext("{*}name")!="make" :
        continue
    version=package.find("{*}version")
    if version.get("ver")!="4.4.1":
        continue
    arch=package.findtext("{*}arch")
    if arch=="armv7l" and version.get("rel")=="1.14":
        arm_sources.append(version.get("vcs"))
    if arch!="x86_64":
        continue
    c=package.find("{*}checksum")
    choices.append(dict(nevra="make-4.4.1-"+version.get("rel")+".x86_64",source_revision=version.get("vcs"),algorithm=c.get("type"),checksum=c.text,
                        href=package.find("{*}location").get("href")))
if len(choices)!=1:
    raise SystemExit(f"expected one matching x86_64 make companion, found {len(choices)}")
row=choices[0]
if arm_sources!=[row["source_revision"]]:
    raise ValueError("companion Make source revision differs from the ARMv7l build dependency")
row["url"]="https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_20261030.120529/repos/standard/packages/"+row["href"]
row["provenance"]="companion architecture for model only; actual ARMv7l build log uses 4.4.1-1.14.armv7l"
(e/"reproduction/make-tool/selection.json").write_text(json.dumps(row,indent=2)+"\n")
print(row["url"])
