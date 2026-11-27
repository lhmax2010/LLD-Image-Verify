#!/usr/bin/env bash
set -eu
uname -a
lscpu
free -h
df -h "$PWD"
taskset -pc $$
printf '%s\n' 'Cgroups'
for name in cpu.max memory.max pids.max; do
  if [[ -r /sys/fs/cgroup/$name ]]; then cat "/sys/fs/cgroup/$name"; fi
done
make --version | sed -n '1p'
rpm --version
python3 --version
readelf --version | sed -n '1p'
strace --version | sed -n '1p'
bwrap --version
strace -qq -e trace=execve,exit_group /usr/bin/true
