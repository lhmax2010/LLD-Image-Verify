#!/usr/bin/env bash
# Copy a validated RPM scan into the checkout's published data tables.
set -euo pipefail
scan=$(realpath "$1")
repo=$(cd "$(dirname "$0")/.." && pwd)
data="$repo/data"
report="$repo/docs/rpm-pass.md"
python3 "$repo/scripts/summarize-rpm-pass.py" --scan "$scan" --output "$data/rpm-coverage.csv" --report "$report"
for name in rpm-inventory rpm-pass; do
    gzip -nc "$scan/$name.csv" > "$data/$name.csv.gz"
done
for name in rpm-elf-evidence debuginfo-evidence; do
    cp "$scan/$name.csv.gz" "$data/$name.csv.gz"
done
gzip -t "$data/"{rpm-inventory,rpm-pass,rpm-elf-evidence,debuginfo-evidence}.csv.gz
python3 "$repo/scripts/validate-published-evidence.py"
