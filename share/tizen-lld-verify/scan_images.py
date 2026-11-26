"""Inventory ELF artifacts in the QB loop images without booting or mounting them."""
from collections import defaultdict
import csv
import gzip
import hashlib
from io import BytesIO
import json
import lzma
import mmap
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import tarfile
import tempfile
import zipfile

from config import WORK
TYPES = {1: 'REL', 2: 'EXEC', 3: 'DYN', 4: 'CORE'}
MACHINES = {3: 'i386', 40: 'arm', 62: 'x86_64', 137: 'VideoCore III', 183: 'aarch64', 243: 'riscv'}
FIELDS = ['image', 'partition', 'path', 'kind', 'machine', 'linker', 'evidence',
          'comments', 'build_id', 'sha256', 'debuglink', 'debug_crc', 'load_flags',
          'relro_delta', 'version_parent', 'rpm', 'source', 'source_commit']
MARKER = re.compile(rb'^Linker:\s+(LLD|GNU ld|GNU gold|mold)\b', re.I)
ZIP_SUFFIXES = {'.tpk', '.wgt', '.zip', '.jar', '.apk'}


def unpack(folder):
    profile = folder.name
    with (folder / 'manifest.json').open() as f:
        mounts = json.load(f)['loop']['partitions']
    images = WORK / 'partitions' / profile
    images.mkdir(parents=True, exist_ok=True)
    expected = {f'{part}.img' for part in mounts.values()}
    if not all((images / name).is_file() for name in expected):
        with tarfile.open(next(folder.glob('*.tar.gz')), 'r|gz') as archive:
            for member in archive:
                if member.name not in expected or not member.isfile():
                    raise ValueError(f'Unexpected image archive entry {member.name}')
                target = images / member.name
                if not target.is_file() or target.stat().st_size != member.size:
                    with tempfile.TemporaryDirectory(dir=images) as temporary:
                        archive.extract(member, path=temporary, filter='data')
                        (Path(temporary) / member.name).replace(target)
    for mount, part in mounts.items():
        image = images / f'{part}.img'
        output = WORK / 'extracted' / profile / part
        if part == 'user':
            with image.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
                signatures = (b'\x7fELF', b'PK\x03\x04', b'!<arch>\n',
                              b'\x1f\x8b\x08', b'\xfd7zXZ\x00', b'\x28\xb5\x2f\xfd')
                if not any(data.find(signature) >= 0 for signature in signatures):
                    continue
            raise ValueError(f'Candidate native payload in F2FS partition {image}')
        if not output.is_dir():
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f'.{part}-', dir=output.parent) as temporary:
                staging = Path(temporary) / 'files'
                staging.mkdir()
                extract_partition(image, part, staging)
                staging.rename(output)
        yield mount, part, output


def extract_partition(image, part, output):
    if part == 'boot':
        command = ['mcopy', '-s', '-i', str(image), '::*', str(output)]
    elif part.startswith('ramdisk'):
        command = ['unmkinitramfs', str(image), str(output)]
    else:
        command = ['debugfs', '-R', f'rdump / "{output}"', str(image)]
    result = subprocess.run(command, capture_output=True, text=True)
    unexpected = [line for line in result.stderr.splitlines()
                  if 'while changing ownership' not in line
                  and not line.startswith(('debugfs ', 'cpio: cannot mknod'))]
    if result.returncode or unexpected:
        detail = '\n'.join(unexpected[:12])
        raise RuntimeError(f'{image}: extraction failed (exit {result.returncode})\n{detail}')
    output.chmod(0o700)
    for directory, folders, files in os.walk(output):
        for entry in (*folders, *files):
            path = Path(directory) / entry
            if not path.is_symlink():
                mode = path.stat().st_mode
                path.chmod(mode | (0o700 if path.is_dir() else 0o400))


def package_owners(folder):
    packages = {}
    owners = defaultdict(set)
    for line in next(folder.glob('*.packages')).read_text().splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3:
            key = ' '.join(parts[:2])
            source, sep, sha = parts[2].partition('#')
            packages[key] = (source, sha if sep else '')
    ownership_files = list(folder.glob('*.files'))
    # Include boot-RPM inventory if available. /lib vs /usr/lib may be an alias.
    ownership_files.extend((WORK / 'rpm-filelists' / folder.name).glob('*.files'))
    for path in ownership_files:
        key = ''
        for line in path.read_text().splitlines():
            if line[:1].isspace():
                if key and (name := line.strip()).startswith('/'):
                    owners[name].add(key)
            else:
                key = line.strip()
    return packages, owners


