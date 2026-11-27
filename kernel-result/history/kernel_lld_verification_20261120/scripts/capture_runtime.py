#!/usr/bin/env python3
"""Recollect reviewed read commands from the target's authorized SDB serial."""
import json
import re

from record import ROOT, run

SERIAL = 'private-address-02:26101'
ORDER = ('banner','ip','ip-fallback','boot-dtb','files','layout','boot-candidates',
         'partition-metadata','notes','rpm-list','kernel-package-names','pinned-rpm-device-queries',
         'find-direct','alias-find','other-module-roots','module-files','module-owners',
         'module-archive-base64','loaded','loaded-list','loaded-build-ids','lsmod')

def main():
    status, probe = run('preflight/sdb-devices',['sdb','devices'],10)
    target = [row.split() for row in probe.read_text().splitlines()
              if row.split() and row.split()[0]==SERIAL]
    if status or len(target)!=1 or target[0][1:2]!=['device']:
        raise SystemExit(f'Target {SERIAL} is not an authorized SDB device; see {probe.relative_to(ROOT)}')
    commands = json.loads((ROOT/'scripts/runtime-read-plan.json').read_text())
    for stem in ORDER:
        command = commands[stem]
        if stem == 'loaded-build-ids':
            loaded = (ROOT/'evidence/runtime/loaded-list.out').read_text().splitlines()
            if not loaded or loaded[-1]!='[PROC_MODULES_EXIT=0]':
                raise ValueError('could not obtain a valid loaded module snapshot')
            names = [line.split()[0] for line in loaded[:-1]]
            if not all(re.fullmatch('[A-Za-z0-9_]+', name) for name in names):
                raise ValueError('unexpected module name')
            command = 'for m in '+' '.join(names)+'; do'+command.split('; do',1)[1]
        code, path = run('runtime/'+stem,['sdb','-s',SERIAL,'shell',command],150)
        if code:
            raise SystemExit(f'{stem} exited {code}; see {path.relative_to(ROOT)}')
    result, _ = run('runtime/parse-runtime-recollected',['python3','scripts/parse_runtime.py'],60)
    raise SystemExit(result)

if __name__=='__main__':
    main()
