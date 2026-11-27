#!/usr/bin/env python3
"""Compare the two exact QB Makefile payloads using the Phase 9 process graph."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/"evidence/reproduction"
FIX=E/"phase9-fixture"
OLD="20261120.082536"
NEW="20261125.130358"

def need(value,message):
    if not value:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load_phase9():
    spec=importlib.util.spec_from_file_location("phase9_model",FIX/"run.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def bind_kbuild(path):
    checks={
        "Makefile": (r"ifneq \(\$\(LLVM\),\)",r"^\s*LD\s*=\s*\$\(LLVM_PREFIX\)ld\.lld\$\(LLVM_SUFFIX\)",
                     r"^\s*LD\s*=\s*\$\(CROSS_COMPILE\)ld\s*$",r"^export.*\bCROSS_COMPILE LD CC\b",
                     r"\$\(MAKE\) -f \$\(srctree\)/scripts/Makefile\.modfinal"),
        "scripts/Makefile.build":(r"^include \$\(kbuild-file\)",r"cmd_ld_multi_m = \$\(LD\).*-r",
                                  r"\$\(MAKE\) \$\(build\)=\$@"),
        "scripts/Makefile.modfinal":(r"\$\(LD\) -r",r"^%.ko: %.o",),
    }
    matched={}
    for name,expressions in checks.items():
        data=(path/name).read_bytes()
        rows=data.decode().splitlines()
        anchors={}
        for expr in expressions:
            result=[dict(line=i,line_text=line) for i,line in enumerate(rows,1) if re.search(expr,line)]
            need(result,f"matched Kbuild rule is absent: {path/name} ({expr})")
            anchors[expr]=result
        matched[name]=dict(path=str((path/name).relative_to(ROOT)),sha256=sha(data),anchors=anchors)
    return matched

def describe_inputs(label,wrapper,kdbus):
    local=E/"inputs"/label
    local.mkdir(parents=True,exist_ok=True)
    data={}
    for name,source in (("Makefile",wrapper),("kdbus.Makefile",kdbus)):
        raw=source.read_bytes()
        out=local/name
        out.write_bytes(raw)
        data[name]=dict(path=str(out.relative_to(ROOT)),source_location=str(source),sha256=sha(raw))
    return data

def expected(llvm,cross,env_ld,cli,use_e,override):
    fallback=(llvm+"ld.lld" if llvm.endswith("/") else "ld.lld"+llvm if llvm.startswith("-")
              else "ld.lld" if llvm else cross+"ld")
    top=cli or (env_ld if use_e and env_ld else fallback)
    # The current known external assignment is a plain makefile assignment.
    merge=cross+"ld" if override and not cli and not (use_e and env_ld) else top
    return merge,top

def run_case(model,case,label,input_paths,make,root,env_base):
    name,variant,llvm,cross,env_ld,cli,use_e,*_=case
    case_root=root/label/name
    external,kernel=case_root/"external",case_root/"kernel"
    (external/"kdbus").mkdir(parents=True)
    kernel.mkdir()
    for target,key in ((external/"Makefile","Makefile"),(external/"kdbus/Makefile","kdbus.Makefile")):
        actual=(ROOT/input_paths[key]["path"]).read_bytes()
        need(sha(actual)==input_paths[key]["sha256"],"experiment input copy has changed")
        target.write_bytes(actual)
    shutil.copy2(FIX/"fixtures/Makefile",kernel/"Makefile")
    env=dict(env_base,MAKEFLAGS="-ek" if use_e else "-k")
    for key,value in (("LLVM",llvm),("CROSS_COMPILE",cross),("LD",env_ld)):
        if value:
            env[key]=value
    argv=[str(make),"--no-print-directory","-C",str(external),f"KERNELDIR={kernel}"]
    if cli:
        argv.append("LD="+cli)
    argv.append("all")
    proc=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=30)
    raw=E/"runs"/label
    raw.mkdir(parents=True,exist_ok=True)
    (raw/(name+".out")).write_text(proc.stdout)
    (raw/(name+".err")).write_text(proc.stderr)
    (raw/(name+".cmd.json")).write_text(json.dumps(dict(argv=argv,env=env,exit_status=proc.returncode,
                        input_payload_sha256=input_paths["Makefile"]["sha256"]),indent=2)+"\n")
    need(proc.returncode==0,f"{label}/{name} isolated make failed")
    trace={}
    calls={}
    for line in proc.stdout.splitlines():
        if line.startswith("PHASE9_LD|"):
            row=dict(zip(model.TRACE_FIELDS,line.split("|")[1:],strict=True))
            need(row["stage"] not in trace,"duplicate trace")
            trace[row["stage"]]=row
        if line.startswith("PHASE9_MOCK|"):
            call=json.loads(line.partition("|")[2])
            need(call["stage"] not in calls,"duplicate mock call")
            calls[call["stage"]]=call
    need(tuple(trace)==model.TRACE_STAGES and set(calls)=={"intermediate","final"},"model stages changed")
    original=(external/"Makefile").read_text()
    prefixed=original.count(model.ORIGINAL)
    need(prefixed<=1,"ambiguous external Makefile assignment")
    one,two=expected(llvm,cross,env_ld,cli,use_e,prefixed==1)
    for phase,want,target in (("intermediate",one,"kdbus/kdbus.o"),("final",two,"kdbus/kdbus.ko")):
        proof=calls[phase]
        need(trace[phase]["effective_ld"]==proof["modeled_argv"][0]==want and not proof["actual_linker_executed"]
             and proof["modeled_argv"][proof["modeled_argv"].index("-o")+1]==target,
             f"{label}/{name} wrong {phase} modeled command")
    return dict(case=name,round3_variant_label=variant,snapshot=label,observed_argv=calls,trace=trace,
                llvm=llvm,cross_compile=cross,env_ld=env_ld,cli_ld=cli,make_e=use_e,intermediate=one,final=two,status="PASS")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-makefile",type=Path,required=True)
    parser.add_argument("--old-kdbus",type=Path,required=True)
    parser.add_argument("--new-makefile",type=Path,required=True)
    parser.add_argument("--new-kdbus",type=Path,required=True)
    parser.add_argument("--new-kbuild",type=Path,required=True)
    parser.add_argument("--make",type=Path,required=True)
    args=parser.parse_args()
    model=load_phase9()
    original=describe_inputs(OLD,args.old_makefile.resolve(),args.old_kdbus.resolve())
    candidate=describe_inputs(NEW,args.new_makefile.resolve(),args.new_kdbus.resolve())
    snapshot_inputs={OLD:original,NEW:candidate}
    old=(ROOT/original["Makefile"]["path"]).read_bytes()
    new=(ROOT/candidate["Makefile"]["path"]).read_bytes()
    need(old.count(model.ORIGINAL.encode())==1,"old payload does not have the exact historical LD assignment")
    need(new==old.replace(model.ORIGINAL.encode(),b"",1),"actual new wrapper differs beyond the scoped deletion")
    need(original["kdbus.Makefile"]["sha256"]==candidate["kdbus.Makefile"]["sha256"],"kdbus recursive Makefile changed")
    make=args.make.resolve()
    env={"PATH":os.pathsep.join([str(make.parent),os.defpath]),"LC_ALL":"C","PYTHONIOENCODING":"utf-8",
         "REPRO_DIR":str(FIX),"REPRO_PYTHON":sys.executable,"BUILD_kdbus":"m"}
    version=subprocess.run([str(make),"--version"],env=env,capture_output=True,text=True,check=True).stdout.splitlines()[0]
    need(make.name=="make" and version.startswith("GNU Make"),"selected tool is not GNU Make named make")
    kbuild=bind_kbuild(args.new_kbuild.resolve())
    cases=model.CASES+(
        ("llvm_directory_prefix","actual-payload","/opt/tizen-llvm/bin/",model.ARM,"","",False),
        ("explicit_bfd_unprefixed","actual-payload","1",model.ARM,"","ld.bfd",False),
    )
    need(len(model.CASES)==21,"21 original Phase 9 flag shapes unavailable")
    with tempfile.TemporaryDirectory(prefix=".qb-linker-model-",dir=ROOT) as scratch:
        temp=Path(scratch)
        runs=[run_case(model,case,snapshot,paths,make,temp,env)
              for case in cases for snapshot,paths in snapshot_inputs.items()]
    rows=[]
    for entry in runs:
        for name,trace in entry["trace"].items():
            rows.append(dict(snapshot=entry["snapshot"],case=entry["case"],round3_variant_label=entry["round3_variant_label"],
                             **trace,mocked_argv=json.dumps(entry["observed_argv"].get(name,{}).get("modeled_argv",[])),
                             actual_linker_executed=False,status="PASS"))
    with (ROOT/"11E_REPRODUCTION_RESULTS.csv").open("w",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary=dict(status="PASS",gnu_make=version,gnu_make_file=str(make.relative_to(ROOT)) if make.is_relative_to(ROOT) else str(make),
                 make_sha256=sha(make.read_bytes()),historical_make_nevra="make-4.4.1-1.14.armv7l",input_payloads=snapshot_inputs,
                 new_kbuild_bindings=kbuild,phase9_flag_shapes=21,additional_cases=2,runs=len(runs),observations=len(rows),
                 modeled_calls=2*len(runs),historical_link_proven=False,scope="unmodified RPM Makefiles in the Phase 9 process-boundary mock",
                 results=runs)
    (ROOT/"11E_MAKE_VARIABLE_TRACE.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    print(f"PASS: {len(runs)} exact-payload models, {len(rows)} observations and {2*len(runs)} mock linker calls, {version}.")

if __name__=="__main__":
    main()
