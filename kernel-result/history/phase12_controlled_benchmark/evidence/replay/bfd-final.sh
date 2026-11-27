set -eu
cd /boot/kernel/devel/kernel-devel-arm-rpi4
( cd /boot/kernel/devel/kernel-devel-arm-rpi4
exec -a ld.lld /emul/usr/bin/lld -r -EL -z noexecstack --build-id=sha1 -T scripts/module.lds -o /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/kdbus.ko /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/kdbus.o /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/kernel/kdbus/kdbus.mod.o /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/kernel/.module-common.o
)
LLVM_OBJCOPY=llvm-objcopy /mnt/entry/pahole -J -j1 --btf_features=encode_force,var,float,enum64,decl_tag,type_tag,optimized_func,consistent_func,decl_tag_kfuncs --lang_exclude=rust --btf_features=distilled_base --btf_base vmlinux /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/kdbus.ko
./tools/bpf/resolve_btfids/resolve_btfids -b vmlinux /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/kdbus.ko
cp /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/kdbus.ko /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/stripped/kdbus.ko
cd /boot/kernel/devel/kernel-devel-arm-rpi4
exec -a llvm-strip /emul/usr/bin/llvm-objcopy --strip-debug /home/abuild/rpmbuild/BUILD/linux-tizen-modules-11.0.0/replayed/bfd/stripped/kdbus.ko
