#!/usr/bin/env python3
"""Exercise the six approved toolchain cases on Git candidate bytes using Phase 9 mocks."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
CHECKOUT=ROOT/"checkout"
ROUND3=ROOT.parent/"kernel_lld_verification_20261120/pm_review_round3"
REPRO=ROUND3/"reproducer"
OUT=ROOT/"evidence/make-validation"
TARGET="kernel/Makefile"
BASE="25797e8af7ed95a5783bbe84c11959560aaf7e92"
REMOVED=b"LD = $"+b"{CROSS_COMPILE}ld\n"
PREFIXES={"ARMv7l":"armv7l-tizen-linux-gnueabi-","AArch64":"aarch64-tizen-linux-gnu-"}
TRACE_FIELDS=("stage","makelevel","origin","flavor","raw_ld","effective_ld","llvm_origin","llvm",
              "cross_compile","makeflags","makeoverrides")
CASES=(
    ("armv7l-gcc-bfd","ARMv7l GCC + BFD","ARMv7l","","",PREFIXES["ARMv7l"]+"ld","GNU BFD"),
    ("armv7l-clang-llvm","ARMv7l Clang + LLVM=1","ARMv7l","1","","ld.lld","LLD"),
    ("aarch64-gcc-bfd","AArch64 GCC + BFD","AArch64","","",PREFIXES["AArch64"]+"ld","GNU BFD"),
    ("aarch64-clang-llvm","AArch64 Clang + LLVM=1","AArch64","1","","ld.lld","LLD"),
    ("explicit-ld-bfd","Explicit LD=ld.bfd","ARMv7l","1","ld.bfd","ld.bfd","GNU BFD"),
    ("explicit-ld-lld","Explicit LD=ld.lld","ARMv7l","1","ld.lld","ld.lld","LLD"),
)

def need(condition,message):
    if not condition:
        raise ValueError(message)

def file_sha(data):
    return hashlib.sha256(data).hexdigest()

def git(*args):
    return subprocess.run(["git","-C",str(CHECKOUT),*args],capture_output=True,check=True).stdout

def read_candidate():
    original=git("show",f"{BASE}:{TARGET}")
    candidate=(CHECKOUT/TARGET).read_bytes()
    submodule=(CHECKOUT/"kernel/kdbus/Makefile").read_bytes()
    need(original==(ROUND3/"evidence/source/external/Makefile").read_bytes(),"checkout base differs from verified source")
    need(submodule==(ROUND3/"evidence/source/external/kdbus/Makefile").read_bytes(),"kdbus sub-Makefile differs from verified source")
    need(original.count(REMOVED)==1 and candidate==original.replace(REMOVED,b"",1),"candidate is not exact approved deletion")
    return original,candidate,submodule

def test_case(case, temporary, make, env_base, candidate, submodule):
    stem,label,architecture,llvm,cli,expected,family=case
    base=temporary/stem
    external,kernel=base/"external",base/"kernel"
    (external/"kdbus").mkdir(parents=True)
    kernel.mkdir()
    (external/"Makefile").write_bytes(candidate)
    (external/"kdbus/Makefile").write_bytes(submodule)
    shutil.copy2(REPRO/"fixtures/Makefile",kernel/"Makefile")
    env=dict(env_base,ARCH="arm" if architecture=="ARMv7l" else "arm64",CROSS_COMPILE=PREFIXES[architecture])
    if llvm:
        env["LLVM"]=llvm
    command=[make,"--no-print-directory","-C",str(external),f"KERNELDIR={kernel}"]
    if cli:
        command.append("LD="+cli)
    command.append("all")
    proc=subprocess.run(command,env=env,capture_output=True,text=True,check=False,timeout=30)
    (OUT/(stem+".out")).write_text(proc.stdout)
    (OUT/(stem+".err")).write_text(proc.stderr)
    data=dict(argv=command,environment=env,exit_status=proc.returncode,candidate_makefile_sha256=file_sha(candidate))
    (OUT/(stem+".cmd.json")).write_text(json.dumps(data,indent=2)+"\n")
    need(proc.returncode==0,f"{stem}: make failed")
    stages={}
    mock_calls={}
    for line in proc.stdout.splitlines():
        if line.startswith("PHASE9_LD|"):
            row=dict(zip(TRACE_FIELDS,line.split("|")[1:],strict=True))
            need(row["stage"] not in stages,"duplicate Make observation")
            stages[row["stage"]]=row
        if line.startswith("PHASE9_MOCK|"):
            row=json.loads(line.partition("|")[2])
            need(row["stage"] not in mock_calls,"duplicate mock link")
            mock_calls[row["stage"]]=row
    need(len(stages)==7 and set(mock_calls)=={"intermediate","final"},f"{stem}: fixture scope mismatch")
    for stage in ("kbuild_top_selected","build_before_include","build_after_include","intermediate","final"):
        need(stages[stage]["effective_ld"]==expected,f"{stem}: unexpected {stage} linker")
    for stage,row in mock_calls.items():
        target="kdbus/kdbus.o" if stage=="intermediate" else "kdbus/kdbus.ko"
        argv=row["modeled_argv"]
        need(not row["actual_linker_executed"] and argv[0]==expected and argv[argv.index("-o")+1]==target,
             f"{stem}: selected compiler command or target mismatch")
    if cli:
        need(all(stages[stage]["origin"]=="command line" for stage in ("intermediate","final")),
             f"{stem}: lost command-line override")
    else:
        need(stages["intermediate"]["origin"]==stages["final"]["origin"]=="environment",
             f"{stem}: did not inherit the exported LD")
    return dict(case=stem,configuration=label,expected_family=family,expected_command=expected,
                intermediate_ld=stages["intermediate"]["effective_ld"],final_ld=stages["final"]["effective_ld"],
                intermediate_origin=stages["intermediate"]["origin"],final_origin=stages["final"]["origin"],
                actual_linker_executed=False,status="PASS")

def main():
    original,candidate,submodule=read_candidate()
    OUT.mkdir(parents=True,exist_ok=True)
    make=shutil.which("make")
    need(make is not None,"GNU Make unavailable")
    env={"PATH":os.pathsep.join((str(Path(make).parent),os.defpath)),"LC_ALL":"C",
         "PYTHONIOENCODING":"utf-8","BUILD_kdbus":"m","MAKEFLAGS":"-k","REPRO_DIR":str(REPRO),
         "REPRO_PYTHON":sys.executable}
    version=subprocess.run([make,"--version"],env=env,capture_output=True,text=True,check=True).stdout
    need(version.startswith("GNU Make"),"GNU Make unavailable")
    with tempfile.TemporaryDirectory(prefix=".phase10-make-",dir=ROOT) as folder:
        results=[test_case(case,Path(folder),make,env,candidate,submodule) for case in CASES]
    with (OUT/"results.csv").open("w",newline="") as report:
        writer=csv.DictWriter(report,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    (OUT/"summary.json").write_text(json.dumps(dict(status="PASS",real_build=False,
        model="Phase 9 fixtures on the exact Git candidate Makefile and kdbus sub-Makefile",
        GNU_make=version.splitlines()[0],base_sha256=file_sha(original),candidate_sha256=file_sha(candidate),
        kdbus_submake_sha256=file_sha(submodule),cases=results),indent=2)+"\n")
    for row in results:
        print(f'{row["status"]} {row["configuration"]}: {row["intermediate_ld"]} -> {row["final_ld"]}')

if __name__=="__main__":
    main()
