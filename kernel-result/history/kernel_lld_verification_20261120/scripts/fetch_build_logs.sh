#!/usr/bin/env bash
# Obtain the successful ARMv7l build logs from the exact snapshot, via HTTPS.
set -euo pipefail
base=https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536
for package in linux-rpi linux-tizen-modules; do
    python3 scripts/record.py --timeout 45 "build/${package}-armv7l" curl -fLsS --max-time 40 --retry 1 \
        --dump-header "evidence/build/${package}-armv7l.headers" \
        "$base/builddata/buildlogs/standard/armv7l/succeeded/$package.buildlog.txt" > /dev/null
done
