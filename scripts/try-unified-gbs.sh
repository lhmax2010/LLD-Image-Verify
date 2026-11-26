#!/usr/bin/env bash
# Trial a source RPM through GBS using the pinned Unified profile.
set -eu
work=$(realpath "$1")
arch=$2
source_dir=$(realpath "$3")
archdir="$work/$arch"
mkdir -p "$archdir"/{gbs,home,tmp,var-tmp,project/packaging}
cp -a "$source_dir/." "$archdir/project/packaging/"
git -C "$archdir/project" init -q
git -C "$archdir/project" add -f packaging
if ! git -C "$archdir/project" diff --cached --quiet; then
  git -C "$archdir/project" -c user.name='Unified Linker Replay' -c user.email='linker-replay@example.invalid' commit -qm "Import trial recipe"
fi
cat > "$archdir/gbs.conf" <<EOF
[general]
profile = profile.tizen_unified_standard
buildroot = $archdir/gbs

[profile.tizen_unified_standard]
repos = repo.base-standard, repo.unified-standard

[repo.base-standard]
url=https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base-Toolchain/tizen-base-toolchain_20261119.042539/repos/standard/packages/

[repo.unified-standard]
url=https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/repos/standard/packages/
EOF
spec=("$source_dir"/*.spec)
label=$(rpmspec -q --srpm --qf '%{NAME}-%{VERSION}-%{RELEASE}' "${spec[0]}")
export_dir="$archdir/gbs/local/sources/tizen_unified_standard/$label"
mkdir -p "$export_dir"
cp -a "$source_dir/." "$export_dir/"
command=(gbs -c "$archdir/gbs.conf" build -A "$arch" -P tizen_unified_standard
         -B "$archdir/gbs" --threads=1 --style tar --overwrite "$archdir/project")
printf '%q ' "${command[@]}"
printf '\n'
exec bwrap --unshare-user --uid 0 --gid 0 --unshare-pid --unshare-ipc --cap-add ALL \
  --ro-bind / / --bind "$archdir" "$archdir" --bind "$archdir/tmp" /tmp \
  --bind "$archdir/var-tmp" /var/tmp --tmpfs /run --ro-bind-try /run/systemd/resolve /run/systemd/resolve \
  --proc /proc --dev /dev --setenv HOME "$archdir/home" \
  "${command[@]}"
