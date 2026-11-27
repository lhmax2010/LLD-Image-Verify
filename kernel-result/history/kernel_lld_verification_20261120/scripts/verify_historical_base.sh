#!/usr/bin/env bash
# Check the exact historical builder dependencies, without installing or executing them.
set -euo pipefail

folder=evidence/build/historical-base
case_count=0
while IFS=$'\t' read -r name arch version release location expected_sha expected_size; do
    [[ $name == /* ]] && continue
    package="$folder/${location##*/}"
    got=$(sha256sum "$package")
    got=${got%% *}
    actual_size=$(stat -c %s "$package")
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$package" "$got" "$actual_size" "$version-$release.$arch"
    [[ $got == "$expected_sha" && $actual_size == "$expected_size" ]]
    case_count=$((case_count + 1))
done < evidence/build/historical-base-packages.out
test "$case_count" -eq 3
