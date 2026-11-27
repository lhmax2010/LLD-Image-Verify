#!/usr/bin/env python3
"""Recompute external-module source and payload bindings without executing their contents."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parents[1]
OUT = HERE/'evidence/external'
RELEASE = '6.12.80-arm-rpi4-v7l'
NAME = 'linux-tizen-modules-rpi4-11.0.0-0.armv7l'
PROVIDER = 'linux-tizen-modules-source-11.0.0-0.armv7l'
SRCROOT = 'usr/src/linux-tizen-modules-source/'
SPECRPM = 'linux-tizen-modules-11.0.0-0.src.rpm'
TARBALL = 'linux-tizen-modules-11.0.0.tar.xz'
MODULES = ('dm-bow', 'extcon-usb-fixed', 'inform-reboot', 'kdbus/kdbus',
           'logger', 'proc-tsm', 'zlogger/zlogger')
LINKERS = ('ld', 'ld.bfd')
BINUTILS = 'binutils-2.43-1.8.armv7l.rpm'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def require(ok, context):
    if not ok:
        raise ValueError(context)

def run(stem, argv, retain=True):
    argv = list(map(str, argv))
    result = subprocess.run(argv, cwd=HERE, capture_output=True, check=False)
    write_json(stem+'.cmd.json', dict(argv=argv, cwd=str(HERE), exit_status=result.returncode,
        stdout_bytes=len(result.stdout), stdout_sha256=sha(result.stdout), stdout_retained=retain))
    (OUT/(stem+'.err')).write_bytes(result.stderr)
    if retain:
        (OUT/(stem+'.out')).write_bytes(result.stdout)
    require(result.returncode==0, f'{stem} exit {result.returncode}')
    return result.stdout

def package_from_primary(path, name, arch, version, rel):
    with gzip.open(path, 'rb') as stream:
        for _, p in ET.iterparse(stream, events=('end',)):
            if p.tag.rsplit('}',1)[-1]!='package':
                continue
            v = p.find('{*}version')
            if (p.findtext('{*}name'),p.findtext('{*}arch'),v.get('ver'),v.get('rel'))==(name,arch,version,rel):
                return dict(name=name, arch=arch, version=version, release=rel,
                            href=p.find('{*}location').get('href'), sha256=p.findtext('{*}checksum'),
                            bytes=int(p.find('{*}size').get('package')),
                            files=[element.text for element in p.findall('.//{*}file')])
            p.clear()
    raise ValueError(f'{name} not in archived primary')

def verify_rpm(path, row, stem):
    require(path.stat().st_size==row['bytes'] and sha(path.read_bytes())==row['sha256'],
            f'archived primary mismatch: {path}')
    run(stem+'-rpm-digests',['rpm','-Kv',path])
    info = run(stem+'-rpm-header',['rpm','-qp','--qf',
        '%{NAME}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n%{SOURCERPM}\n%{VCS}\n',path]).decode().splitlines()
    require(info[:4]==[row[key] for key in ('name','version','release','arch')], f'RPM header identity {path}')
    return dict(row, rpm_file=path.name, source_rpm=info[4], vcs=info[5])

def require_primary(base, repomd, path, kind):
    roots = ET.parse(base/repomd)
    desc = roots.find(f".//{{*}}data[@type='{kind}']")
    expected = desc.findtext('{*}checksum')
    contents = (base/path).read_bytes()
    require(sha(contents)==expected, f'{kind} compressed checksum')
    require(sha(gzip.decompress(contents))==desc.findtext('{*}open-checksum'),
            f'{kind} open checksum')
    return dict(path=path, compressed_sha256=expected,
                open_sha256=desc.findtext('{*}open-checksum'))

def newc(stem, path, hardlink_details=None):
    archive = run(stem,['rpm2cpio',path],retain=False)
    offset = 0
    paths = {}
    inode_members = {}
    while True:
        head = archive[offset:offset+110]
        require(head[:6] in (b'070701',b'070702'), 'invalid cpio newc header')
        fields = [int(head[number:number+8],16) for number in range(6,110,8)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        offset += 110
        raw_name = archive[offset:offset+namesize]
        require(raw_name.endswith(b'\0'), 'unclosed cpio name')
        name = raw_name[:-1].decode()
        if name=='TRAILER!!!':
            break
        pure = PurePosixPath(name)
        require(not pure.is_absolute() and '..' not in pure.parts, f'unsafe cpio path {name}')
        name = str(pure)
        require(name not in paths, f'duplicate cpio path {name}')
        offset = (offset+namesize+3)&~3
        data = archive[offset:offset+size]
        require(len(data)==size, f'truncated {name}')
        offset = (offset+size+3)&~3
        paths[name] = (mode,data)
        nlink = fields[4]
        if stat.S_ISREG(mode) and nlink>1:
            key = (fields[7],fields[8],fields[0])
            inode_members.setdefault(key,[]).append((name,nlink,size))
    for key, entries in inode_members.items():
        carriers = [member for member, _, size in entries if size]
        require(len(carriers)<=1,f'unsupported multiply-populated cpio hardlink group {entries}')
        if not carriers:
            continue
        carrier = carriers[0]
        for name,nlink,stored_bytes in entries:
            paths[name] = (paths[name][0],paths[carrier][1])
            if hardlink_details is not None:
                hardlink_details[name]=dict(nlink=nlink, device_major=key[0], device_minor=key[1],
                    inode=key[2], archive_entry_bytes=stored_bytes, data_carrier='/'+carrier)
    return paths

def member_row(path, mode, content):
    kind = 'regular' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'other'
    magics = (b'\x7fELF', b'!<arch>\n', b'!<thin>\n', b'BC\xc0\xde', b'\xde\xc0\x17\x0b')
    compressors = (b'\x1f\x8b', b'\xfd7zXZ\x00', b'\x28\xb5\x2f\xfd', b'BZh', b'PK\x03\x04')
    return dict(path=path, file_type=kind, size=len(content), sha256=sha(content),
                object_suffix=bool(re.search(r'\.(?:o(?:_shipped)?|obj|a|bc|so|ko)(?:\.|$)',path,re.I)),
                object_magic=any(content.startswith(magic) for magic in magics),
                nested_archive_magic=any(content.startswith(magic) for magic in compressors),
                magic16=content[:16].hex())

def record_lines(lines, start, end):
    require(0<start<=end<=len(lines),f'invalid range {start}..{end}')
    return [dict(line=number, raw=lines[number-1]) for number in range(start,end+1)]

def match_event(lines, start, end, phrase):
    matches = [item for item in record_lines(lines,start,end) if re.search(phrase,item['raw'])]
    require(len(matches)==1, f'expected one event {phrase!r}: {matches}')
    return matches[0]

def module_paths_from_filelists(base, pkgid):
    with gzip.open(base/'evidence/repository/packages-filelists.out','rb') as data:
        for _, obj in ET.iterparse(data,events=('end',)):
            if obj.tag.rsplit('}',1)[-1]=='package':
                if obj.get('pkgid')==pkgid:
                    return sorted(path.text for path in obj.findall('{*}file')
                                  if path.text and path.text.endswith('.ko'))
                obj.clear()
    raise ValueError(f'missing filelists record {pkgid}')

def main():
    opt = argparse.ArgumentParser(description=__doc__)
    opt.add_argument('--base', type=Path, default=HERE.parent, help='archived round-one directory')
    opt.add_argument('--binutils-rpm', type=Path, help='optional exact binutils RPM for executable resolution')
    args = opt.parse_args()
    base = args.base.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    paths = dict(target_primary='evidence/repository/packages-primary.out',
                 base_primary='evidence/build/historical-base-primary.out',
                 target_repomd='evidence/repository/packages-repomd.out')
    metadata = [
        require_primary(base,paths['target_repomd'],paths['target_primary'],'primary'),
        require_primary(base,paths['target_repomd'],'evidence/repository/packages-filelists.out','filelists')]
    provider = package_from_primary(base/paths['target_primary'],'linux-tizen-modules-source','armv7l','11.0.0','0')
    published = package_from_primary(base/paths['target_primary'],'linux-tizen-modules-rpi4','armv7l','11.0.0','0')
    target = base/'evidence/repository/rpms'/(NAME+'.rpm')
    source = OUT/(PROVIDER+'.rpm')
    source_info = verify_rpm(source,provider,'source-provider')
    target_info = verify_rpm(target,published,'external-target')
    source_match = 'platform/kernel/linux-tizen-modules-source#25797e8af7ed95a5783bbe84c11959560aaf7e92'
    packaging_match = 'platform/kernel/linux-tizen-modules#458baad02d812098938663971d1b8560a4813375'
    require(source_info['vcs']==source_match and target_info['vcs']==packaging_match and
            target_info['source_rpm']==SPECRPM,'VCS and Source RPM attribution')
    manifest_path='evidence/repository/manifest.out'
    manifest=(base/manifest_path).read_text().splitlines()
    binding=[match_event(manifest,1,len(manifest),project+r'" .*revision="'+rev+'"' )
             for project, rev in (source_match.split('#'), packaging_match.split('#'))]
    members = newc('source-provider-cpio',source)
    vendor_files = {path[len(SRCROOT):]:(mode,body) for path,(mode,body) in members.items()
                    if path.startswith(SRCROOT)}
    require(all(stat.S_ISREG(value[0]) for value in vendor_files.values()),
            'non-regular content in the packaged external source tree')
    makefiles=[]
    for path,(mode,body) in vendor_files.items():
        if PurePosixPath(path).name in ('Makefile','Kbuild'):
            where=OUT/'source'/path
            where.parent.mkdir(parents=True,exist_ok=True)
            where.write_bytes(body)
            makefiles.append(path)
    require(sorted(makefiles)==['Makefile','kdbus/Makefile','zlogger/Makefile'],'external Makefile inventory')
    vendor_rows=[member_row(path,mode,body) for path,(mode,body) in sorted(members.items())]
    source0 = newc('external-wrapper-srpm-cpio',base/'evidence/repository/rpms'/SPECRPM)
    spec = source0['linux-tizen-modules.spec'][1]
    require(spec==(base/'evidence/build/external-source/linux-tizen-modules.spec').read_bytes(),
            'wrapper SPEC differs from archived report')
    (OUT/'linux-tizen-modules.spec').write_bytes(spec)
    with tarfile.open(fileobj=io.BytesIO(source0[TARBALL][1]),mode='r:xz') as archive:
        archive_rows=[]
        for item in archive.getmembers():
            require(item.isfile() or item.isdir(),f'unexpected wrapper Source0 member {item.name}')
            if item.isfile():
                data=archive.extractfile(item).read()
                archive_rows.append(member_row(item.name,stat.S_IFREG,data))
    for result in vendor_rows+archive_rows:
        require(not any(result[k] for k in ('object_suffix','object_magic','nested_archive_magic')),
                f'prebuilt or nested data detected: {result["path"]}')
    payload=newc('external-target-cpio',target)
    payloads={path:body for path,(mode,body) in payload.items()
              if path.endswith('.ko') and stat.S_ISREG(mode)}
    filelists=module_paths_from_filelists(base,published['sha256'])
    expected=['/lib/modules/'+RELEASE+'/extra/'+item+'.ko' for item in MODULES]
    require(sorted('/'+path for path in payloads)==sorted(expected)==filelists,
            'final .ko filelist, RPM payload and expected target set differ')
    payload_headers = run('external-target-rpm-filedigests',['rpm','-qp','--qf',
        '%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\n]',target]).decode().splitlines()
    require(payload_headers[0]=='8','RPM payload file digest algorithm is not SHA256')
    payload_headers=dict(line.split('\t',1) for line in payload_headers[1:])
    with (base/'05_kernel_module_inventory.csv').open(newline='') as stream:
        inventory=[r for r in csv.DictReader(stream) if r['path'] in expected or r['repository_path'] in expected]
    require(len(inventory)==14,'expected seven exact rows per source')
    repo={r['path']:r for r in inventory if r['scope']=='repository'}
    installed={r['repository_path']:r for r in inventory if r['scope']=='device'}
    require(len(repo)==len(installed)==7,'duplicate module paths')
    log_path='evidence/build/linux-tizen-modules-armv7l.out'
    log=(base/log_path).read_bytes()
    (OUT/'external-buildlog-full.out').write_bytes(log)
    lines=log.decode().splitlines()
    ranges=[(1,20),(358,358),(397,487),(491,611),(612,665),(765,790),(807,833),(850,867)]
    (OUT/'external-buildlog-lines.txt').write_text(''.join(f'{entry["line"]:4d} {entry["raw"]}\n'
        for lo,hi in ranges for entry in record_lines(lines,lo,hi)))
    provider_log=(OUT/'source-provider-buildlog.out').read_bytes()
    provider_lines=provider_log.decode().splitlines()
    provider_wrote=match_event(provider_lines,1,len(provider_lines),r'\bWrote: .*/'+re.escape(PROVIDER)+r'\.rpm$')
    rootmake=vendor_files['Makefile'][1].decode().splitlines()
    kdbus_make=vendor_files['kdbus/Makefile'][1].decode().splitlines()
    simple_inputs=[line[:-2]+'.c' for line in re.findall(r'(?m)^\s*([a-z_-]+\.o)\s*\\?\s*$', '\n'.join(kdbus_make))]
    kdbus_inputs=['kdbus/'+line for line in simple_inputs]
    require(len(kdbus_inputs)==19,'kdbus objects not matched')
    module_rows=[]
    for module in MODULES:
        path='/lib/modules/'+RELEASE+'/extra/'+module+'.ko'
        raw_sha=sha(payloads[path[1:]])
        device_sha=sha((base/installed[path]['file']).read_bytes())
        require(raw_sha==payload_headers[path]==repo[path]['raw_sha256']==device_sha==installed[path]['raw_sha256'],
                f'module SHA256 mismatch for {path}')
        require(repo[path]['parsed']=='True' and repo[path]['classification']=='LLD_INDICATED' and
                installed[path]['classification']=='LLD_INDICATED' and
                repo[path]['proves_final_link']=='False','round one status or parse changed')
        obj_sources=kdbus_inputs if module=='kdbus/kdbus' else [module+'.c']
        for real_source in obj_sources:
            require(real_source in vendor_files,f'missing compiled source {real_source}')
        compile_events=[match_event(lines,577,617,r'\bCC \[M\]\s+.*/kernel/'+re.escape(real_source[:-2])+r'\.o$')
                        for real_source in obj_sources]
        proof=match_event(lines,620,640,r'\bLD \[M\]\s+.*/kernel/'+re.escape(module)+r'\.ko$')
        install=match_event(lines,646,661,r'\bINSTALL\s+.*'+re.escape(path)+r'$')
        intermediate=match_event(lines,577,617,r'\bLD \[M\]\s+.*/kernel/kdbus/kdbus\.o$') if module=='kdbus/kdbus' else None
        module_rows.append(dict(name=repo[path]['name'],module_path=path,device_path=installed[path]['path'],
             source_inputs=obj_sources,build_log_cc=compile_events,build_log_final_link=proof,
             build_log_install=install,build_log_intermediate_link=intermediate,
             payload_sha256=raw_sha, device_sha256=device_sha, binary_rpm=target.name,
             binary_source_rpm=SPECRPM, provider_rpm=source.name,
             provider_source_rpm=source_info['source_rpm'], round1_classification=repo[path]['classification']))
    ld_assign=match_event(rootmake,1,len(rootmake),r'^LD\s*=\s*\$\{CROSS_COMPILE\}ld$')
    write_json('source-content-inventory.json',dict(provider_package=source_info,
        source0_archive=TARBALL,source0_sha256=sha(source0[TARBALL][1]),source0_members=archive_rows,
        source_rpm_members=sorted(source0),provider_members=vendor_rows,makefiles=sorted(makefiles),
        prebuilt_findings=[],source_scope='entire contents of exact copied source-provider payload and wrapper Source0'))
    write_json('target-bindings.json',dict(metadata=metadata,target_package=target_info,
        manifest_path=manifest_path,manifest_binding=binding,provider_package_line=provider_wrote,
        provider_log_sha256=sha(provider_log),round1_full_log_path=log_path,full_log_sha256=sha(log),
        final_rpm_line=match_event(lines,850,855,r'\bWrote: .*/'+re.escape(NAME)+r'\.rpm$'),
        source_copy=match_event(lines,497,512,r'\+ cp -a /usr/src/linux-tizen-modules-source ./kernel$'),
        llvm=match_event(lines,548,573,r'\+ export LLVM=1$'),
        parent_make_ld_assignment=ld_assign,rows=module_rows))
    print('Verified source provider, wrapper SPEC, seven final links/install events/filelists and 7 device/payload SHA256 bindings.')
    if args.binutils_rpm is None:
        return
    binutils_path=args.binutils_rpm.resolve()
    binutils=package_from_primary(base/paths['base_primary'],'binutils','armv7l','2.43','1.8')
    binutils_info=verify_rpm(binutils_path,binutils,'binutils')
    binutils_header = run('binutils-rpm-fileheaders',['rpm','-qp','--qf',
        '[%{FILENAMES}\t%{FILEINODES}\t%{FILEDEVICES}\t%{FILESIZES}\t%{FILEDIGESTS}\n]',binutils_path])
    headers = {fields[0]:fields[1:] for fields in
                (line.split('\t') for line in binutils_header.decode().splitlines())}
    hardlinks = {}
    binutils_members=newc('binutils-cpio', binutils_path, hardlinks)
    wanted={}
    for name in LINKERS:
        path='usr/bin/'+name
        mode,body=binutils_members[path]
        target_info=member_row('/'+path,mode,body)
        target_info['rpm_inode'],target_info['rpm_device'],size,target_info['rpm_file_sha256'] = headers['/'+path]
        target_info['rpm_filesize']=int(size)
        target_info['cpio_hardlink']=hardlinks.get(path)
        if stat.S_ISLNK(mode):
            target_info['target']=body.decode()
        elif stat.S_ISREG(mode):
            require(len(body)==int(size) and sha(body)==target_info['rpm_file_sha256'],'binutils header/payload digest mismatch')
            target_info['elf_class']='ELF32' if body[4]==1 else 'ELF64'
            target_info['elf_machine']='ARM' if body[18:20]==b'\x28\x00' else body[18:20].hex()
            target_info['version_strings']=[m.group().decode() for m in re.finditer(
                rb'(?:GNU ld|GNU Binutils)[ -~]{0,96}',body)][:20]
        wanted['/'+path]=target_info
    ld, bfd = (wanted['/usr/bin/'+name] for name in LINKERS)
    require(ld['cpio_hardlink'] is not None and bfd['cpio_hardlink'] is not None and
            ld['rpm_inode']==bfd['rpm_inode'] and ld['rpm_device']==bfd['rpm_device'] and
            ld['sha256']==bfd['sha256'] and 'GNU Binutils) 2.43' in bfd['version_strings'],
            'binutils ld / ld.bfd relation did not match')
    write_json('historical-binutils-resolution.json',dict(package=binutils_info,
          ld_resolution='Hardlink to the same GNU BFD ARM ELF as /usr/bin/ld.bfd',
          historical_base_primary=paths['base_primary'],historical_log_evidence=match_event(
              lines,400,475,r'\bkeeping binutils-2\.43-1\.8$'),executable_paths=wanted))
    print(json.dumps(wanted,ensure_ascii=False))

if __name__=='__main__':
    main()
