#!/usr/bin/env python3
"""Run the existing image audit against a pinned Unified snapshot."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import threading
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

KIT = Path(__file__).resolve().parents[1] / 'share' / 'tizen-lld-verify'
sys.path.insert(0, str(KIT))
import config
import match_debug
import scan_images
import summarize
import verify

PS3 = {
    'platform/core/system/deviced': '3c1560adc2d5854bf11582cdc9c4a2b0307a2fca',
    'platform/framework/web/wrtjs': 'b3d3f392df903e8928e04df59077cac86ac116e7',
}
CHECK_FRESH = {'/usr/bin/deviced', '/usr/sbin/deviced-request-shutdown', '/usr/bin/wrt-loader'}


def reuse_pairings(previous):
    matches = defaultdict(list)
    for path in sorted(previous.glob('debug-matches-*.jsonl')):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            matches[record['sha256']].append(record)
    if not matches:
        raise ValueError(f'No completed debuginfo matches in {previous}')
    original_match = match_debug.match_arch
    original_plan = match_debug.plan

    def audit_arch(arch, profiles, jobs):
        reused = {}

        def plan(rows):
            fresh = []
            for row in rows:
                candidates = matches.get(row['sha256'], [])
                if row['path'] in CHECK_FRESH or not candidates:
                    fresh.append(row)
                    continue
                for record in candidates:
                    reused[(record['sha256'], record['rpm'], record['debug_path'])] = record
            return original_plan(fresh)

        match_debug.plan = plan
        try:
            path, errors = original_match(arch, profiles, jobs)
        finally:
            match_debug.plan = original_plan
        with path.open('a') as f:
            for record in reused.values():
                f.write(json.dumps(record | {'pair_origin': 'previous byte-identical ELF'}) + '\n')
        print(f'{arch}: reused {len(reused)} prior exact ELF/debuginfo pairs', flush=True)
        return path, errors

    match_debug.match_arch = audit_arch


def enable_http_keepalive():
    import requests

    worker = threading.local()

    def run(pkg, candidates):
        repo, href, digest, _ = pkg
        folder = config.WORK / 'debug-cache' / repo
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / PurePosixPath(href).name
        url = match_debug.ROOTS[repo] + href
        if not path.is_file():
            if not hasattr(worker, 'session'):
                worker.session = requests.Session()
            temp = path.with_suffix('.part')
            for attempt in range(3):
                try:
                    with worker.session.get(url, stream=True, timeout=(12, 45)) as reply:
                        reply.raise_for_status()
                        with temp.open('wb') as f:
                            for block in reply.iter_content(262144):
                                f.write(block)
                    if verify.sha256(temp) != digest:
                        raise ValueError(f'{url}: RPM checksum mismatch')
                    temp.replace(path)
                    break
                except (OSError, ValueError):
                    if attempt == 2:
                        raise
                finally:
                    temp.unlink(missing_ok=True)
        with path.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
                raise ValueError(f'{path}: RPM checksum mismatch')
        return [(key, entry | {'rpm': url, 'repo': repo})
                for key, entry in match_debug.inspect_rpm(path, candidates)]

    match_debug.run = run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', default='tizen-unified-toolchain_20261120.082536')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--profile', action='append', choices=config.PROFILES)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--expect-ps3', action='store_true')
    parser.add_argument('--no-debuginfo', action='store_true')
    parser.add_argument('--reuse-audit', type=Path,
                        help='Reuse prior debuginfo matches for byte-identical runtime ELFs')
    parser.add_argument('--sample-only', action='store_true',
                        help='Recheck PS3 targets against the new RPMs and extracted headed images')
    options = parser.parse_args()
    work = options.work_dir.resolve()
    config.BUILD = options.snapshot
    config.UNIFIED = ('https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/'
                      f'{config.BUILD}/')
    metadata = verify.fetch(config.UNIFIED + 'build.xml', work / 'raw' / 'build.xml')
    build = ET.parse(metadata)
    if build.findtext('id') != config.BUILD:
        raise ValueError('Work directory belongs to a different snapshot')
    base = build.find('base_id')
    config.BASE = urljoin(base.get('url').replace('http:', 'https:', 1), base.text + '/')
    config.SOURCES = {'unified': config.UNIFIED, 'base': config.BASE}
    config.WORK = work
    for module in (scan_images, match_debug, summarize):
        module.WORK = work
    summarize.SOURCES = config.SOURCES
    summarize.UNIFIED = config.UNIFIED
    match_debug.ROOTS = {name: url + 'repos/standard/debug/'
                        for name, url in config.SOURCES.items()}
    manifest_name = f'{config.BUILD}_standard.xml'
    manifest = verify.fetch(config.UNIFIED + 'builddata/manifest/' + manifest_name,
                            work / 'raw' / manifest_name)
    projects = {r.get('name'): r.get('revision') for r in ET.parse(manifest).iter('project')}
    commits = {name: projects.get(name) for name in PS3}
    if options.expect_ps3 and commits != PS3:
        raise ValueError(f'Unexpected deviced/wrtjs revisions: {commits}')
    print(json.dumps({'unified': config.UNIFIED, 'base': config.BASE, 'revisions': commits}),
          flush=True)
    options.all = not options.profile
    if options.sample_only:
        verify.SAMPLES = (('deviced', '/usr/bin/deviced'),
                          ('deviced', '/usr/sbin/deviced-request-shutdown'),
                          ('wrtjs', '/usr/bin/wrt-loader'))
        for arch in config.ARCHES:
            root = work / 'extracted' / f'tizen-headed-{arch}' / 'rootfs'
            if not root.is_dir():
                raise ValueError(f'Missing headed rootfs: {root}')
            verify.sample_command(argparse.Namespace(arch=arch, image_root=root))
        return 0
    if not options.no_debuginfo:
        enable_http_keepalive()
    if options.reuse_audit and not options.no_debuginfo:
        reuse_pairings(options.reuse_audit.resolve())
    return verify.image_command(options)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError,
            subprocess.SubprocessError, ET.ParseError) as exc:
        sys.exit(f'Error: {exc}')