def lookup(path, packages, owners):
    for name in (path, path.removeprefix('/usr') if path.startswith('/usr/') else '/usr'+path):
        if name in owners:
            keys = sorted(owners[name])
            return ('|'.join(keys),
                    '|'.join(sorted({packages.get(key, ('', ''))[0] for key in keys} - {''})),
                    '|'.join(sorted({packages.get(key, ('', ''))[1] for key in keys} - {''})))
    boot_kernel = re.match(r'/boot/(?:vmlinuz|zImage|Image|kernel[78](?:l)?)(?:[.-]|$)', path)
    is_module = path.startswith('/lib/modules/') and re.search(r'\.ko(?:\.(?:xz|gz|zst))?$', path)
    if is_module or boot_kernel:
        kernel = [key for key in packages if re.search(r'-linux-kernel' +
                  ('-modules' if is_module else '') + r'\.', key)]
        if len(kernel) == 1:
            key = kernel[0]
            return key, *packages[key]
    return '', '', ''


def scan_elf(f, metadata=None):
    ident = f.read(16)
    if ident[:4] != b'\x7fELF':
        return None
    if len(ident) != 16 or ident[4] not in (1, 2) or ident[5] not in (1, 2):
        raise ValueError('Invalid ELF class or data encoding')
    bits64 = ident[4] == 2
    endian = '<' if ident[5] == 1 else '>'
    header = struct.Struct(endian + ('HHIQQQIHHHHHH' if bits64 else 'HHIIIIIHHHHHH'))
    section = struct.Struct(endian + ('IIQQQQIIQQ' if bits64 else 'IIIIIIIIII'))
    e = header.unpack(f.read(header.size))
    elf_type, machine, offset, entry_size, count, str_index = e[0], e[1], e[5], e[10], e[11], e[12]
    evidence = []
    comments = b''
    build_id = ''
    debuglink = debug_crc = version_parent = ''
    flags = []
    relro_delta = ''
    if e[4] and e[9]:
        pfmt = struct.Struct(endian + ('IIQQQQQQ' if bits64 else 'IIIIIIII'))
        f.seek(e[4])
        programs = f.read(e[8] * e[9])
        for k in range(e[9]):
            program = pfmt.unpack_from(programs, e[8] * k)
            pflags, filesz, memsz = (program[1], program[5], program[6]) if bits64 else (program[6], program[4], program[5])
            if program[0] == 1:
                flags.append(''.join(letter for bit, letter in ((4, 'R'), (2, 'W'), (1, 'X')) if pflags & bit))
            if program[0] == 0x6474e552:
                relro_delta = str(memsz - filesz)
    if offset and entry_size >= section.size:
        f.seek(offset)
        first = section.unpack(f.read(section.size))
        count = count or first[5]
        if str_index == 0xffff:
            str_index = first[6]
        if count > 100000 or str_index >= count:
            raise ValueError('Invalid ELF section table')
        f.seek(offset)
        table = f.read(count * entry_size)
        sections = [section.unpack_from(table, i * entry_size) for i in range(count)]
        def contents(record, limit=1048576):
            f.seek(record[4])
            if record[5] > limit:
                raise ValueError('Unusually large ELF metadata section')
            return f.read(record[5])
        names = contents(sections[str_index])
        for record in sections:
            start = record[0]
            end = names.find(b'\0', start)
            name = names[start:end] if end >= start else b''
            if metadata is not None and name == b'.note.gnu.gold-version':
                metadata['gold_note'] = True
            if name == b'.comment' and record[1] != 8:
                comments = contents(record)
            elif name == b'.gnu_debuglink':
                data = contents(record)
                end = data.find(b'\0')
                crc_offset = (end + 4) & ~3
                if end > 0 and crc_offset + 4 <= len(data):
                    debuglink = data[:end].decode(errors='replace')
                    debug_crc = f'{struct.unpack_from(endian + "I", data, crc_offset)[0]:08x}'
            elif name == b'.gnu.version_d' and record[1] != 8:
                data = contents(record)
                pos = 0
                while pos + 20 <= len(data):
                    _, _, _, count, _, _, step = struct.unpack_from(endian+'HHHHIII', data, pos)
                    if count > 1:
                        version_parent = 'yes'
                        break
                    if step < 20:
                        break
                    pos += step
            elif name == b'.note.gnu.gold-version' and b'GNU gold' in contents(record):
                evidence.append(('GNU gold', '.note.gnu.gold-version'))
            elif name == b'.note.gnu.build-id':
                note = contents(record)
                if len(note) >= 16:
                    namesz, descsz, typ = struct.unpack_from(endian + 'III', note)
                    begin = 12 + ((namesz + 3) & ~3)
                    if typ == 3 and note[12:16] == b'GNU\0':
                        build_id = note[begin:begin + descsz].hex()
            elif name == b'.note.go.buildid':
                evidence.append(('', '.note.go.buildid'))
    strings = [p.strip() for p in comments.split(b'\0') if p.strip()]
    for value in strings:
        match = MARKER.match(value)
        if match:
            evidence.append((match[1].decode(), value.decode(errors='replace')))
        elif value.startswith(b'MetaWare Linker '):
            evidence.append(('MetaWare Linker', value.decode(errors='replace')))
        elif value.startswith(b'mold '):
            evidence.append(('mold', value.decode(errors='replace')))
    IDs = {linker for linker, _ in evidence if linker}
    linker = next(iter(IDs)) if len(IDs) == 1 else 'conflicting' if IDs else 'unknown'
    if not IDs and not evidence:
        evidence = [('', '.comment without linker ID' if comments else 'no .comment')]
    f.seek(0)
    return (TYPES.get(elf_type, str(elf_type)), MACHINES.get(machine, str(machine)), linker,
            ' | '.join(value for _, value in evidence),
            ' | '.join(s.decode(errors='replace').replace('\n',' ') for s in strings),
            build_id, hashlib.file_digest(f, 'sha256').hexdigest(), debuglink, debug_crc,
            ','.join(flags), relro_delta, version_parent)


