#!/usr/bin/env python3
"""Summarize the authorized device identity from untouched archived stdout."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"evidence/runtime"
NEW="tizen-unified-toolchain_20261125.130358"
OLD="tizen-unified-toolchain_20261120.082536"
HEX=re.compile(r"^(?:\s+[0-9a-f]{2})+\s*$")
SHA=re.compile(r"^([0-9a-f]{64})\s+(.+)$")

def read_notes(lines):
    original=next((SHA.fullmatch(line) for line in lines if SHA.fullmatch(line)),None)
    if original is None:
        return None
    blob=bytes.fromhex(" ".join(line for line in lines if HEX.fullmatch(line)))
    digest=hashlib.sha256(blob).hexdigest()
    if digest!=original.group(1):
        raise ValueError("device notes SHA256 differs from the recovered bytes")
    offset=0
    notes=[]
    while offset < len(blob):
        start=offset
        n,d,kind=struct.unpack_from("<III",blob,offset)
        offset+=12
        owner=blob[offset:offset+n].rstrip(b"\0").decode()
        offset+=(n+3)&~3
        desc=blob[offset:offset+d].hex()
        offset+=(d+3)&~3
        if offset>len(blob):
            raise ValueError("short ELF note")
        notes.append(dict(offset=start, owner=owner, type=kind, description=desc))
    return dict(sha256=digest,source_path=original.group(2),size=len(blob),
                build_id=next((n["description"] for n in notes if n["owner"]=="GNU" and n["type"]==3),None),
                raw_hex=blob.hex(),notes=notes)

def main():
    record=json.loads((E/"identity-device.cmd.json").read_text())
    sections={}
    current=None
    for line in (E/"identity-device.out").read_text().splitlines():
        if line.startswith("[") and re.fullmatch(r"\[[A-Z_]+\]",line):
            current=line[1:-1]
            sections[current]=[]
        elif current:
            sections[current].append(line)
    if record["exit_status"] or "END" not in sections:
        raise ValueError("complete device read unavailable")
    uname,release,arch=sections["UNAME"]
    information={k:v.strip('"') for k,v in (line.split("=",1) for line in sections["OS_RELEASE"] if "=" in line)}
    build=information["BUILD_ID"]
    observed_old=build.startswith(OLD+"_")
    observed_new=build.startswith(NEW+"_")
    status="PENDING_NEW_IMAGE_DEPLOYMENT" if observed_old else (
        "NEW_QB_OBSERVED_RUNTIME_NOT_YET_VERIFIED" if observed_new else "PENDING_DEVICE_IDENTITY"
    )
    kernel=read_notes(sections["KERNEL_NOTES"])
    note=read_notes(sections["KDBUS_NOTE"])
    modules=[dict(path=m.group(2),sha256=m.group(1)) for line in sections["KDBUS_FILES"] if (m:=SHA.fullmatch(line))]
    result=dict(
        status=status,serial="private-address-02:26101",image_build_id=build,requested_snapshot=NEW,
        observed_old_snapshot=observed_old,new_snapshot_verified=observed_new,uname=uname,release=release,arch=arch,
        model=sections["DEVICE_MODEL"][0],proc_version=sections["PROC_VERSION"][0],
        boot_banner=next((line for line in sections["BOOT_BANNER"] if "Linux version" in line),None),
        kernel=kernel,installed_kdbus=modules,loaded_kdbus=sections["KDBUS_LOADED"],loaded_kdbus_notes=note,
        device_capture="evidence/runtime/identity-device.out", command="evidence/runtime/identity-device.cmd.json",
        identity_probes_only=True, mutation_performed=False,
        diagnostics=[line for scope in ("BOOT_BANNER","LOCAL_ADDRESS") for line in sections[scope] if "error" in line or "not found" in line])
    (ROOT/"11H_RUNTIME_IDENTITY.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    (ROOT/"11H_RUNTIME_VERIFICATION.md").write_text(f'''# 11H · 设备运行验收

**RUNTIME_VALIDATION = {status}。** 使用当前已授权 SDB 会话只读识别了目标 Raspberry Pi 4。设备 IMAGE BUILD_ID 为 {build}，内核为 {release}，运行 banner 为 {result["proc_version"]}。本次设备运行证据属于所观察到的镜像。 [原始读数](evidence/runtime/identity-device.out) · [SDB 清单](evidence/runtime/sdb-list-after.out)

| 身份项 | 实测 |
| --- | --- |
| SDB serial | private-address-02:26101 |
| 架构和型号 | {arch} / {result["model"]} |
| 运行 Kernel GNU Build ID | {kernel["build_id"] if kernel else "不可得"} |
| 已安装 kdbus.ko SHA256 | {modules[0]["sha256"] if len(modules)==1 else "无唯一记录"} |
| 已加载 kdbus Build ID | {note["build_id"] if note else "不可得"} |

设备仍运行旧 QB 时，身份检查后即停止。本次旧设备文件和已加载模块仅用于确认部署状态。新 QB 的启动状态、模块加载及运行兼容性待确认。诊断中 ifconfig 不可用，SDB serial 和设备内 BUILD_ID、DT 型号及经 SHA256 核对的 notes 可用。dmesg 截取首条 banner 导致一条管道诊断，首条内容已保留。 [结构化身份](11H_RUNTIME_IDENTITY.json) · [命令及退出码](evidence/runtime/identity-device.cmd.json)
''')
    print(f"{status}: {build}, kernel GNU Build ID {kernel['build_id'] if kernel else None}")

if __name__=="__main__":
    main()
