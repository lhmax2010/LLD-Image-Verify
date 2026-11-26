#!/usr/bin/env python3
"""Match unresolved speech-engine ELF files to prebuilt members of SRPMs."""
import argparse
import csv
import hashlib
import subprocess
import tarfile
import tempfile
from pathlib import Path


def collect(args):
    projects = ('stt-engine-default', 'vc-engine-default')
    with args.elf_table.open() as stream:
        rows = [row for row in csv.DictReader(stream, delimiter='\t')
                if row['classification'] == 'unresolved' and row['source'].endswith(projects)]
    unique = {row['sha256']: row for row in rows}
    fields = ('source', 'source_commit', 'machine', 'path', 'build_id', 'sha256', 'debuglink',
              'debug_crc', 'source_rpm', 'source_tar_member', 'source_elf_sha256',
              'elf_byte_match', 'source_comment')
    with args.output.open('w') as output:
        writer = csv.DictWriter(output, fields, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        for rpm in args.srpm:
            with tempfile.TemporaryDirectory(prefix='voice-source-') as scratch:
                with subprocess.Popen(['rpm2cpio', rpm.resolve()], stdout=subprocess.PIPE) as pipe:
                    subprocess.run(['cpio', '-id', '--quiet'], cwd=scratch, stdin=pipe.stdout, check=True)
                    if pipe.wait():
                        raise RuntimeError(f'Failed to extract {rpm}')
                archive_path, = Path(scratch).glob('*.tar.gz')
                with tarfile.open(archive_path) as archive:
                    members = archive.getmembers()
                    for row in unique.values():
                        pkg = row['source'].rsplit('/', 1)[-1]
                        if pkg not in rpm.name:
                            continue
                        relative = Path(row['path']).relative_to(f'/usr/apps/org.tizen.{pkg}')
                        role, filename = relative.parts
                        arch = 'aarch64' if row['machine'] == 'aarch64' else 'arm'
                        names = [arch] if arch == 'aarch64' else ['arm', 'armv7l']
                        suffixes = [f'/{role}/{name}/{filename}' for name in names]
                        candidates = [m for m in members if m.name.endswith(tuple(suffixes))]
                        if not candidates:
                            raise ValueError(f'Could not locate {row["path"]} in {rpm}')
                        for member in candidates:
                            with archive.extractfile(member) as stream:
                                binary = stream.read()
                            member_file = Path(scratch) / 'candidate.elf'
                            member_file.write_bytes(binary)
                            comment = subprocess.check_output(
                                ['readelf', '-p', '.comment', member_file], stderr=subprocess.DEVNULL,
                                text=True).splitlines()
                            comment = [line.split(']', 1)[1].strip()
                                       for line in comment if line.lstrip().startswith('[')]
                            sha256 = hashlib.sha256(binary).hexdigest()
                            writer.writerow({**row, 'source_rpm': rpm.name,
                                'source_tar_member': member.name, 'source_elf_sha256': sha256,
                                'elf_byte_match': sha256 == row['sha256'],
                                'source_comment': ' | '.join(comment)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf-table', type=Path, required=True)
    parser.add_argument('--srpm', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args())
