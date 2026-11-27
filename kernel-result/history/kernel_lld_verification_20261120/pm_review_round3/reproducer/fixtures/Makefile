# Reduced Tizen Kbuild top level for Phase 9. Only the LLVM/LD choice,
# export and recursive process boundaries are modeled.
MAKEFLAGS += -rR
include $(REPRO_DIR)/fixtures/trace.mk
$(call trace_ld,kbuild_top_before)

ifneq ($(LLVM),)
ifneq ($(filter %/,$(LLVM)),)
LLVM_PREFIX := $(LLVM)
else ifneq ($(filter -%,$(LLVM)),)
LLVM_SUFFIX := $(LLVM)
endif
LD = $(LLVM_PREFIX)ld.lld$(LLVM_SUFFIX)
else
LD = $(CROSS_COMPILE)ld
endif

export CROSS_COMPILE LD
$(call trace_ld,kbuild_top_selected)
.DEFAULT_GOAL := modules
.PHONY: modules objects modpost
objects:
	+$(MAKE) -f $(REPRO_DIR)/fixtures/Makefile.build M="$(M)" object_descend

modpost: objects
	+$(MAKE) -f $(REPRO_DIR)/fixtures/Makefile.modpost M="$(M)" modpost

modules: modpost
	+$(MAKE) -f $(REPRO_DIR)/fixtures/Makefile.modfinal module_final
