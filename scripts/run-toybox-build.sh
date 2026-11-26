#!/usr/bin/env bash
# Build the diagnostic spec in a dedicated GBS root for each architecture.
set -euo pipefail
if (( $# != 1 )); then
    echo "Usage: $0 PREPARED_WORK_DIRECTORY" >&2
    exit 2
fi
work=$(realpath "$1")
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname -- "$here")
archive="$root/evidence/2026-11-23"
test -f "$work/gbs.conf"
git -C "$work/source" apply --reverse --check "$here/toybox-linker-verbose.patch"
mkdir -p "$root/results"
result=${AUDIT_RESULTS:-$(mktemp -d "$root/results/$(TZ=America/Los_Angeles date +%F)-toybox.XXXXXX")}
mkdir -p "$result"
result=$(realpath "$result")
printf 'Result directory: %s\n' "$result"

cpus=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:2])))')
cd "$work/source"
status=0
for arch in aarch64 armv7l; do
    if taskset -c "$cpus" gbs -c "$work/gbs.conf" build -A "$arch" \
        --include-all --threads=1 --define 'jobs 2' --define '_smp_mflags -j2' \
        -B "$work/gbs-$arch" |& tee "$work/gbs-$arch.log"; then
        find "$work/gbs-$arch" -type f \( -name '.build.log' -o -name '*toybox*.rpm' \) -print
    else
        status=$?
        printf '%s GBS exited with status %s\n' "$arch" "$status" >&2
    fi
    cp "$work/gbs-$arch.log" "$result/"
done

case "$(sed -n 's|^url=.*tizen-base-toolchain_\([^/]*\)/.*|\1|p' "$work/gbs.conf")" in
    20261119.042539) expected="$archive/toybox/toybox-identities.tsv" ;;
    20261117.165617) expected="$archive/toybox-qb1234653/toybox-identities.tsv" ;;
    *) expected='' ;;
esac
if [[ -n $expected ]]; then
    python3 "$here/collect-toybox-build.py" "$work" --expected "$expected" --out "$result" || status=$?
    printf 'Linker and ELF SHA256 comparison saved in %s/result.json\n' "$result"
fi
printf '%s\n' "$status" > "$result/exit-code.txt"
exit "$status"
