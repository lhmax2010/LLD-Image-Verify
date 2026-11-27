#!/usr/bin/env bash
# Replay the original Base inputs verification and read the historical packaging script.
set -euo pipefail

base=https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_20261119.042539/repos/standard/packages
folder=evidence/build/historical-base
mkdir -p "$folder"
primary=e315be17d10e5403940fad6e0ec3a4de44e34cd9c62cd27f8612df54a3e18096-primary.xml.gz
for record in "index repomd.xml" "primary $primary"; do
    read -r name path <<< "$record"
    python3 scripts/record.py --timeout 35 "build/historical-base-$name" curl -fLsS --max-time 30 \
        --dump-header "evidence/build/historical-base-$name.headers" "$base/repodata/$path" > /dev/null
done
python3 scripts/record.py build/historical-base-packages python3 scripts/match_build_environment.py
python3 scripts/record.py build/historical-base-accelerator python3 scripts/match_build_environment.py clang-accel-x86_64-armv7l
while IFS=$'\t' read -r name arch version release location unused; do
    [[ $name == /* ]] && continue
    python3 scripts/record.py --timeout 35 "build/historical-base/download-$name-$version-$release" \
        curl -fLsS --max-time 30 --dump-header "$folder/download-$name-$version-$release.headers" \
        -o "$folder/${location##*/}" "$base/$location"
done < evidence/build/historical-base-packages.out
python3 scripts/record.py build/historical-base-package-checks bash scripts/verify_historical_base.sh
python3 scripts/record.py build/historical-base-llvm-payload rpm -qplv "$folder/llvm-22.1.8-1.6.armv7l.rpm" > /dev/null
python3 scripts/record.py build/historical-base-rpmbuild-payload rpm -qplv "$folder/rpm-build-4.14.1.1-1.8.armv7l.rpm" > /dev/null
python3 scripts/record.py build/historical-base-find-debuginfo-extract bash scripts/extract_build_evidence.sh \
    "$folder/rpm-build" "$folder/rpm-build-4.14.1.1-1.8.armv7l.rpm" ./usr/lib/rpm/find-debuginfo.sh ./usr/lib/rpm/debugedit
python3 scripts/record.py build/historical-base-reseed-script-lines rg -n -e 'build-id-seed|build_id_seed|debugedit' \
    "$folder/rpm-build/usr/lib/rpm/find-debuginfo.sh"
python3 scripts/record.py build/historical-base-debugedit-text bash -o pipefail -c \
    'strings -a evidence/build/historical-base/rpm-build/usr/lib/rpm/debugedit | rg -i "build id|build.id|seed"'
