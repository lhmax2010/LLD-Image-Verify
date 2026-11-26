#!/usr/bin/env python3
"""Check the published image, build-log, and rule denominators."""
from collections import Counter
from importlib import import_module
from pathlib import Path
import re

image = import_module("export-image-evidence")
root = Path(__file__).resolve().parents[1]
data = root / "data"
sha256 = re.compile("[0-9a-f]{64}").fullmatch

for unified, _ in image.ROUNDS.values():
    instances = list(image.rows(data / f"image-instances-{unified}.csv"))
    native = [r for r in instances if r["evidence_class"] != "static-archive"]
    assert len(instances) == 10887 and len(native) == 10875
    assert len({r["sha256"] for r in native}) == 6014
    assert all(sha256(r["sha256"]) for r in native)
    assert len(image.identities(native)) == len(native)
    assert Counter(r["repository"] for r in native) == {"Unified": 7071, "Base": 3804}
    assert Counter(r["evidence_class"] for r in native) == {
        "lld-confirmed": 6892, "gnu-ld-confirmed": 140, "not-linked-by-our-toolchain": 103,
        "gnu-ld-like-layout": 3459, "lld-layout": 24, "not-lld-22.1.8": 234, "unresolved": 23
    }
    assert len([r for r in native if not r["rpm_nevra"] and r["rpm_owner_candidates"]]) == 10
    rpms = [r for r in image.rows(data / "image-rpm-verdicts.csv") if r["snapshot"].endswith(unified)]
    assert len(rpms) == 2556
    assert sum(int(r["native_instances"]) for r in rpms) == 10865

exceptions = list(image.rows(data / "unified-exceptions-by-rpm.csv"))
assert len({r["snapshot"] for r in exceptions}) == 2
assert sum(int(r["instances"]) for r in exceptions) == 358
owners = list(image.rows(root / "evidence/recovered-image-rpm-owners.csv"))
assert len(owners) == 32
assert all(r["sha256"] == r["rpm_payload_sha256"] and sha256(r["rpm_digest"]) for r in owners)

buildlogs = list(image.rows(data / "buildlogs.csv"))
assert len(buildlogs) == 7598 and all(not r["error"] and sha256(r["sha256"]) for r in buildlogs)
package_logs = list(image.rows(data / "buildlog-package-evidence.csv"))
assert {r["url"] for r in buildlogs} == {r["url"] for r in package_logs}
base = [r for r in package_logs if r["snapshot"].endswith("20261119.042539")]
assert len(base) == 779 and len({r["package"] for r in base}) == 264
assert sum(r["gcc_only_by_recipe"] == "yes" for r in base) == 16

for r in image.rows(data / "debuginfo-rule-summary.csv"):
    assert int(r["all_instances"]) == int(r["evaluated"]) + int(r["unpaired"])
    assert int(r["evaluated"]) == int(r["rule_fires"]) + int(r["rule_does_not_fire"])
print("Image and RPM identities, build-log coverage, and rule denominators verified")
