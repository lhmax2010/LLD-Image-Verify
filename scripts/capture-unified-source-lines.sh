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
