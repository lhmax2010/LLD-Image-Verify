#!/usr/bin/env bash
# Extract only named, inert build evidence from checksummed local RPM files.
set -euo pipefail

destination=$1
package=$2
shift 2

mkdir -p "$destination"
rpm2cpio "$package" | cpio -idu --no-absolute-filenames --no-preserve-owner -D "$destination" "$@"
for member in "$@"; do
    [[ -f "$destination/$member" && ! -L "$destination/$member" ]]
done