def handle_file(name, f):
    ident = f.read(8)
    f.seek(0)
    if ident.startswith(b'\x7fELF'):
        scanned = scan_elf(f)
        if scanned:
            yield name, scanned
    elif ident in (b'!<arch>\n', b'!<thin>\n'):
        yield name, ('archive', '', 'not-applicable', 'ar archive', '', '', '', '', '', '', '', '')
    elif PurePosixPath(name).suffix.lower() in ZIP_SUFFIXES and ident[:2] == b'PK':
        with zipfile.ZipFile(f) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                with archive.open(member) as entry:
                    prefix = entry.read(4)
                    if prefix == b'\x7fELF':
                        scanned = scan_elf(BytesIO(prefix + entry.read()))
                        if scanned:
                            yield f'{name}!/{member.filename}', scanned


def scan_image(folder):
    packages, owners = package_owners(folder)
    report = WORK / 'observed'
    report.mkdir(exist_ok=True)
    problems = []
    rows = 0
    with (report / f'{folder.name}.tsv').open('w', newline='') as out:
        writer = csv.writer(out, delimiter='\t')
        writer.writerow(FIELDS)
        for mount, part, root in unpack(folder):
            for parent, dirs, names in os.walk(root):
                dirs.sort()
                for name in sorted(names):
                    local = Path(parent) / name
                    if name == '.scan-extracted' or local.is_symlink() or not local.is_file():
                        continue
                    path = mount.rstrip('/') + '/' + str(local.relative_to(root))
                    package = lookup(path, packages, owners)
                    try:
                        if name.endswith('.ko.xz'):
                            blob = lzma.open(local).read()
                        elif name.endswith('.ko.gz'):
                            blob = gzip.open(local).read()
                        elif name.endswith('.ko.zst'):
                            blob = subprocess.check_output(['zstd', '-dc', local])
                        else:
                            blob = None
                        f = BytesIO(blob) if blob is not None else local.open('rb')
                        with f:
                            for inner, info in handle_file(path, f):
                                writer.writerow((folder.name, part, inner, *info, *package))
                                rows += 1
                    except (OSError, ValueError, struct.error, zipfile.BadZipFile, RuntimeError) as exc:
                        problems.append((path, str(exc)))
    (report / f'{folder.name}-issues.json').write_text(json.dumps(problems, indent=2))
    print(f'{folder.name}: {rows} ELF/archive entries, {len(problems)} read issues', flush=True)
