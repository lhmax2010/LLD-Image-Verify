#!/usr/bin/env bash
# Operate on the sealed evidence or replay into a new work directory.
set -euo pipefail
src=$(cd -- "$(dirname -- "$0")" && pwd)
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1
usage() {
  cat <<'EOF'
Usage
  bash verify.sh check
  bash verify.sh replay NEW_DIRECTORY
  bash verify.sh capture NEW_DIRECTORY
  bash verify.sh refresh NEW_DIRECTORY

check    Validate the archived evidence without network access.
replay   Recompute analysis from archived inputs in a new directory.
capture  Recollect from the authorized SDB target, then recompute.
refresh  Recollect the SDB target and the pinned repository, profiles and logs.
EOF
}
mode=check
if (( $# )); then mode=$1; fi
case "$mode" in
  check)
    [[ $# -le 1 ]] || { usage; exit 2; }
    cd -- "$src"
    exec python3 scripts/check_bundle.py
    ;;
  replay|capture|refresh) ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 2 ;;
esac
[[ $# -eq 2 ]] || { usage; exit 2; }
destination=$(realpath -m -- "$2")
[[ ! -e "$destination" && ! -L "$destination" && "$destination" != "$src" && "$destination" != "$src/"* ]] || {
  printf 'Choose a new destination outside %s\n' "$src" >&2
  exit 2
}
(cd -- "$src" && python3 scripts/check_bundle.py)
mkdir -- "$destination"
cp -a --reflink=auto -- "$src/." "$destination"
cd -- "$destination"
record() {
  local timeout=$1 stem=$2
  shift 2
  python3 scripts/record.py --timeout "$timeout" "$stem" "$@"
}
if [[ $mode != replay ]]; then
  record 120 preflight/refresh-host bash scripts/preflight.sh
  record 900 runtime/recapture python3 scripts/capture_runtime.py
else
  record 120 runtime/offline-replay python3 scripts/parse_runtime.py
fi
if [[ $mode == refresh ]]; then
  record 900 repository/refresh python3 scripts/repository.py --refresh
  record 700 repository/image-refresh python3 scripts/repository_image.py --refresh
  record 120 build/log-refresh bash scripts/fetch_build_logs.sh
else
  record 360 repository/recompute-rpm python3 scripts/repository.py --replay
  record 120 repository/recompute-images python3 scripts/repository_image.py
fi
record 360 build/recompute-config-extraction bash scripts/collect_build_rpm_evidence.sh
record 120 build/recompute-config python3 scripts/build_config_evidence.py
record 120 build/recompute-log-index python3 scripts/build_log_evidence.py
record 360 kernel_binary/analysis-run python3 scripts/analyze_artifacts.py
record 120 kernel_binary/byte-comparison-run python3 scripts/compare_kernel_bytes.py
record 120 build/recompute-phase4 python3 scripts/summarize_build_evidence.py
record 120 repository/recompute-phase2 python3 scripts/report_repository.py
record 120 preflight/generate-reports python3 scripts/create_reports.py
record 600 preflight/self-check python3 scripts/check_bundle.py --seal
