#!/usr/bin/env python3
"""Print the modeled linker selection and arguments without touching any target."""
import json
import sys

stage, linker, *arguments = sys.argv[1:]
print("PHASE9_MOCK|" + json.dumps(dict(stage=stage, modeled_argv=[linker,*arguments], actual_linker_executed=False)))
