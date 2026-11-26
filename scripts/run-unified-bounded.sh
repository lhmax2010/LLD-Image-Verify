#!/usr/bin/env bash
# Put the command and all of its children in a resource-limited user scope.
set -eu
exec systemd-run --user --scope --quiet \
  -p CPUQuota=25% -p CPUWeight=10 \
  -p MemoryMax=1G -p MemorySwapMax=0 -p TasksMax=32 \
  nice -n 15 ionice -c 3 "$@"
