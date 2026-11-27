#!/usr/bin/env python3
"""Audit archived build controls and source members without executing build rules."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parents[1]
DEVEL_PREFIX = PurePosixPath('boot/kernel/devel/kernel-devel-arm-rpi4')
EXTRA = (
    'scripts/Makefile.host', 'scripts/dummy-tools/ld', 'tools/bpf/bpftool/Makefile',
    'tools/bpf/resolve_btfids/Makefile', 'tools/build/Makefile.build',
    'tools/lib/subcmd/Makefile', 'tools/perf/Makefile', 'tools/perf/Makefile.perf',
    'tools/scripts/Makefile.include',
)
PATCH_CONTEXT = re.compile(r'^(?:Makefile(?:\..*)?|Kbuild(?:\..*)?|[^/]+\.mk|[^/]+\.spec)$')
OBJECT_NAME = re.compile(r'(?:\.(?:o|a|obj|elf|rlib|bc|so(?:\.\d+)*|ko(?:\.(?:gz|xz|zst))?)|(?:\.o|\.a|\.ko|\.elf)_shipped)$', re.I)
PATTERNS = (
    ('EXPLICIT_LD_BFD', re.compile(r'(?<![\w.-])ld\.bfd(?![\w.-])')),
    ('BARE_LD', re.compile(r'(?<![\w/.-])ld(?=$|[\s;|&)"\'])')),
    ('CROSS_COMPILE_LD', re.compile(r'\$(?:\(CROSS_COMPILE\)|\{CROSS_COMPILE\})ld\b')),
    ('LD_ASSIGNMENT', re.compile(
        r'(?:^|[\s;])(?:(?:override|export|private)\s+)*(?:LD|HOSTLD)\s*(?:::=|::=|:=|[?+!]?=)'
        r'|(?:^|\s)(?:export|unexport)[^#\n]*\s(?:LD|HOSTLD)(?=$|[\s;])'
        r'|\$\(call\s+allow-override,\s*(?:LD|HOSTLD),')),
    ('LD_RELOCATABLE', re.compile(r'(?:\$\((?:LD|HOSTLD)\)|\$(?:\{(?:LD|ld)\}|(?:LD|ld)\b)|\bld(?:\.lld|\.bfd)?)\s+(?:.*?\s+)?-r(?=\s|$)')),
    ('DRIVER_LINKER_SELECTION', re.compile(r'-fuse-ld(?:=|\s+)\S+|--ld-path(?:=|\s+)\S+')),
    ('HARD_CODED_LINKER_PATH', re.compile(r'(?<![\w/$])/(?:[\w.+-]+/)+ld(?:\.lld|\.bfd)?(?![\w.-])')),
    ('PREBUILT_OBJECT', re.compile(r'\b[\w./-]+\.(?:o|a|ko|elf)_shipped\b|\b(?:incbin|llvm-link)\b')),
    ('RECURSIVE_TOOLCHAIN', re.compile(
        r'(?:\$\((?:MAKE|build)\)|\b(?:g?make|[\w/_-]+-make)\b).*(?:\b(?:LD|HOSTLD|LLVM|LLVM_IAS|CROSS_COMPILE|MAKEFLAGS|GNUMAKEFLAGS|PATH)\s*[:?+]?=|Makefile\.(?:build|modfinal|modpost|vmlinux(?:_o)?)|/tools/|\$\(build\)|(?:^|\s)-C\s+(?:tools/|\$\(KERNELDIR\)|kernel\b))'
        r'|^\s*(?:export\s+)?(?:MAKEFLAGS|GNUMAKEFLAGS|MAKEFILES|LLVM|LLVM_IAS)\s*[:?+]?='
        r'|^\s*export\s+(?:LLVM|LD)\s*(?:#.*)?$')),
    ('INHERITED_LINK_RULE', re.compile(
        r'^\s*(?:(?:quiet_)?cmd_[\w-]+\s*=\s*)?(?:\$\(Q\))?(?:\$\((?:LD|HOSTLD|HOSTCC|HOSTCXX)\)|\$\{(?:LD|ld)\})(?:\s|$)'
        r'|\$\((?:LD|HOSTLD)\)[^#\n]*(?:-o |\s-r\s|-\w+script)|\b(?:if_changed|ld-option),ld\b')),
)
ALLOWED = {'CONFIRMED_BYPASS','POTENTIAL_BYPASS','SAFE_INHERITANCE','EXPECTED_HOST_TOOL','FALSE_POSITIVE'}

def need(value, message):
    if not value:
        raise ValueError(message)

def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()

def out_json(path, data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def cpio_header(inp):
    header=inp.read(110)
    need(len(header)==110 and header[:6] in (b'070701',b'070702'),'unexpected cpio header')
    size=int(header[54:62],16)
    namesize=int(header[94:102],16)
    path=PurePosixPath(inp.read(namesize).decode().rstrip('\0'))
    inp.read((-110-namesize)%4)
    need(not path.is_absolute() and '..' not in path.parts,f'unsafe cpio name: {path}')
    return path,size,int(header[14:22],16)

def save(out, rel, payload):
    path=out/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)

def add_copies(base, out, other):
    primary=other/'evidence/kernel'
    source_binding=json.loads((primary/'kernel-source-binding.json').read_text())
    ext=other/'evidence/external'
    ext_binding=json.loads((ext/'source-content-inventory.json').read_text())
    origin=Path('pm_review_round2/evidence')
    coverage=[]
    def bound(prior, destination, expected, group):
        current=base/prior
        data=current.read_bytes()
        sha=hashlib.sha256(data).hexdigest()
        need(sha==expected,f'archived source checksum differs: {prior}')
        save(out,destination,data)
        coverage.append(dict(file=str(destination),origin=str(prior),sha256=sha,group=group))
    for member in source_binding['devel']['members']+source_binding['srpm']['srpm_spec_members']:
        bound(origin/'kernel'/member['file'],Path('sources/kernel')/Path(member['file']).relative_to('source'),member['sha256'],'matched-kernel')
    provider_members={row['path']:row for row in ext_binding['provider_members']}
    for rel in ext_binding['makefiles']:
        member=provider_members[f'usr/src/linux-tizen-modules-source/{rel}']
        bound(origin/'external/source'/rel,Path('sources/external')/rel,member['sha256'],'external-provider')
    wrapper=base/origin/'external/linux-tizen-modules.spec'
    bound(origin/'external/linux-tizen-modules.spec',Path('sources/external/linux-tizen-modules.spec'),digest(wrapper),'external-wrapper')
    return source_binding,ext_binding,coverage

def load_extra(base,out,binding,coverage):
    path=Path(binding['devel']['payload'])
    with (base/path).open('rb') as file:
        while True:
            member,size,mode=cpio_header(file)
            if member.name=='TRAILER!!!':
                break
            offset=file.tell()
            if member.is_relative_to(DEVEL_PREFIX):
                name=str(member.relative_to(DEVEL_PREFIX))
                if name in EXTRA and mode&0o170000==0o100000:
                    data=file.read(size)
                    copied=Path('sources/host-and-tools')/name
                    save(out,copied,data)
                    coverage.append(dict(file=str(copied),origin=str(path),cpio_member=str(member),
                                         cpio_payload_offset=offset,sha256=hashlib.sha256(data).hexdigest(),group='host-and-tools'))
            file.seek(offset+size+(-size)%4)
    found={Path(row['file']).relative_to('sources/host-and-tools').as_posix() for row in coverage if row['group']=='host-and-tools'}
    need(set(EXTRA)==found, f'missing exact devel rules {set(EXTRA)-found}')

class Bounded:
    def __init__(self, stream, length):
        self.stream=stream
        self.remaining=length
    def read(self, size=-1):
        take=min(size,self.remaining) if size>=0 else self.remaining
        result=self.stream.read(take)
        need(len(result)==take,'truncated source tar member')
        self.remaining-=len(result)
        return result

def identify_header(raw):
    for magic, label in ((b'\x7fELF','ELF'),(b'!<arch>\n','ar'),(b'!<thin>\n','thin ar'),
                         (b'BC\xc0\xde','LLVM bitcode'),(b'\xde\xc0\x17\x0b','LLVM bitcode wrapper'),
                         (b'\x1f\x8b','gzip'),(b'\xfd7zXZ\x00','xz'),(b'\x28\xb5\x2f\xfd','zstd'),
                         (b'PK\x03\x04','zip')):
        if raw.startswith(magic):
            return label
    return ''

def read_srpm(base,out,binding):
    srpm=binding['srpm']
    src=base/srpm['rpm']
    need(digest(src)==srpm['rpm_sha256'],'kernel SRPM SHA256 differs')
    parents={PurePosixPath(s) for s in binding['directory_scope']}
    prefixes=set(PurePosixPath(s) for s in (
        'arch/arm/boot/compressed','tools/bpf/resolve_btfids','tools/perf','tools/build',
        'scripts/dummy-tools','scripts/basic'))
    examined=0
    total=0
    samples=[]
    prebuilt=[]
    patch_rows=[]
    proc=subprocess.Popen(['rpm2cpio',str(src)],stdout=subprocess.PIPE)
    with proc.stdout as raw:
        while True:
            member,size,_=cpio_header(raw)
            if member.name=='TRAILER!!!':
                raw.read()
                break
            remaining=Bounded(raw,size)
            if member.name==srpm['tar_member']:
                with tarfile.open(fileobj=remaining,mode='r|xz') as archive:
                    for item in archive:
                        total+=1
                        p=PurePosixPath(item.name)
                        if len(p.parts)<2:
                            continue
                        rel=PurePosixPath(*p.parts[1:])
                        if not (rel.parent in parents or any(rel.is_relative_to(prefix) for prefix in prefixes)):
                            continue
                        if not item.isfile():
                            if item.islnk() or item.issym():
                                if OBJECT_NAME.search(str(rel)):
                                    prebuilt.append(dict(path=str(rel),kind='object-like archive link',target=item.linkname))
                            continue
                        examined+=1
                        body=archive.extractfile(item)
                        prefix=body.read(16)
                        magic=identify_header(prefix)
                        if magic or OBJECT_NAME.search(str(rel)):
                            hit=dict(path=str(rel),kind=magic or 'object-like suffix',size=item.size,hex16=prefix.hex(),
                                     object_suffix=bool(OBJECT_NAME.search(str(rel))))
                            samples.append(hit)
                            if hit['object_suffix'] or magic in ('ELF','ar','thin ar','LLVM bitcode','LLVM bitcode wrapper'):
                                prebuilt.append(hit)
            elif any(stem in member.name for stem in ('.patch','.diff')):
                import gzip
                data=remaining.read()
                match=next(row for row in srpm['patches'] if row['file']==member.name)
                need(hashlib.sha256(data).hexdigest()==match['sha256'],f'patch hash differs: {member}')
                text=(gzip.decompress(data) if member.name.endswith('.gz') else data).decode('utf-8','replace')
                patch_rows+=patch_controls(member.name,text,parents,prefixes)
            remaining.read()
            raw.read((-size)%4)
    need(proc.wait()==0 and total==srpm['tar_members_examined'],'source archive scan mismatch')
    result=dict(rpm=srpm['rpm'],rpm_sha256=srpm['rpm_sha256'],tar_member=srpm['tar_member'],archive_members_seen=total,
                scoped_regular_magic_checked=examined,exact_parent_directory_scope=sorted(map(str,parents)),
                supplementary_prefixes=sorted(map(str,prefixes)),magic_and_suffix_matches=samples,
                possibly_prebuilt_matches=prebuilt,round2_external_prebuilt_evidence='pm_review_round2/evidence/external/source-content-inventory.json')
    out_json(out/'source-object-magic.json',result)
    out_json(out/'patch-control-lines.json',patch_rows)
    return result,patch_rows

def patch_controls(patch,text,parents,prefixes):
    result=[]
    path=None
    for i,line in enumerate(text.splitlines(),1):
        if line.startswith('+++ b/'):
            target=PurePosixPath(line[6:].split('\t',1)[0])
            path=target if (PATCH_CONTEXT.fullmatch(target.name) and
                    (target.parent in parents or any(target.is_relative_to(prefix) for prefix in prefixes))) else None
        elif path and line.startswith('+') and not line.startswith('+++'):
            result.append(dict(patch=patch,line=i,target=str(path),raw=line[1:]))
    return result

def logical_lines(lines):
    start=1
    group=[]
    for number,line in enumerate(lines,1):
        if not group:
            start=number
        group.append(line)
        if not line.rstrip().endswith('\\'):
            yield start,number,group
            group=[]
    if group:
        yield start,number,group

def classify_row(file,start,end,raw,tags):
    parts=PurePosixPath(file).parts
    group=parts[1]
    rel=PurePosixPath(*parts[2:]).as_posix()
    if raw.startswith('#'):
        return 'FALSE_POSITIVE', 'comment or help', 'Comment/prose or an example does not execute a linker.'
    if group=='external':
        if rel=='Makefile' and start==2:
            return 'POTENTIAL_BYPASS', 'kdbus/kdbus.o', (
                'Exact provider Makefile is included by scripts/Makefile.build L41. Its recursive LD assignment '
                'replaces the inherited environment value and descends via L485 to the composite-object rule at L433. '
                'External log L612 records that target. Archived ld/ld.bfd gives a GNU BFD path without an exec receipt. '
                'The separate modfinal sibling used at L636 does not import the assignment.')
        if rel=='Makefile':
            return 'SAFE_INHERITANCE', 'external wrapper recipe', (
                'Wrapper forwards kernel/M/install arguments. This line has no LD or LLVM command-line assignment.')
        if rel.endswith('.spec'):
            if 245<=start<=268:
                return 'SAFE_INHERITANCE', 'non-RT RPi4 packaging', (
                    'Non-RT RPi4 SPEC exports LLVM=1 and submits clean/build/install without assigning LD; '
                    'historical expanded commands appear at external log L565 and L574-L576.')
            return 'FALSE_POSITIVE', 'other platform or RPi4 RT', (
                'Different hardware or the separate RT recipe. This line is excluded from the observed non-RT target.')
    if group=='host-and-tools':
        if rel.startswith('scripts/dummy-tools/'):
            return 'FALSE_POSITIVE', 'synthetic build probe', 'Dummy tool fixture has no observed place in the historical target build.'
        if rel.endswith('scripts/Makefile.host') or rel.startswith('tools/bpf/') or 'HOSTLD' in raw or 'host_' in raw:
            return 'EXPECTED_HOST_TOOL', 'Kbuild host utility', (
                'Host-tool linker settings or HOSTCC/HOSTLD recipes build a build-time program or its supporting library. '
                'The target Kbuild LD and module final rule are a different link scope.')
        if rel.startswith('tools/lib/subcmd/'):
            return 'EXPECTED_HOST_TOOL', 'tool-support library', (
                'This subcmd fallback/export is scoped to a tool-support library. The observed resolve_btfids child '
                'takes HOST_OVERRIDES and emits libsubcmd-in.o (kernel log L3455), outside target kernel and .ko.')
        return 'FALSE_POSITIVE', 'standalone userspace tool', (
            'This is the separate tools build. It selects or passes link variables for perf or its supporting objects, '
            'not vmlinux or a kernel module; perf has a separate SPEC invocation and build log scope.')
    if rel=='Makefile':
        if 'KBUILD_USERLDFLAGS' in raw:
            return 'SAFE_INHERITANCE', 'compiler-driven userspace helper', (
                'When CONFIG_CC_IS_CLANG, the user-program driver option --ld-path uses the current LD. '
                'This neither chooses a different executable nor proves which target kernel linker ran.')
        if start==489:
            return 'FALSE_POSITIVE', 'normal non-LLVM compiler branch', (
                'Ordinary Kbuild fallback when LLVM is empty. Observed RPi4 Linux SPEC exports LLVM=1 before '
                'building; that selects L480. This line does not override the observed LLVM selection.')
        if '$(HOST' in raw or re.search(r'\btools/(?:bpf/resolve_btfids|objtool)',raw):
            return 'EXPECTED_HOST_TOOL', 'Kbuild host-tool descendant', 'Recursive build of a host utility under tools/.'
        if '/tools/' in raw:
            return 'FALSE_POSITIVE', 'separate tools or selftest target', 'Explicit tools or selftest goal is outside final target evidence.'
        return 'SAFE_INHERITANCE', 'kernel parent and recursive targets', (
            'Top-level selection/export or recursion retains the effective selected LD. The matching non-RT build '
            'selected LLVM=1 and the recipe supplies no alternate target linker.')
    if rel=='scripts/ld-version.sh':
        return 'FALSE_POSITIVE', 'version identification', 'Comparison/display of version text does not name the program being executed.'
    if rel=='scripts/link-vmlinux.sh':
        if raw=='local ld':
            return 'FALSE_POSITIVE', 'shell declaration', 'A local variable declaration is not a bare ld invocation.'
        return 'SAFE_INHERITANCE', 'vmlinux/temporary kernel ELF', (
            'Shell script obtains its LD from positional argument 1 passed by scripts/Makefile.vmlinux. '
            'Native ARM uses the inherited linker; UML-only compiler branch is outside this build.')
    if rel=='scripts/Makefile.lib' and 'incbin' in raw:
        return 'FALSE_POSITIVE', 'generated device-tree blob', (
            'The assembler includes a device-tree data blob, not a precompiled object. DTC rule builds the prerequisite.')
    if rel=='scripts/Makefile.lib' and '$(DTC)' in raw:
        return 'EXPECTED_HOST_TOOL', 'host preprocessing and DTC', (
            'HOSTCC performs preprocessing for the build-time device-tree compiler; it does not link the target kernel.')
    if rel=='scripts/Makefile.build' and 'single_m' in raw:
        return 'SAFE_INHERITANCE', 'optional single-object LTO conversion', (
            'The generic command uses the current LD; this branch is gated by CONFIG_LTO_CLANG. '
            'The observed auto.conf enables CONFIG_LTO_NONE and does not activate the conversion.')
    if rel=='scripts/Makefile.build' and 'multi_m' in raw:
        return 'SAFE_INHERITANCE', 'composite .o linker consumer', (
            'Recipe invokes the current LD instead of replacing it. Caller provenance matters: the external '
            'provider assignment can alter LD for the kdbus composite path, which is classified separately.')
    if rel=='scripts/Makefile.build':
        return 'SAFE_INHERITANCE', 'object-builder recursive scope', (
            'Kbuild passes tools to descendants. Child makefile includes may reassign that value, including the '
            'known external provider override at its Makefile L2.')
    if rel=='scripts/Makefile.modfinal':
        return 'SAFE_INHERITANCE', 'final .ko', (
            'Parent launches separate modfinal with exported LD. The final rule consumes it for -r and never '
            'includes the external module Makefile; no recursive override in the scoped final rule.')
    if rel=='scripts/Makefile.vmlinux_o':
        return 'SAFE_INHERITANCE', 'vmlinux.o', 'Relocatable kernel link consumes top-level LD through the exported Kbuild toolchain.'
    if rel in ('arch/arm/boot/Makefile','arch/arm/boot/compressed/Makefile','scripts/Makefile.lib',
               'scripts/Makefile.vmlinux','arch/arm/Makefile'):
        return 'SAFE_INHERITANCE', 'kernel or ARM wrapper', (
            'Recipe or shorthand derives the historically scoped kernel/ARM rule from the parent LD, '
            'or adjusts flags/features without selecting an executable.')
    if rel=='spec/linux-rpi.spec':
        if 'tools/' in raw:
            return 'FALSE_POSITIVE', 'separate tools build/install', 'The kernel SPEC invokes a separate userspace utility or bootstrap build goal.'
        return 'SAFE_INHERITANCE', 'Linux RPM toolchain', 'SPEC exports LLVM=1 for the selected non-RT target without overriding the linker explicitly.'
    return '', '', ''


def scan(out, coverage, patch_rows):
    found=[]
    for item in sorted(coverage,key=lambda row:row['file']):
        name=item['file']
        for start,end,group in logical_lines((out/name).read_text(errors='replace').splitlines()):
            connection=' '.join(line.strip().removesuffix('\\').rstrip() for line in group)
            tags=[tag for tag,regex in PATTERNS if regex.search(connection)]
            if not tags:
                continue
            classification, target, rationale=classify_row(name,start,end,connection,tags)
            found.append(dict(source_file=name,line_start=start,line_end=end,patterns='|'.join(tags),raw='\n'.join(group),
                              classification=classification,target=target,reason=rationale,origin=item['origin']))
    for item in patch_rows:
        raw=item['raw'].strip()
        tags=[tag for tag,regex in PATTERNS if regex.search(raw)]
        if tags:
            classification,target,reason=classify_row('sources/kernel/'+item['target'],item['line'],item['line'],raw,tags)
            if item['target'].startswith('tools/') and not classification:
                classification,target,reason=('FALSE_POSITIVE','standalone userspace tools patch',
                    'A matching SRPM patch modifies a tools/ program; active target kernel rules were taken from the patched devel payload.')
            found.append(dict(source_file='patch-control-lines.json',line_start=item['line'],line_end=item['line'],
                              patterns='|'.join(tags),raw=item['raw'],classification=classification,target=target,reason=reason,
                              origin=f"{item['patch']}:{item['target']}"))
    return found

def write_csv(path, rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=HERE.parent)
    parser.add_argument('--output',type=Path,default=HERE)
    parser.add_argument('--reuse-scan',action='store_true',help='Reclassify sealed exact copied sources and patch scan.')
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    need(out!=base and not out.is_relative_to(base/'pm_review_round2'),
         'staged audit output must not modify Round 1 or Round 2')
    audit=out/'evidence/audit'
    audit.mkdir(parents=True,exist_ok=True)
    if args.reuse_scan:
        scope=json.loads((audit/'source-scope.json').read_text())
        coverage=scope['files']
        for member in coverage:
            need(digest(audit/member['file'])==member['sha256'],f"copied source differs: {member['file']}")
        patch_rows=json.loads((audit/'patch-control-lines.json').read_text())
    else:
        binding,external,coverage=add_copies(base,audit,base/'pm_review_round2')
        load_extra(base,audit,binding,coverage)
        machine,patch_rows=read_srpm(base,audit,binding)
        scope=dict(snapshot=binding['snapshot'],kernel_revision=binding['vcs_revision'],
                   external_revision=external['provider_package']['vcs'],files=coverage,
                   archive=machine, external_provider_members=len(external['provider_members']),
                   external_wrapper_source0_members=len(external['source0_members']),
                   external_prebuilt_findings=external['prebuilt_findings'])
        out_json(audit/'source-scope.json',scope)
    matches=scan(audit,coverage,patch_rows)
    write_csv(audit/'raw-candidates.csv',matches)
    print(f"Controls: {len(coverage)}; source and patch matches: {len(matches)}; magic members: {scope['archive']['scoped_regular_magic_checked']}")
    print('Classes: '+str(Counter(row['classification'] for row in matches)))
    missing=[f"{row['source_file']}:{row['line_start']}" for row in matches if row['classification'] not in ALLOWED]
    need(not missing,f'Unclassified source lines: {missing}')
    dispositions=[dict(row,source_file='evidence/audit/'+row['source_file']) for row in matches]
    write_csv(out/'KERNEL_LINKER_OVERRIDE_FINDINGS.csv',dispositions)
    tag_counts=Counter(t for row in matches for t in row['patterns'].split('|'))
    counts=Counter(row['classification'] for row in matches)
    out_json(audit/'findings-summary.json',dict(
        source_control_files=len(coverage),source_and_patch_hits=len(matches),classification_counts={key:counts[key] for key in sorted(ALLOWED)},
        pattern_counts={tag:tag_counts[tag] for tag,_ in PATTERNS},
        prebuilt_kernel_confirmed=len(scope['archive']['possibly_prebuilt_matches']),
        prebuilt_external_confirmed=len(scope['external_prebuilt_findings']),
        original_target_release='6.12.80-arm-rpi4-v7l',
        potential_bypass_rows=[row for row in dispositions if row['classification']=='POTENTIAL_BYPASS']))


if __name__=='__main__':
    main()
