# These are parse-time observations of the isolated experiment.
# CASE_STAGE is fixed by the caller. No compiler or real linker is invoked.
trace_ld = $(info PHASE9_LD|$(1)|$(MAKELEVEL)|$(origin LD)|$(flavor LD)|$(value LD)|$(LD)|$(origin LLVM)|$(LLVM)|$(CROSS_COMPILE)|$(MAKEFLAGS)|$(MAKEOVERRIDES))
