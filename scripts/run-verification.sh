#!/usr/bin/env bash
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname -- "$here")
old=${AUDIT_BASELINE_WORK:-"$root/../qb-1234653-linker-audit"}
initial="$root/evidence/qb1234653-initial"
archive="$root/evidence/2026-11-23"
work=${AUDIT_WORK:-${TMPDIR:-/tmp}/tizen-lld-20261120.082536}
probe=${AUDIT_PROBE_WORK:-${TMPDIR:-/tmp}/tizen-lld-base-probe-20261117}
latest_probe=${AUDIT_LATEST_PROBE_WORK:-${TMPDIR:-/tmp}/tizen-lld-base-probe-20261119}
mkdir -p "$root/results"
out=${AUDIT_RESULTS:-$(mktemp -d "$root/results/$(TZ=America/Los_Angeles date +%F)-replay.XXXXXX")}
mkdir -p "$work" "$out" "$out/ps3" "$out/inputs"
work=$(realpath "$work")
probe=$(realpath -m "$probe")
out=$(realpath "$out")
printf 'Result directory: %s\n' "$out"
unified_build=tizen-unified-toolchain_20261120.082536
base_build=tizen-base-toolchain_20261119.042539
unified="https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/$unified_build/"
base="https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/$base_build/"

original() {
    python3 -u "$here/trace-linkers.py" --audit-dir "$old" --output "$out/qb1234653" --all-base-logs --jobs 2
}

image() {
    local status=0
    python3 "$here/audit-snapshot.py" --expect-ps3 --reuse-audit "$initial" --jobs 2 \
        --work-dir "$work" || status=$?
    python3 "$here/save-scan-evidence.py" "$work" "$out/image"
    return "$status"
}

latest_summary() {
    python3 -u "$here/trace-linkers.py" --audit-dir "$work" --unified "$unified" --base "$base" \
        --output "$out/latest" --all-base-logs --jobs 2
    local base_manifest="$out/inputs/${base_build}_standard.xml"
    curl -fsSL --retry 2 "$base/builddata/manifest/${base_build}_standard.xml" -o "$base_manifest"
    python3 "$here/check-scope.py" --commits "$archive/inputs/expected-qb-commits.txt" \
        --manifest "$work/raw/${unified_build}_standard.xml" --manifest "$base_manifest" \
        --elf "$out/latest/elf-results.tsv" --output "$out/latest-scope.tsv"
}

samples() {
    # Use a separate cache so that these RPM downloads do not collide with the bulk audit.
    local sample_work="${work}-samples"
    mkdir -p "$sample_work"
    ln -sfn "$work/extracted" "$sample_work/extracted"
    python3 "$here/audit-snapshot.py" --expect-ps3 --sample-only --work-dir "$sample_work"
    cp "$sample_work"/sample-*.tsv "$out/ps3/"
    python3 "$here/check-ps3-identity.py" --previous "$initial/elf-linker-audit.tsv" \
        --samples "$out/ps3" --output "$out/ps3/identity.tsv"
}

controls() {
    python3 "$here/probe-linkers.py" --image-audit "$old" --out "$probe"
    python3 "$here/probe-linkers.py" --base "$base" --image-audit "$work" --out "$latest_probe"
    for arch in aarch64 armv7l; do
        mkdir -p "$out/base-probe/$arch" "$out/latest-base-probe/$arch"
        cp "$probe/$arch/"*.txt "$probe/$arch/inputs.json" "$out/base-probe/$arch/"
        cp "$latest_probe/$arch/"*.txt "$latest_probe/$arch/inputs.json" "$out/latest-base-probe/$arch/"
    done
}

abi() {
    python3 "$here/compare-contract.py" --output "$out/contracts"
}

loader() {
    python3 "$here/check-loader.py" --image-audit "$work" --out "$out/loader"
}

symbols() {
    python3 "$here/check-symbol-load.py" --image-audit "$work" --tool-probe "$probe" \
        --contracts "$out/contracts" --output "$out/symbol-load"
}

importers() {
    local roots=(
        "--root=llvm-headed-aarch64=$work/extracted/tizen-headed-aarch64/rootfs"
        "--root=llvm-headed-armv7l=$work/extracted/tizen-headed-armv7l/rootfs"
    )
    if [[ -n ${VD_ROOT:-} ]]; then roots+=("--root=vd-headless-armv7l=$VD_ROOT"); fi
    python3 "$here/check-importers.py" --contracts "$out/contracts/contracts.json" \
        "${roots[@]}" --output "$out/consumer-imports.json"
}

case "${1:-all}" in
    all)
        original |& tee "$out/original-run.log"
        image |& tee "$out/image-run.log"
        latest_summary |& tee "$out/latest-summary-run.log"
        samples |& tee "$out/ps3-run.log"
        controls |& tee "$out/controls-run.log"
        abi |& tee "$out/abi-run.log"
        loader |& tee "$out/loader-run.log"
        symbols |& tee "$out/symbols-run.log"
        importers |& tee "$out/importers-run.log"
        ;;
    original|image|latest_summary|samples|controls|abi|loader|symbols|importers)
        task=$1
        "$task" |& tee "$out/$task-run.log"
        ;;
    *)
        echo "Usage: $0 [all|original|image|latest_summary|samples|controls|abi|loader|symbols|importers]" >&2
        exit 2
        ;;
esac
