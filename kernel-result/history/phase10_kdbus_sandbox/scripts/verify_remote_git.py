#!/usr/bin/env python3
"""Fetch the published Gerrit ref into an empty Git repository and verify the commit."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"evidence"
REF="refs/heads/sandbox/liushanshan/lld"
URL="https://review.tizen.org/gerrit/platform/kernel/linux-tizen-modules-source"
BASE="25797e8af7ed95a5783bbe84c11959560aaf7e92"

def git(repo,*args):
    argv=["git","-C",str(repo),*args]
    result=subprocess.run(argv,capture_output=True,check=False,timeout=80)
    print(json.dumps(dict(argv=argv,exit_status=result.returncode,stderr=result.stderr.decode(errors="replace"))))
    result.check_returncode()
    return result.stdout

def need(check,message):
    if not check:
        raise ValueError(message)

def main():
    local=git(ROOT/"checkout","rev-parse","HEAD").decode().strip()
    expected_diff=(EVIDENCE/"local-commit-diff.out").read_bytes()
    expected_message=(EVIDENCE/"local-commit-message.out").read_text().strip()
    with tempfile.TemporaryDirectory(prefix=".gerrit-fresh-verification-",dir=ROOT) as name:
        remote=Path(name)
        git(remote,"init","--bare","--quiet")
        git(remote,"fetch","--no-tags",URL,f"{REF}:{REF}")
        head=git(remote,"rev-parse",REF).decode().strip()
        git(remote,"merge-base","--is-ancestor",local,head)
        parents=git(remote,"rev-list","--parents","-n","1",local).decode().split()
        need(parents==[local,BASE],"wrong published commit parent")
        diff=git(remote,"show","--format=","--no-ext-diff","--no-textconv",local)
        need(diff==expected_diff,"remote diff does not match locally approved patch")
        numstat=git(remote,"diff-tree","--no-commit-id","--numstat","-r",local).decode().strip()
        need(numstat=="0\t1\tkernel/Makefile","unexpected paths or counts in published commit")
        message=git(remote,"show","-s","--format=%B",local).decode().strip()
        need(message==expected_message,"remote message or Gerrit trailers differ")
        after=git(remote,"show",f"{local}:kernel/Makefile")
        model=json.loads((EVIDENCE/"make-validation/summary.json").read_text())
        need(hashlib.sha256(after).hexdigest()==model["candidate_sha256"],"remote Makefile differs from isolated validation input")
        (EVIDENCE/"remote-fetched-diff.out").write_bytes(diff)
        report=dict(status="PASS",method="fresh authenticated Git fetch into an empty bare repository",
                    remote_url=URL,ref=REF,remote_head=head,remote_head_contains_commit=True,
                    remote_head_exact_commit=head==local,expected_commit=local,parent=BASE,
                    diff_equals_local=True,changed_file="kernel/Makefile",added_lines=0,
                    deleted_lines=1,makefile_sha256=model["candidate_sha256"],commit_message_equals_local=True)
        (EVIDENCE/"remote-object-verification.json").write_text(json.dumps(report,indent=2)+"\n")
        print(f"PASS: Gerrit {REF} at {head} contains {local}; parent, one-line diff, candidate SHA256 and commit message match")

if __name__=="__main__":
    main()
