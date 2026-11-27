#!/usr/bin/env python3
"""Parse actual packaged kernel config, preserving raw lines and SHA256."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
DEVEL = Path('evidence/build/devel/boot/kernel/devel/kernel-devel-arm-rpi4')
KEYS = (
    'CC_VERSION_TEXT', 'CC_IS_CLANG', 'CLANG_VERSION', 'CC_IS_GCC', 'GCC_VERSION',
    'LD_IS_LLD', 'LLD_VERSION', 'LD_IS_BFD', 'LD_VERSION', 'AS_IS_LLVM', 'AS_VERSION',
    'LTO', 'LTO_NONE', 'LTO_CLANG', 'LTO_CLANG_THIN', 'LTO_CLANG_FULL', 'IKCONFIG', 'IKCONFIG_PROC',
)
LINE = re.compile(r'(CONFIG_[A-Z0-9_]+)=(.*)$')
UNSET = re.compile(r'# (CONFIG_[A-Z0-9_]+) is not set$')

def sha_file(relative):
    with (ROOT / relative).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def parse(relative):
    values = {}
    for number, line in enumerate((ROOT / relative).read_text().splitlines(), 1):
        match = LINE.fullmatch(line)
        if match:
            key, value = match.groups()
            values[key] = {'state': 'set', 'value': value, 'line': number, 'raw': line}
            continue
        match = UNSET.fullmatch(line)
        if match:
            values[match[1]] = {'state': 'explicitly_unset', 'value': None, 'line': number, 'raw': line}
    expected_keys = {}
    for suffix in KEYS:
        key = f'CONFIG_{suffix}'
        expected_keys[key] = values.get(key, {'state': 'absent', 'value': None, 'line': None, 'raw': None})
    return {'evidence': str(relative), 'sha256': sha_file(relative), 'keys': expected_keys}

def normalized(value):
    raw = value['value']
    return raw.strip('"') if raw is not None else None

def main():
    actual = parse(DEVEL / '.config')
    autoconf = parse(DEVEL / 'include/config/auto.conf')
    baseline_config = parse(DEVEL / 'arch/arm/configs/tizen_bcm2711_defconfig')
    generated = [
        DEVEL / f'include/generated/{name}.h'
        for name in ('compile', 'utsrelease', 'utsversion')
    ]
    records = {
        'actual_config': actual,
        'generated_auto_conf': autoconf,
        'cross_check': {
            key: normalized(actual['keys'][key]) == normalized(autoconf['keys'][key])
            for key in actual['keys']
        },
        'source_baseline_defconfig': baseline_config,
        'generated_headers': [
            {'evidence': str(path), 'sha256': sha_file(path), 'raw': (ROOT / path).read_text()}
            for path in generated
        ],
    }
    if not all(records['cross_check'].values()):
        raise ValueError('Selected .config and auto.conf keys have different values')
    dest = ROOT / 'evidence/build/packaged-config-values.json'
    dest.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    print(f"{len(records['cross_check'])} selected .config and auto.conf values cross-checked")

if __name__ == '__main__':
    main()
