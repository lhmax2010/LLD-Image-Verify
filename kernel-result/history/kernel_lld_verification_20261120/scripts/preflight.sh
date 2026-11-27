#!/usr/bin/env bash
set -u
cd -- "$(dirname -- "$0")/.."
record() { python3 scripts/record.py "preflight/$1" "${@:2}"; }
record host-env bash -c 'date -u +%FT%TZ; TZ=America/Los_Angeles date +%FT%T%:z; uname -a; cat /etc/os-release; pwd'
record host-space df -hP . /tmp /opt/nvme-home
record host-route ip route get private-address-02
record host-tools bash -c '
for tool in sdb ssh curl wget rpm rpm2cpio cpio readelf llvm-readelf llvm-objdump objdump strings sha256sum file modinfo python3 gzip xz zstd pandoc markdown llvm-readelf-{14,15,16,17,18,19,20,21,22} llvm-objdump-{14,15,16,17,18,19,20,21,22}; do
    if tool_path=$(command -v "$tool"); then
        args=(--version)
        [[ $tool == ssh ]] && args=(-V)
        [[ $tool == file ]] && args=(-v)
        printf "%s\t%s\n" "$tool" "$tool_path"
        "$tool" "${args[@]}" 2>&1 | sed -n "1,3p"
        printf "version_exit=%s\n" "${PIPESTATUS[0]}"
    else
        printf "%s\tMISSING\n" "$tool"
    fi
done'
record sdb-devices timeout 8 sdb devices
