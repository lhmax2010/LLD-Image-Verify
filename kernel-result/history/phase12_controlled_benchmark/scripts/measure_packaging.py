#!/usr/bin/env python3
"""Measure equal strip and single-file XZ settings separately from published RPMs."""
import json
import subprocess

from llvm_replay import ROOT, SELECTED, reference

EVIDENCE = ROOT/'evidence/packaging'


def main():
    data = json.loads((ROOT/'evidence/build/controlled-builds.json').read_text())['groups']
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    records={}
    for group,build in data.items():
        unstripped = build['unstripped_module']['size']
        stripped = build['strip_debug_module']['size']
        output = EVIDENCE/f'{group}-module.xz'
        cmd = ['xz','--threads=1','-6','-c',str(ROOT/build['strip_debug_module']['path'])]
        with output.open('wb') as f:
            subprocess.run(cmd, stdout=f, check=True)
        assert subprocess.check_output(['xz','-dc',str(output)]) == (ROOT/build['strip_debug_module']['path']).read_bytes()
        records[group]={'xz_version':subprocess.check_output(['xz','--version'],text=True).splitlines()[0],
                        'strip_trace': str((SELECTED/f'{group}-strip.strace').relative_to(ROOT)),
                        'unstripped_bytes':unstripped,'stripped_bytes':stripped,'bytes_removed_by_strip':unstripped-stripped,
                        'single_file_xz': {'argv':cmd,**reference(output)}}
    (EVIDENCE/'compression.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    main()
