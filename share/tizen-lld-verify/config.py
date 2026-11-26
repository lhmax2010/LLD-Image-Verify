"""Public repositories and profiles for Tizen QuickBuild 1234653."""
from pathlib import Path
import os

BUILD = 'tizen-unified-toolchain_20261119.012153'
UNIFIED = f'https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/{BUILD}/'
BASE = ('https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/'
        'tizen-base-toolchain_20261117.165617/')
SOURCES = {'unified': UNIFIED, 'base': BASE}
ARCHES = ('aarch64', 'armv7l')
PROFILES = tuple(f'tizen-{variant}-{arch}{suffix}'
                 for variant, suffix in (('headed', ''), ('headless', ''), ('boot', '-rpi'))
                 for arch in ARCHES)
WORK = Path(os.environ.get('TIZEN_LLD_AUDIT_WORK', 'tizen-lld-audit-work')).resolve()
