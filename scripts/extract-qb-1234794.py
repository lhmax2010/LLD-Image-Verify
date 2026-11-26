#!/usr/bin/env python3
"""Retain QuickBuild scheduling and project configuration lines for this audit."""
import argparse
from pathlib import Path
import re

RANGES = ((6, 7), (12, 13), (55, 55), (209, 209), (369, 369), (383, 384),
          (1183, 1184), (1251, 1254), (1267, 1270), (1325, 1325), (1330, 1334),
          (1404, 1404), (1588, 1588), (1597, 1597), (1767, 1769), (1777, 1777),
          (2366, 2373), (2468, 2469), (2488, 2490), (2492, 2494), (2500, 2503),
          (2646, 2646), (2654, 2654), (2665, 2666), (2668, 2669), (2690, 2691),
          (2696, 2704))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    lines = (args.capture / "full-log.txt").read_bytes().decode(errors="replace").split("\n")
    selected = [f"{n:4d} {lines[n-1]}" for start, end in RANGES for n in range(start, end + 1) if n <= len(lines)]
    report = (args.capture / "report-all.html").read_text().splitlines()
    statuses = [f"{n:4d} {line.strip()}" for n, line in enumerate(report, 1) if n <= 35 and
                re.search(r"<td>(armv7l|aarch64|x86_64)</td>|succeeded:|failed:", line)]
    (args.out / "parent-log-excerpts.txt").write_text("\n".join(selected) + "\n")
    (args.out / "gbs-report-excerpts.txt").write_text("\n".join(statuses) + "\n")


if __name__ == "__main__":
    main()
