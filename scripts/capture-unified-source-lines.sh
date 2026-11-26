#!/usr/bin/env bash
# Capture numbered recipe and ANGLE GN source statements from unpacked SRPMs.
set -eu
work=$(realpath "$1")
for n in nntrainer yaca onnxruntime openblas hdf5 lapack angle; do
  spec=("$work/recipes/sources/$n/"*.spec)
  printf '\n%s\n' "${spec[0]##*/}"
  rg -n '_toolchain_override|^%build|^export F9X|FC=gfortran|is_clang=false|Wno-error=stringop-overflow|CMAKE_.*FLAGS' "${spec[0]}"
done
for n in org.example.gbs-sample fluoride emuld nnfw mtp-initiator; do
  spec=("$work/provenance/sources/$n/"*.spec)
  printf '\n%s\n' "${spec[0]##*/}"
  rg -n 'build-native -a|strip -|gn gen --|liblc3/|^%build|^%prep|^%define strip_options|unrpm|^%files haltests|CMAKE_' "${spec[0]}"
done
archive="$work/recipes/sources/angle/angle-2.1.tar"
for f in BUILD.gn build/config/BUILDCONFIG.gn build/config/compiler/compiler.gni build/config/compiler/BUILD.gn build/toolchain/linux/BUILD.gn; do
  printf '\nANGLE %s\n' "$f"
  tar -xOf "$archive" "angle-2.1/$f" |
    rg -n 'angle_enable_abseil =|custom_toolchain|use_lld =|use_gold =|-fuse-ld=\b|aarch64-linux-gnu|toolprefix =.*tizen'
done
for n in u-boot u-boot-rpi4; do
  spec=("$work/u-boot-trials/sources/$n/"*.spec)
  archive=("$work/u-boot-trials/sources/$n/"*.tar.bz2)
  printf '\n%s\n' "${spec[0]##*/}"
  rg -n 'HOSTCC|make .*EXTRAVERSION|install -p .* (tools/env/fw_printenv|scripts/dtc/dtc)' "${spec[0]}"
  for f in Makefile scripts/Makefile.host tools/env/Makefile; do
    printf '\n%s %s\n' "$n" "$f"
    tar --occurrence=1 -xOf "${archive[0]}" "u-boot-2025.10/$f" |
      rg -n '^HOSTCC|^CC[[:space:]]|^LD[[:space:]]|override HOSTCC|^envtools:|cmd_host-cmulti'
  done
done
