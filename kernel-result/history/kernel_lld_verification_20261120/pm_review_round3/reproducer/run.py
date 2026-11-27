#!/usr/bin/env python3
"""Run the isolated GNU Make linker-scope experiment and emit auditable rows."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXTERNAL = ROOT / "evidence/source/external"
ORIGINAL = "LD = $" + "{CROSS_COMPILE}ld\n"
ARM = "armv7l-tizen-linux-gnueabi-"
ARM64 = "aarch64-tizen-linux-gnu-"
TRACE_FIELDS = ("stage", "makelevel", "origin", "flavor", "raw_ld", "effective_ld", "llvm_origin", "llvm", "cross_compile", "makeflags", "makeoverrides")
TRACE_STAGES = ("kbuild_top_before", "kbuild_top_selected", "build_before_include", "build_after_include", "intermediate", "modpost", "final")

# Expected tool selections at the object merge and final .ko recipe.
CASES = (
    ("historical_shape_control", "original", "1", "", "", "", False, "ld", "ld.lld"),
    ("armv7l_cross_prefix", "original", "1", ARM, "", "", False, ARM+"ld", "ld.lld"),
    ("aarch64_cross_prefix", "original", "1", ARM64, "", "", False, ARM64+"ld", "ld.lld"),
    ("ld_lld_command_line", "original", "1", "", "", "ld.lld", False, "ld.lld", "ld.lld"),
    ("ld_lld_environment", "original", "1", "", "ld.lld", "", False, "ld", "ld.lld"),
    ("ld_bfd_environment", "original", "1", "", "ld.bfd", "", False, "ld", "ld.lld"),
    ("ld_bfd_environment_e", "original", "1", "", "ld.bfd", "", True, "ld.bfd", "ld.bfd"),
    ("clang_bfd_command_line", "original", "1", ARM, "", ARM+"ld.bfd", False, ARM+"ld.bfd", ARM+"ld.bfd"),
    ("llvm_zero", "original", "0", "", "", "", False, "ld", "ld.lld"),
    ("llvm_suffix", "original", "-22", "", "", "", False, "ld", "ld.lld-22"),
    ("gcc_armv7l_original", "original", "", ARM, "", "", False, ARM+"ld", ARM+"ld"),
    ("gcc_aarch64_original", "original", "", ARM64, "", "", False, ARM64+"ld", ARM64+"ld"),
    ("remove_ld_armv7l", "remove", "1", ARM, "", "", False, "ld.lld", "ld.lld"),
    ("remove_ld_aarch64", "remove", "1", ARM64, "", "", False, "ld.lld", "ld.lld"),
    ("remove_ld_gcc_armv7l", "remove", "", ARM, "", "", False, ARM+"ld", ARM+"ld"),
    ("remove_ld_gcc_aarch64", "remove", "", ARM64, "", "", False, ARM64+"ld", ARM64+"ld"),
    ("remove_ld_clang_bfd", "remove", "1", ARM, "", ARM+"ld.bfd", False, ARM+"ld.bfd", ARM+"ld.bfd"),
    ("simple_replacement", "simple", "1", ARM, "", "", False, ARM+"ld", "ld.lld"),
    ("conditional_replacement", "conditional", "1", ARM, "", "", False, "ld.lld", "ld.lld"),
    ("explicit_export_replacement", "export", "1", ARM, "", "", False, ARM+"ld", "ld.lld"),
    ("override_with_cli", "override", "1", ARM, "", "ld.lld", False, "ld.lld", "ld.lld"),
)
VARIANTS = {"original": ORIGINAL, "remove": "", "simple": ORIGINAL.replace(" = "," := "),
            "conditional": ORIGINAL.replace(" = "," ?= "), "export": "export "+ORIGINAL, "override": "override "+ORIGINAL}

def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")

def validate_scopes(name, variant, top, object_child, intermediate, final, expected):
    pair=(intermediate['effective_ld'],final['effective_ld'])
    if pair!=expected:
        raise ValueError(f"{name}: selected {pair}; expected {expected}")
    if name=="historical_shape_control":
        if ((top["origin"],top["flavor"],object_child["origin"],object_child["flavor"],intermediate["origin"],final["origin"]) !=
              ("file","recursive","file","recursive","environment","environment")):
            raise ValueError(f"{name}: unexpected Make origins or flavors")
    if name=="ld_lld_command_line" and any(row["origin"]!="command line" for row in (top,object_child,intermediate,final)):
        raise ValueError(f"{name}: CLI LD did not propagate")
    if name=="ld_bfd_environment_e" and any(row["origin"]!="environment override" for row in (top,object_child,intermediate)):
        raise ValueError(f"{name}: -e did not override the assignments")
    if name=="simple_replacement" and object_child["flavor"]!="simple":
        raise ValueError(f"{name}: := flavor mismatch")
    if name=="conditional_replacement" and object_child["origin"]!="environment":
        raise ValueError(f"{name}: ?= should preserve the existing LD")
    if variant=="override" and object_child["origin"]!="override":
        raise ValueError(f"{name}: explicit override origin missing")

def perform(args):
    make=shutil.which("make")
    if not make:
        raise SystemExit("GNU Make is required")
    original=(EXTERNAL/"Makefile").read_text()
    if original.splitlines(keepends=True)[1]!=ORIGINAL or original.count(ORIGINAL)!=1:
        raise ValueError("archived wrapper's observed LD assignment differs")
    raw_directory=args.output/"evidence"/"reproducer"
    raw_directory.mkdir(parents=True,exist_ok=True)
    env_base={"PATH":os.pathsep.join([str(Path(make).parent),os.defpath]),"LC_ALL":"C","PYTHONIOENCODING":"utf-8",
              "REPRO_DIR":str(HERE),"REPRO_PYTHON":sys.executable,"BUILD_kdbus":"m"}
    version=subprocess.run([make,"--version"],env=env_base,capture_output=True,check=True,text=True).stdout
    if not version.startswith("GNU Make "):
        raise SystemExit("expected GNU Make")
    (raw_directory/"make-version.out").write_text(version)
    results=[]
    receipts=[]
    with tempfile.TemporaryDirectory(prefix=".kdbus-scope-",dir=args.output) as scratch:
        container=Path(scratch)
        for name,variant,llvm,cross,env_ld,cli_ld,use_e,expected_o,expected_ko in CASES:
            case=container/name
            external=case/"external"
            kernel=case/"kernel"
            (external/"kdbus").mkdir(parents=True)
            kernel.mkdir()
            (external/"Makefile").write_text(original.replace(ORIGINAL,VARIANTS[variant]))
            shutil.copy2(EXTERNAL/"kdbus/Makefile",external/"kdbus/Makefile")
            shutil.copy2(HERE/"fixtures/Makefile",kernel/"Makefile")
            env=dict(env_base,MAKEFLAGS="-k")
            if llvm:
                env["LLVM"]=llvm
            if cross:
                env["CROSS_COMPILE"]=cross
            if env_ld:
                env["LD"]=env_ld
            if use_e:
                env["MAKEFLAGS"]="-ek"
            command=[make,"--no-print-directory","-C",str(external),f"KERNELDIR={kernel}"]
            if cli_ld:
                command.append("LD="+cli_ld)
            command.append("all")
            proc=subprocess.run(command,env=env,capture_output=True,text=True,check=False,timeout=30)
            (raw_directory/(name+".out")).write_text(proc.stdout)
            (raw_directory/(name+".err")).write_text(proc.stderr)
            receipts.append(dict(case=name,argv=command,environment=env,exit_status=proc.returncode,
                                 wrapper_input_sha256=hashlib.sha256((external/"Makefile").read_bytes()).hexdigest()))
            write_json(raw_directory/"cases.json",receipts)
            if proc.returncode:
                raise ValueError(f"{name}: GNU Make failed: {proc.stderr}")
            trace = {}
            calls = {}
            for line in proc.stdout.splitlines():
                if line.startswith("PHASE9_LD|"):
                    row=dict(zip(TRACE_FIELDS,line.split("|")[1:],strict=True))
                    if row["stage"] in trace:
                        raise ValueError(f"{name}: duplicate trace stage {row['stage']}")
                    trace[row["stage"]]=row
                if line.startswith("PHASE9_MOCK|"):
                    call=json.loads(line.partition("|")[2])
                    calls[call["stage"]]=call
            if tuple(trace)!=TRACE_STAGES or set(calls)!={"intermediate","final"}:
                raise ValueError(f"{name}: incomplete trace or modeled calls")
            validate_scopes(name,variant,trace["kbuild_top_selected"],trace["build_after_include"],
                            trace["intermediate"],trace["final"],(expected_o,expected_ko))
            for stage, row in trace.items():
                call=calls.get(stage,{})
                if call and (call["actual_linker_executed"] or call["modeled_argv"][0]!=row["effective_ld"]):
                    raise ValueError(f"{name}/{stage}: modeled call differs from trace")
                results.append(dict(case=name,variant=variant,evidence_type="ISOLATED_MAKE_MODEL",env_llvm=llvm,env_ld=env_ld,
                                    cli_ld=cli_ld,env_priority_e=use_e,**row,
                                    mocked_argv=json.dumps(call.get("modeled_argv",[])),result="PASS"))
    with (args.output/"KDBUS_REPRODUCTION_RESULTS.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"PASS: {len(CASES)} GNU Make scenarios, {len(results)} variable observations, {2*len(CASES)} mocked linker argv records.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True,help="Write to an experiment output directory.")
    args=parser.parse_args()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    perform(args)

if __name__=="__main__":
    main()
