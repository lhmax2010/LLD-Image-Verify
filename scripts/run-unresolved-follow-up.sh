#!/usr/bin/env bash
# Recreate the supplemental proof from the two archived Base/Unified snapshots.
set -euo pipefail

if [[ $# != 4 ]]; then
    echo "Usage: $0 LATEST_IMAGE_WORK OLD_IMAGE_WORK LATEST_GBS_WORK OLD_GBS_WORK" >&2
    exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
output=$(mktemp -d "$PWD/results/unresolved-replay.XXXXXX")
scratch=$(mktemp -d "${TMPDIR:-/tmp}/unresolved-replay.XXXXXX")
printf 'Results %s\nScratch %s\n' "$output" "$scratch"
latest_image=$1
old_image=$2
latest_gbs=$3
old_gbs=$4
base=https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain

for run in latest qb1234653; do
    if [[ $run == latest ]]; then
        snapshot=20261119.042539
        images=$latest_image
        gbs=$latest_gbs
    else
        snapshot=20261117.165617
        images=$old_image
        gbs=$old_gbs
    fi
    for arch in aarch64 armv7l; do
        libdir=lib
        [[ $arch != aarch64 ]] || libdir=lib64
        image="$images/extracted/tizen-headed-$arch/rootfs"
        root="$gbs/gbs-$arch/local/BUILD-ROOTS/scratch.$arch.0"
        archive="$PWD/evidence/2026-11-23/$run/logs/base/$arch"
        for package in bzip2 zip; do
            log="$archive/$package.txt.gz"
            rpm=$(gzip -dc "$log" | awk -F/ '/Wrote: .*SRPMS/ && !seen++ { print $NF }')
            rpm_file="$scratch/$run-$arch-$rpm"
            curl -fsSL "$base/tizen-base-toolchain_$snapshot/repos/standard/source/$rpm" -o "$rpm_file"
            args=(--root "$root" --srpm "$rpm_file" --build-log "$log"
                  --work "$scratch/$package-$run-$arch" --output "$output/$package/$run/$arch")
            if [[ $package == bzip2 ]]; then
                python3 scripts/replay-base-link-candidate.py "${args[@]}" --elf "$image/usr/$libdir/libbz2.so.1.0.8"
            else
                python3 scripts/replay-zip-link.py "${args[@]}" --image-bin "$image/usr/bin"
            fi
        done
        log="$images/buildlogs/base/$arch/glibc.buildlog.txt"
        rpm=$(awk -F/ '/Wrote: .*\/RPMS\/.*\/glibc-[0-9]+\.[0-9]+-[0-9.]+\.(aarch64|armv7l)\.rpm$/ { print $NF }' "$log")
        rpm_url="$base/tizen-base-toolchain_$snapshot/repos/standard/packages/$arch/$rpm"
        rpm_file="$scratch/$run-$arch-$rpm"
        curl -fsSL "$rpm_url" -o "$rpm_file"
        python3 scripts/probe-glibc-post-upgrade.py --log "$log" --root "$root" --rpm "$rpm_file" \
            --elf "$image/usr/sbin/glibc_post_upgrade" --rpm-url "$rpm_url" --output "$output/glibc/$run/$arch"
    done
done

for arch in aarch64 armv7l; do
    image="$latest_image/extracted/tizen-headed-$arch/rootfs"
    python3 scripts/probe-dart-aot-elf.py "$image/usr/apps/org.tizen.homescreen/lib/libapp.so" \
        "$latest_image/trace/homescreen-$arch.tpk" > "$output/dart-$arch.json"
done

unified=https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain
voice_rpms=()
for rpm in org.tizen.stt-engine-default-1.100.3-1.src.rpm org.tizen.vc-engine-default-1.90.1-1.src.rpm; do
    curl -fsSL "$unified/tizen-unified-toolchain_20261120.082536/repos/standard/source/$rpm" -o "$scratch/$rpm"
    voice_rpms+=("$scratch/$rpm")
done
python3 scripts/check-voice-srpm.py --elf-table statistics/latest/elf-results.tsv \
    --srpm "${voice_rpms[@]}" --output "$output/voice-source-provenance.tsv"
python3 scripts/reconcile-unresolved-round.py --statistics statistics --proofs "$output"
