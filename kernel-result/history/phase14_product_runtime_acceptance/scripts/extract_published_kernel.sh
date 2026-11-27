#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
base=$PWD/evidence/release
rpm="$base/arm-rpi4-linux-kernel-6.12.80-0.armv7l.rpm"
expected=$(python3 -B - <<'PY'
import csv
from pathlib import Path
path=Path('../kernel_lld_verification_20261125/11A_RPM_INVENTORY.csv')
with path.open(newline='') as stream:
    row=next(r for r in csv.DictReader(stream) if r['role']=='KERNEL_IMAGE')
    print(row['published_checksum'])
PY
)
printf '%s  %s\n' "$expected" "$rpm" | sha256sum -c
rpm -qp --qf '%{NEVRA} %{SOURCERPM} %{VCS}\n' "$rpm"
rpm -qp --dump "$rpm" | awk '$1=="/boot/zImage" {print}'
(
  cd "$base"
  rpm2cpio "$rpm" | cpio -idmu --quiet --no-absolute-filenames './boot/zImage'
)
sha256sum "$base/boot/zImage"
