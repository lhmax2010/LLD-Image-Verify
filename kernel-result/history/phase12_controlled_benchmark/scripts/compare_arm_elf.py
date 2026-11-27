#!/usr/bin/env python3
"""Compare frozen-input, controlled build, and historical ARM32 ELF pairs."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess

from phase11_elf32_module import (
    SHT_NOBITS, SHT_REL, SHT_RELA, SHT_SYMTAB_SHNDX, digest, module_signature,
    parse_build_ids, parse_modinfo, parse_relocations, parse_sections, parse_symbol_versions,
    parse_symbols, readelf_arm_names,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/elf"
OLD_QB = ROOT.parent / "kernel_lld_verification_20261120"
NEW_QB = ROOT.parent / "kernel_lld_verification_20261125"
AAELF32 = "https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst#mapping-symbols"
ADDENDA32 = "https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst#default-values-for-public-tags"
MAPPING = re.compile(r"^\$([atd])(?:\..+)?$")
ARM_ATTRIBUTES_DEFAULTS = {"Tag_ABI_PCS_R9_use": "V6", "Tag_ABI_FP_exceptions": "Unused"}
DEBUG_SECTION = re.compile(r"^(?:\.rel(?:a)?\.)?\.?debug(?:_|$)|^\.zdebug_")
DATA_2_BYTES = {"R_ARM_ABS16", "R_ARM_THM_ABS5", "R_ARM_THM_JUMP11", "R_ARM_THM_JUMP8",
                "R_ARM_THM_JUMP6", "R_ARM_THM_SWI8", "R_ARM_THM_PC8"}
RAW4_TYPES = {"R_ARM_ABS32", "R_ARM_REL32", "R_ARM_PREL31", "R_ARM_TARGET1", "R_ARM_TARGET2",
              "R_ARM_CALL", "R_ARM_JUMP24", "R_ARM_PC24", "R_ARM_V4BX", "R_ARM_THM_CALL",
              "R_ARM_THM_JUMP24", "R_ARM_THM_JUMP19", "R_ARM_MOVW_ABS_NC", "R_ARM_MOVT_ABS",
              "R_ARM_MOVW_PREL_NC", "R_ARM_MOVT_PREL", "R_ARM_THM_MOVW_ABS_NC", "R_ARM_THM_MOVT_ABS",
              "R_ARM_THM_MOVW_PREL_NC", "R_ARM_THM_MOVT_PREL", "R_ARM_GOT_BREL", "R_ARM_GOTOFF32",
              "R_ARM_BASE_PREL", "R_ARM_ABS32_NOI", "R_ARM_REL32_NOI", "R_ARM_THM_GOT_BREL12"}

SIZE_FIELDS = ("comparison", "kind", "record", "section", "occurrence", "old_present", "new_present",
               "old_bytes", "new_bytes", "delta_bytes", "old_file_bytes", "new_file_bytes",
               "delta_file_bytes", "old_offset", "new_offset", "old_flags", "new_flags",
               "old_alignment", "new_alignment", "old_sha256", "new_sha256")


def display(path):
    return os.path.relpath(path, ROOT)


def absolute(path):
    return (ROOT / path).resolve()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def section_key(section):
    return section["name"], section["occurrence"]


def key_label(key):
    return key[0] if key[1] == 1 else f"{key[0]}#{key[1]}"


def run_tool(name, tool, *args, env=None):
    path = EVIDENCE / "tools" / Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LC_ALL="C", **(env or {}))
    argv = [*tool, *map(str, args)]
    attempt = subprocess.run(argv, env=env, capture_output=True, check=False)
    path.with_suffix(path.suffix + ".out").write_bytes(attempt.stdout)
    path.with_suffix(path.suffix + ".err").write_bytes(attempt.stderr)
    write_json(path.with_suffix(path.suffix + ".cmd.json"), {
        "argv": argv, "cwd": str(Path.cwd()), "exit_status": attempt.returncode,
        "environment_overrides": {"LC_ALL": "C", **(env.get("LD_LIBRARY_PATH") and
                                  {"LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"]} or {})},
        "stdout_sha256": digest(attempt.stdout), "stderr_sha256": digest(attempt.stderr),
    })
    return attempt.returncode, attempt.stdout.decode(errors="replace")


def symbol_section_index(section, sections, symbol):
    offset = 16 * symbol["index"] + 14
    index = struct.unpack_from("<H", section["bytes"], offset)[0]
    if index == 0xffff:
        extended = next(s for s in sections if s["type"] == SHT_SYMTAB_SHNDX and s["link"] == section["index"])
        index = struct.unpack_from("<I", extended["bytes"], 4 * symbol["index"])[0]
    return index if 0 < index < len(sections) else None


def mapping_model(sections, symbols):
    entries = defaultdict(list)
    findings = []
    for symbol in symbols:
        match = MAPPING.fullmatch(symbol["name"])
        if not match:
            continue
        index = symbol["section_index"]
        entry = {"name": symbol["name"], "kind": match[1], "offset": symbol["value"],
                 "symbol_index": symbol["index"], "section_index": index}
        if symbol["binding"] != "LOCAL" or symbol["type"] != "NOTYPE" or symbol["size"]:
            findings.append({"reason": "bad_binding_type_or_size", **entry})
        if index is None or entry["offset"] > sections[index]["size"]:
            findings.append({"reason": "out_of_section", **entry})
            continue
        entries[index].append(entry)
    models = {}
    for section in sections[1:]:
        index, size = section["index"], section["size"]
        marks = entries[index]
        if not (marks or section["flags"] & 4 and size):
            continue
        label = key_label(section_key(section))
        points = defaultdict(list)
        for entry in marks:
            points[entry["offset"]].append(entry)
        transitions = []
        previous = None
        for offset, group in sorted(points.items()):
            kinds = sorted({entry["kind"] for entry in group})
            if len(kinds) > 1:
                findings.append({"reason": "conflicting_classes", "section": label, "offset": offset, "kinds": kinds})
            kind = kinds[0] if len(kinds) == 1 else "conflict:" + "/".join(kinds)
            for index_in_group, entry in enumerate(group):
                if len(kinds) > 1:
                    category = "conflict"
                elif index_in_group:
                    category = "same_offset_duplicate"
                elif offset == size:
                    category = "zero_length_end"
                elif previous == kind or (previous is None and kind == "d" and not section["flags"] & 4):
                    category = "same_class_run" if previous == kind else "data_only_optional_start"
                else:
                    category = "class_boundary"
                entry["category"] = category
            if offset < size and previous != kind:
                transitions.append((offset, kind))
                previous = kind
        # A data-only section can omit mapping markers under AAELF32. When it
        # is non-executable and has only data markers, canonicalize as data.
        if size and not section["flags"] & 4 and all(t[1] == "d" for t in transitions):
            transitions = [(0, "d")]
        if size and section["flags"] & 4 and (not transitions or transitions[0][0] != 0):
            findings.append({"reason": "no_start_marker_in_executable_section", "section": label})
            transitions.insert(0, (0, "unknown"))
        spans = [{"start": offset,
                  "end": transitions[pos+1][0] if pos+1 < len(transitions) else size,
                  "kind": kind}
                 for pos, (offset, kind) in enumerate(transitions)]
        models[label] = {
            "section_index": section["index"], "size": size, "executable": bool(section["flags"] & 4),
            "markers": sorted(marks, key=lambda row: (row["offset"], row["symbol_index"])),
            "spans": spans,
        }
    counts = Counter(row["kind"] for group in models.values() for row in group["markers"])
    categories = Counter(row["category"] for group in models.values() for row in group["markers"])
    return {"sections": models, "counts": dict(counts), "categories": dict(categories), "findings": findings}


def reloc_width(name):
    if name == "R_ARM_NONE":
        return 0
    if name == "R_ARM_ABS8":
        return 1
    if name in DATA_2_BYTES:
        return 2
    if name in RAW4_TYPES:
        return 4
    return None


def relocation_model(sections, tables, names):
    parsed = iter(parse_relocations(sections, tables, names))
    for section in sections:
        if section["type"] not in (SHT_RELA, SHT_REL):
            continue
        origin = sections[section["info"]]
        symbols = tables[section["link"]]
        width = section["entry_size"]
        for offset in range(0, section["size"], width):
            row = next(parsed)
            info = struct.unpack_from("<I", section["bytes"], offset + 4)[0]
            target = symbols[info >> 8]
            row["origin_key"] = key_label(section_key(origin))
            row["relocation_key"] = key_label(section_key(section))
            row["target_key"] = key_label(tuple(target["section_key"]))
            row["target_section_index"] = target["section_index"]
            row["target_symbol_type"] = target["type"]
            row["target_named_mapping_symbol"] = bool(MAPPING.fullmatch(target["name"]))
            row["origin_sha256"] = origin["content_sha256"]
            byte_count = reloc_width(row["type"])
            if width == 8 and byte_count is not None and row["offset"] + byte_count <= len(origin["bytes"]):
                row["rel_site_bytes"] = origin["bytes"][row["offset"]:row["offset"] + byte_count].hex()
            else:
                row["rel_site_bytes"] = None
            yield row


def parse_one(path, label, readelf):
    data = path.read_bytes()
    header, sections = parse_sections(data)
    tables = parse_symbols(sections)
    for index, table in tables.items():
        for symbol in table:
            related = symbol_section_index(sections[index], sections, symbol)
            symbol["section_index"] = related
            symbol["section_key"] = section_key(sections[related]) if related else (symbol["section"], 1)
    result, text = run_tool(label + "/readelf", readelf, "-WhASsrn", path)
    if result:
        raise ValueError(f"readelf failed for {path}")
    attributes = {}
    for line in text.splitlines():
        match = re.match(r"\s*(Tag_\w+):\s*(.*)", line)
        if match:
            attributes[match[1]] = match[2]
    symbols = [s for table in tables.values() for s in table]
    records = [s for table in tables.values() for s in table[1:]]
    versions = parse_symbol_versions(sections)
    meta = next((s["bytes"] for s in sections if s["name"] == ".modinfo"), None)
    info = parse_modinfo(meta) if meta is not None else None
    mapping = mapping_model(sections, records)
    relocs = list(relocation_model(sections, tables, readelf_arm_names(text)))
    return {
        "path": path, "sha256": digest(data), "size": len(data), "header": header, "sections": sections,
        "symbols": records, "statistics": {"total": len(records), "null": len(symbols) - len(records),
        "by_binding": dict(Counter(s["binding"] for s in records))},
        "mapping": mapping, "relocations": relocs, "versions": versions, "metadata": info,
        "attributes": attributes, "build_ids": parse_build_ids(sections), "signature": module_signature(data),
        "layout": {"elf_header_bytes": 52, "section_table_bytes": 40 * len(sections),
                   "section_payload_bytes": sum(s["file_size"] for s in sections[1:]),
                   "unassigned_bytes": len(data) - 52 - 40 * len(sections) - sum(s["file_size"] for s in sections[1:])},
    }


def put_size(out, case, kind, record, key, a, b):
    def get(section, name, default=None):
        return section.get(name, default) if section else default
    out.append({
        "comparison": case, "kind": kind, "record": record, "section": key[0], "occurrence": key[1],
        "old_present": a is not None, "new_present": b is not None,
        "old_bytes": get(a, "size", 0), "new_bytes": get(b, "size", 0),
        "delta_bytes": get(b, "size", 0) - get(a, "size", 0),
        "old_file_bytes": get(a, "file_size", 0), "new_file_bytes": get(b, "file_size", 0),
        "delta_file_bytes": get(b, "file_size", 0) - get(a, "file_size", 0),
        **{f"{side}_{key}": get(section, name) for side, section in (("old", a), ("new", b))
           for key, name in [("offset", "offset"), ("flags", "flag_names"), ("alignment", "alignment"),
                             ("sha256", "content_sha256")]},
    })


def make_size_rows(out, case, kind, left, right):
    def file_model(model):
        return {"size": model["size"], "file_size": model["size"], "content_sha256": model["sha256"]}
    put_size(out, case, kind, "ARTIFACT", ("", 1), file_model(left), file_model(right))
    if kind == "rpm":
        return
    groups = {".rel.*": lambda s: s["type"] == SHT_REL, ".rela.*": lambda s: s["type"] == SHT_RELA,
              ".debug_*": lambda s: bool(DEBUG_SECTION.match(s["name"]))}
    by_side = [{section_key(s): s for s in model["sections"][1:]} for model in (left, right)]
    for key in sorted(set(by_side[0]) | set(by_side[1])):
        put_size(out, case, kind, "SECTION", key, by_side[0].get(key), by_side[1].get(key))
    for name, predicate in groups.items():
        totals = [{field: sum(s[field] for s in model["sections"][1:] if predicate(s))
                   for field in ("size", "file_size")} for model in (left, right)]
        put_size(out, case, kind, "SECTION_GROUP", (name, 1), *totals)
    for key in left["layout"]:
        a, b = ({"size": model["layout"][key], "file_size": model["layout"][key]} for model in (left, right))
        put_size(out, case, kind, "LAYOUT", (key, 1), a, b)


def equivalent_merge_payload(a, b):
    if not (a["flags"] & 16 and b["flags"] & 16) or a["entry_size"] != b["entry_size"] or not a["entry_size"]:
        return None
    width = a["entry_size"]
    if a["flags"] & 32 and b["flags"] & 32 and width == 1:
        # A linker may share a suffix of a longer mergeable string.
        return all(item + b"\0" in other["bytes"] for one, other in ((a, b), (b, a))
                   for item in one["bytes"].split(b"\0")[:-1])
    if a["flags"] & 32 or b["flags"] & 32:
        return None
    entry_set = lambda s: {s["bytes"][i:i+width] for i in range(0, s["size"], width)}
    return entry_set(a) == entry_set(b)


def section_comparison(left, right):
    l, r = ({section_key(s): s for s in data["sections"][1:]} for data in (left, right))
    matches = []
    for key in sorted(set(l) | set(r)):
        a, b = l.get(key), r.get(key)
        detail = {"section": key_label(key), "left_index": a and a["index"], "right_index": b and b["index"],
                  "allocated": bool((a and a["flags"] & 2) or (b and b["flags"] & 2)),
                  "executable": bool((a and a["flags"] & 4) or (b and b["flags"] & 4)),
                  "layout_delta": {}, "content_delta": False,
                  "merge_section": bool(a and b and a["flags"] & b["flags"] & 16)}
        for field in ("type", "flags", "size", "alignment", "offset"):
            old, new = a and a[field], b and b[field]
            if old != new:
                detail["layout_delta"][field] = [old, new]
        h1, h2 = a and a["content_sha256"], b and b["content_sha256"]
        if h1 != h2:
            detail["content_delta"] = True
            detail["sha256"] = [h1, h2]
            if detail["merge_section"] and detail["allocated"]:
                detail["merge_payload_equivalent"] = equivalent_merge_payload(a, b)
            elif a and b and detail["allocated"] and a["size"] == b["size"]:
                detail["non_relocation_payload_equivalent"] = (stage_section_mask(left, a) == stage_section_mask(right, b))
            if a and b and a["size"] == b["size"] and a["file_size"] == b["file_size"]:
                detail["changed_byte_count"] = sum(x != y for x, y in zip(a["bytes"], b["bytes"]))
        matches.append(detail)
    return matches


def attr_compare(a, b):
    if a == b:
        return {}
    defaults = {} if "Tag_nodefaults" in (a.keys() | b.keys()) else ARM_ATTRIBUTES_DEFAULTS
    return {key: [a.get(key), b.get(key)] for key in sorted(a.keys() | b.keys())
            if a.get(key, defaults.get(key)) != b.get(key, defaults.get(key))}


def disasm_model(text):
    instructions = []
    section = None
    section_numbers = Counter()
    for line in text.splitlines():
        head = re.match(r"Disassembly of section (.+):", line)
        if head:
            name = head[1]
            section_numbers[name] += 1
            section = key_label((name, section_numbers[name]))
            continue
        match = re.match(r"^\s*([0-9a-fA-F]+):\s+((?:(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{4}|[0-9a-fA-F]{2})[ \t]+)+)(.*)$", line)
        if not section or not match:
            continue
        encoded = "".join(match[2].split()).lower()
        text = match[3].strip()
        if len(encoded) not in (2, 4, 8) or not text or text.startswith("."):
            continue
        instructions.append((section, int(match[1], 16), encoded, text.split()[0].lower()))
    return instructions


def decode_case(label, left, right, disassemblers):
    observed = {}
    parsed = {}
    for name, tool, env in disassemblers:
        captures = []
        for side, data in (("left", left), ("right", right)):
            code, text = run_tool(f"{label}/{side}/{name}-disassembly", tool, "-drz", data["path"], env=env)
            decoded = disasm_model(text) if code == 0 else []
            captures.append(decoded)
        if all(captures):
            parsed[name] = captures
            observed[name] = {"status": "PASS", "instruction_records": list(map(len, captures)),
                              "normalized_equal_within_tool": captures[0] == captures[1],
                              "normalized_location_match": [(s, i) for s, i, _, _ in captures[0]] ==
                                                           [(s, i) for s, i, _, _ in captures[1]],
                              "normalization": "section, instruction offset, displayed instruction bytes, mnemonic"}
        else:
            observed[name] = {"status": "UNAVAILABLE_OR_UNPARSED", "instruction_records": list(map(len, captures))}
    if parsed.keys() == {"gnu", "llvm"}:
        for index, side in enumerate(("left", "right")):
            a, b = ({(sec, off): enc for sec, off, enc, _ in parsed[name][index]} for name in ("gnu", "llvm"))
            observed[f"cross_tool_{side}"] = {
                "same_instruction_offsets": a.keys() == b.keys(), "shared_instruction_offsets": len(a.keys() & b.keys()),
                "encoded_value_conflicts_at_shared_offsets": sum(a[loc] != b[loc] for loc in a.keys() & b.keys()),
                "only_gnu_offsets": len(a.keys() - b.keys()), "only_llvm_offsets": len(b.keys() - a.keys()),
                "comparison_scope": "Rendered opcode words and instruction locations. Mnemonic and operand aliases are tool-specific.",
            }
    return observed


def exports(data):
    members = {s["name"].removeprefix("__ksymtab_") for s in data["symbols"] if s["name"].startswith("__ksymtab_")}
    members.update(s["name"].split("+", 1)[1] for s in data["sections"]
                   if s["name"].startswith("___ksymtab") and "+" in s["name"])
    return sorted(members)


def symbols_interface(data):
    def key(symbol):
        return [symbol[name] for name in ("type", "binding", "visibility", "size", "defined")]
    table = defaultdict(list)
    for symbol in data["symbols"]:
        if symbol["binding"] != "LOCAL" and symbol["name"]:
            table[symbol["name"]].append(key(symbol))
    return {n: sorted(shapes) for n, shapes in table.items()}


def diff_dict(a, b):
    return {key: [a.get(key), b.get(key)] for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key)}


def version_match(data, symvers):
    imports = data["versions"]["imports"]
    if not imports or not symvers:
        return {"status": "NOT_CHECKED", "count": len(imports)}
    mismatch = {name: [value, symvers.get(name)] for name, value in imports.items() if symvers.get(name) != value}
    return {"status": "PASS" if not mismatch else "DIFFERENCE_REVIEW", "count": len(imports),
            "matched": len(imports) - len(mismatch), "mismatch": mismatch}


def merge_entry(section, offset):
    width = section["entry_size"]
    if not 0 <= offset < len(section["bytes"]) or not width:
        return None
    if section["flags"] & 32:
        if width != 1:
            return None
        end = section["bytes"].find(b"\0", offset)
        return None if end < 0 else (digest(section["bytes"][offset:end+1]), 0)
    start = offset - offset % width
    return digest(section["bytes"][start:start+width]), offset-start


def merge_relocation_semantics(data):
    """Resolve SHF_MERGE target offsets to content for audited relocation forms."""
    resolved = defaultdict(Counter)
    count = 0
    for row in data["relocations"]:
        if not row["target_section_index"]:
            continue
        target = data["sections"][row["target_section_index"]]
        if not target["flags"] & 16 or not target["entry_size"]:
            continue
        raw = row["rel_site_bytes"]
        kind = row["type"]
        offset = row["target_value"]
        if raw is not None and kind == "R_ARM_ABS32":
            offset += int.from_bytes(bytes.fromhex(raw), "little", signed=True)
            addend_anchor = None
        elif raw is not None and row["target_symbol_type"] != "SECTION" and kind in {
                "R_ARM_MOVW_ABS_NC", "R_ARM_MOVT_ABS"}:
            # Preserve the instruction word and compare target string content.
            addend_anchor = raw
        else:
            continue
        if not 0 <= offset < len(target["bytes"]):
            continue
        entry = merge_entry(target, offset)
        if entry is None:
            continue
        key = tuple(row[name] for name in ("relocation_key", "origin_key", "type_id", "offset",
                                         "target_key", "target_binding", "target_defined"))
        resolved[key][(*entry, addend_anchor)] += 1
        count += 1
    return resolved, count


def relocation_comparison(a, b):
    relevant_keys = ("relocation_key", "origin_key", "type_id", "offset", "target_symbol", "target_key",
                     "target_binding", "target_defined", "target_value", "addend")
    def identity(row):
        return tuple(row[k] for k in relevant_keys)

    by_side = []
    for data in (a, b):
        normalized = defaultdict(Counter)
        for row in data["relocations"]:
            normalized[identity(row)][(row["rel_site_bytes"], row["origin_sha256"])] += 1
        by_side.append(normalized)
    left, right = by_side
    totals = Counter()
    examples = defaultdict(list)
    for key in sorted(left.keys() | right.keys(), key=str):
        variants_left, variants_right = left.get(key, Counter()), right.get(key, Counter())
        count_a, count_b = sum(variants_left.values()), sum(variants_right.values())
        if count_a != count_b:
            category = "debug" if DEBUG_SECTION.match(key[1]) else "regular"
            totals[f"{category}_identity_deltas"] += abs(count_a - count_b)
            examples[f"{category}_identity_deltas"].append({"identity": list(key), "left": count_a, "right": count_b})
        elif variants_left != variants_right:
            columns = [Counter(), Counter()]
            for group, column in zip((variants_left, variants_right), columns):
                for (raw_bytes, _origin_hash), count in group.items():
                    column[raw_bytes] += count
            category = "debug" if DEBUG_SECTION.match(key[1]) else "regular"
            if columns[0] != columns[1]:
                totals[f"{category}_site_bytes_changed"] += count_a
                examples[f"{category}_site_bytes_changed"].append(
                    {"identity": list(key), "left": dict(columns[0]), "right": dict(columns[1])})
            elif None in columns[0] and key[-1] is None:
                totals[f"{category}_implicit_addend_unverified"] += count_a
    counts = {side: dict(Counter(row["type"] for row in data["relocations"]))
              for side, data in (("left", a), ("right", b))}
    normal_left, norm_count_left = merge_relocation_semantics(a)
    normal_right, norm_count_right = merge_relocation_semantics(b)
    common_semantics = {key for key in normal_left.keys() & normal_right.keys() if normal_left[key] == normal_right[key]}
    merge_touched = Counter()
    for category, items in examples.items():
        for row in items:
            row_ident = row["identity"]
            key = tuple(row_ident[i] for i in (0, 1, 2, 3, 5, 6, 7))
            if key in common_semantics:
                merge_touched[category] += (abs(row["left"] - row["right"])
                                             if isinstance(row["left"], int) else sum(row["left"].values()))
    merge_similarity = {"eligible_relocations": [norm_count_left, norm_count_right],
                        "equivalent_sites": len(common_semantics),
                        "difference_occurrences_explained_by_target_content": dict(merge_touched),
                        "unexplained_difference_occurrences": dict(totals - merge_touched)}
    return {"totals": {side: sum(kinds.values()) for side, kinds in counts.items()},
            "merge_target_content_normalization": merge_similarity,
            "types": counts, "differences": dict(totals), "details": dict(examples),
            "relocations_to_mapping_symbols": {side: sum(r["target_named_mapping_symbol"] for r in d["relocations"])
                                              for side, d in (("left", a), ("right", b))}}


def compare_maps(left, right):
    a, b = (d["mapping"]["sections"] for d in (left, right))
    all_keys = sorted(a.keys() | b.keys())
    # Cover a non-executable section with omitted data markers if the other
    # side had explicit markers for the same section.
    models = [{key_label(section_key(s)): s for s in d["sections"][1:]} for d in (left, right)]
    results = []
    for key in all_keys:
        maps = []
        for data, sections in zip((a, b), models):
            item = data.get(key)
            if item is not None:
                maps.append(item)
            elif key in sections and not sections[key]["flags"] & 4 and sections[key]["size"]:
                maps.append({"markers": [], "spans": [{"start": 0, "end": sections[key]["size"], "kind": "d"}]})
            else:
                maps.append({"markers": [], "spans": []})
        ma, mb = maps
        get_key = lambda row: (row["offset"], row["kind"])
        markers_left = Counter(get_key(row) for row in ma["markers"])
        markers_right = Counter(get_key(row) for row in mb["markers"])
        removed = [dict(row) for row in reversed(ma["markers"]) if markers_left[get_key(row)] and
                   consume_difference(markers_left, markers_right, get_key(row))]
        markers_left = Counter(get_key(row) for row in ma["markers"])
        markers_right = Counter(get_key(row) for row in mb["markers"])
        added = [dict(row) for row in reversed(mb["markers"]) if markers_right[get_key(row)] and
                 consume_difference(markers_right, markers_left, get_key(row))]
        if removed or added or ma["spans"] != mb["spans"]:
            results.append({"section": key, "effective_spans_equal": ma["spans"] == mb["spans"],
                            "left": ma["spans"], "right": mb["spans"], "removed": removed, "added": added})
    return results


def consume_difference(supply, baseline, key):
    supply[key] -= 1
    return supply[key] >= baseline[key]


def source_anchor_candidates(input_data, output):
    """Map input section offsets by congruent named symbols and identical spans."""
    input_index = {s["index"]: s for s in input_data["sections"][1:]}
    output_index = {s["index"]: s for s in output["sections"][1:]}
    out_symbols = defaultdict(list)
    for sym in output["symbols"]:
        if sym["section_index"] and sym["name"] and not MAPPING.fullmatch(sym["name"]):
            out_symbols[(sym["name"], sym["type"], sym["binding"])].append(sym)
    candidates = defaultdict(Counter)
    for sym in input_data["symbols"]:
        if not sym["section_index"] or not sym["name"] or MAPPING.fullmatch(sym["name"]):
            continue
        anchors = out_symbols[(sym["name"], sym["type"], sym["binding"])]
        if len(anchors) == 1:
            match = anchors[0]
            base = match["value"] - sym["value"]
            left, right = input_index[sym["section_index"]], output_index[match["section_index"]]
            if base >= 0 and base+left["size"] <= right["size"] and left["type"] == right["type"]:
                candidates[left["index"]][(right["index"], base)] += 1
    for input_section, guesses in candidates.items():
        ranked = guesses.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue
        (output_section, base), count = ranked[0]
        a, b = input_index[input_section], output_index[output_section]
        byte_equal = a["file_size"] > 0 and a["bytes"] == b["bytes"][base:base+a["size"]]
        yield input_section, output_section, base, count, byte_equal


def bfd_map_contributions(path):
    """Yield GNU LINK_MAP contributions, including wrapped section names."""
    section = pending = None
    start = 0
    for line in path.read_text().splitlines():
        main = re.fullmatch(r"(\S+)(?:\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+)?", line)
        if main and not line.startswith("LOAD"):
            section, start = main[1], int(main[2] or "0", 16)
            pending = None
            continue
        part = re.fullmatch(r"\s+(?:(\S+)\s+)?(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.o)\s*", line)
        if part and section and (part[1] or pending):
            yield section, part[1] or pending, int(part[2], 16)-start, int(part[3], 16), part[4]
            pending = None
        else:
            prefix = re.fullmatch(r"\s+(\S+)", line)
            if prefix:
                pending = prefix[1]


def bfd_marker_sources(inputs, map_path, output):
    by_name = {d["path"].name: d for d in inputs}
    if len(by_name) != len(inputs):
        raise ValueError("BFD map attribution requires unique object basenames")
    result = defaultdict(list)
    for out_name, in_name, start, size, obj in bfd_map_contributions(map_path):
        data = by_name.get(Path(obj).name)
        if data is None or out_name not in output["mapping"]["sections"]:
            continue
        input_sections = [s for s in data["sections"][1:] if key_label(section_key(s)) == in_name]
        if len(input_sections) != 1:
            continue
        section = input_sections[0]
        source = data["mapping"]["sections"].get(in_name, {"markers": []})
        destination = output["mapping"]["sections"][out_name]
        if section["size"] != size or start + size > destination["size"]:
            continue
        targets = {(marker["offset"], marker["kind"]) for marker in destination["markers"]}
        records = [(marker["offset"], marker["kind"], "INPUT_MARKER") for marker in source["markers"]]
        if not source["markers"] and size and not section["flags"] & 4:
            # If the input contributed data at this offset without a mapping
            # marker, a matching BFD output marker was synthesized at link time.
            records.append((0, "d", "BFD_SYNTHESIZED_AT_DATA_CONTRIBUTION"))
        for offset, kind, identity in records:
            key = (start + offset, kind)
            if key in targets:
                result[(out_name, *key)].append({
                    "object": display(data["path"]), "input_section": in_name,
                    "input_offset": offset, "mapped_output_section_offset": key[0],
                    "input_sha256": data["sha256"], "source_type": identity,
                })
    return result


def stage_section_mask(data, section):
    # Use equality on all bytes outside known relocation sites to validate a
    # common linear projection of input to final output. Mapping addresses
    # and actual relocations are evaluated independently of this cross-check.
    payload = bytearray(section["bytes"])
    for row in data["relocations"]:
        if row["origin_key"] != key_label(section_key(section)):
            continue
        raw = row["rel_site_bytes"]
        if raw:
            size = len(raw) // 2
            payload[row["offset"]:row["offset"]+size] = bytes(size)
    return payload


def remap_marker_candidates(intermediate, final, section, marker):
    if section not in intermediate["mapping"]["sections"] or section not in final["mapping"]["sections"]:
        return []
    origin = intermediate["mapping"]["sections"][section]
    dest = final["mapping"]["sections"][section]
    a, b = intermediate["sections"][origin["section_index"]], final["sections"][dest["section_index"]]
    matches = [x for x in origin["markers"] if x["kind"] == marker["kind"]]
    if a["flags"] & 16 and b["flags"] & 16:
        reference = merge_entry(b, marker["offset"])
        if reference:
            return [(x["offset"], "MERGE_ENTRY_CONTENT") for x in matches if merge_entry(a, x["offset"]) == reference]
        return []
    if a["size"] == 0 or a["size"] > b["size"]:
        return []
    left, right = stage_section_mask(intermediate, a), stage_section_mask(final, b)
    start = right.find(left)
    if start < 0 or right.find(left, start+1) >= 0:
        return []
    return [(x["offset"], "SAME_SECTION_PAYLOAD") for x in matches if x["offset"] + start == marker["offset"]]


def attach_map_sources(losses, inputs, map_path, reference, final):
    sources = bfd_marker_sources(inputs, map_path, reference)
    for row in losses:
        for marker in row["removed"]:
            offset = marker["offset"]
            kind = marker["kind"]
            section = row["section"]
            matches = ([(offset, "GNU_BFD_MAP")] if reference is final else
                       remap_marker_candidates(reference, final, section, marker))
            mapped = []
            for offset, mode in matches:
                mapped.extend({**value, "projection": mode} for value in sources[(section, offset, kind)])
            if mapped:
                marker["input_origin_candidates"] = mapped
                marker["origin_status"] = "LINK_MAP_UNIQUE" if len(mapped) == 1 else "LINK_MAP_MULTIPLE"


def mapping_origins(inputs, left, lost, parser, map_path=None, reference=None):
    targets = defaultdict(list)
    for change in lost:
        for row in change["removed"]:
            targets[(row["section_index"], row["offset"], row["kind"])].append(row)
    origins = defaultdict(list)
    details = []
    input_data = [parser(item) for item in inputs]
    for data in input_data:
        projected = list(source_anchor_candidates(data, left))
        by_index = {index: (out, base, count, equal) for index, out, base, count, equal in projected}
        details.append({"path": display(data["path"]), "sha256": data["sha256"],
                        "mapping_counts": data["mapping"]["counts"], "projected_input_sections": len(by_index)})
        for section, model in data["mapping"]["sections"].items():
            index = model["section_index"]
            if index not in by_index:
                continue
            out, base, count, equal = by_index[index]
            for marker in model["markers"]:
                key = (out, base + marker["offset"], marker["kind"])
                if key in targets:
                    origins[key].append({"object": display(data["path"]), "input_section": section,
                                         "input_offset": marker["offset"], "named_anchor_count": count,
                                         "section_bytes_equal": equal})
    for key, rows in targets.items():
        for row in rows:
            row["input_origin_candidates"] = origins[key]
            row["origin_status"] = ("UNIQUE_ANCHOR_AND_BYTES" if len(origins[key]) == 1 and origins[key][0]["section_bytes_equal"]
                                    else "ANCHOR_ESTIMATE_OR_AMBIGUOUS" if origins[key] else "UNRESOLVED")
    if map_path:
        attach_map_sources(lost, input_data, map_path, reference or left, left)
    return details


def summarize_artifact(model):
    def clean_map(values):
        return {name: value for name, value in values.items() if name != "sections"}
    return {
        key: model[key] for key in ("sha256", "size", "header", "layout", "statistics", "metadata",
                                    "versions", "build_ids", "signature", "attributes")
    } | {"path": display(model["path"]), "mapping_summary": clean_map(model["mapping"])}


def read_symvers(path):
    if not path:
        return {}
    result = {}
    for line in path.read_text().splitlines():
        crc, name, *_ = line.split()
        result[name] = f"0x{int(crc, 16):08x}"
    return result


def historical():
    base = NEW_QB / "11F_MODULE_ABI_SUMMARY.json"
    if not base.is_file():
        return []
    abi = json.loads(base.read_text())
    module = abi["modules"]["extra/kdbus/kdbus.ko"]
    return [{
        "id": "historical-qb", "kind": "stripped", "scope": "historical",
        "left": str((NEW_QB / module["old"]["artifact"]).resolve()),
        "right": str((NEW_QB / module["new"]["artifact"]).resolve()),
        "left_sha256": module["old"]["artifact_sha256"], "right_sha256": module["new"]["artifact_sha256"],
        "left_symvers": str((NEW_QB / abi["sdk_symvers_inputs"]["old"]["path"]).resolve()),
        "right_symvers": str((NEW_QB / abi["sdk_symvers_inputs"]["new"]["path"]).resolve()),
    }]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, default=EVIDENCE / "comparison-inputs.json")
    parser.add_argument("--no-historical", action="store_true", help="Run only pairs specified by the descriptor")
    parser.add_argument("--readelf", default="readelf")
    parser.add_argument("--gnu-objdump", help="ARM GNU objdump invocation, including a loader/wrapper if needed")
    parser.add_argument("--gnu-library-path")
    parser.add_argument("--llvm-objdump", help="LLVM objdump invocation, including a loader/wrapper if needed")
    options = parser.parse_args()
    descriptors = [] if options.no_historical else historical()
    if options.descriptor.is_file():
        descriptors.extend(json.loads(options.descriptor.read_text()))
    if not descriptors:
        parser.error("no available ELF comparison descriptors")
    write_json(EVIDENCE / "resolved-inputs.json", descriptors)
    disassemblers = []
    for name, command, libpaths in (("gnu", options.gnu_objdump, options.gnu_library_path),
                                    ("llvm", options.llvm_objdump, None)):
        if command:
            tool = shlex.split(command)
            env = {"LD_LIBRARY_PATH": libpaths} if libpaths else None
            version_rc, _ = run_tool(f"{name}-objdump-version", tool, "--version", env=env)
            if version_rc == 0:
                disassemblers.append((name, tool, env))
    readelf = shlex.split(options.readelf)
    run_tool("readelf-version", readelf, "--version")
    rows, reports = [], []
    for case in descriptors:
        identity, kind, scope = case["id"], case["kind"], case.get("scope", "controlled")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", identity):
            parser.error("case id must be a plain path component")
        inputs = [absolute(case[side]) for side in ("left", "right")]
        for side, path in zip(("left", "right"), inputs):
            required_hash = case.get(side + "_sha256")
            if required_hash and sha(path) != required_hash:
                raise ValueError(f"artifact hash mismatch: {path}")
        if kind == "rpm":
            a, b = ({"size": p.stat().st_size, "sha256": sha(p)} for p in inputs)
            make_size_rows(rows, identity, kind, a, b)
            reports.append({"id": identity, "kind": kind, "scope": scope, "left": a, "right": b})
            continue
        left, right = [parse_one(path, f"{identity}/{side}", readelf)
                       for side, path in zip(("left", "right"), inputs)]
        make_size_rows(rows, identity, kind, left, right)
        maps = compare_maps(left, right)
        src_inputs = case.get("left_inputs", case.get("inputs", []))
        ref = parse_one(absolute(case["left_origin_intermediate"]), f"{identity}/source-intermediate", readelf) if case.get(
            "left_origin_intermediate") else left
        map_path = absolute(case["left_map"]) if case.get("left_map") else None
        if map_path and (ref["sha256"] != case["left_map_output_sha256"] or sha(map_path) != case["left_map_sha256"]):
            raise ValueError(f"{identity}: BFD link map evidence does not match reference artifact or map digest")
        sources = mapping_origins(src_inputs, left, maps, lambda p: parse_one(
            absolute(p), f"{identity}/input/{hashlib.sha256(p.encode()).hexdigest()[:10]}-{Path(p).name}", readelf),
            map_path=map_path, reference=ref) if src_inputs else []
        sections = section_comparison(left, right)
        symbol_diffs = diff_dict(symbols_interface(left), symbols_interface(right))
        attribute_diffs = attr_compare(left["attributes"], right["attributes"])
        header_diffs = diff_dict({k: v for k, v in left["header"].items() if k != "section_count"},
                                 {k: v for k, v in right["header"].items() if k != "section_count"})
        version_diffs = diff_dict(left["versions"]["imports"], right["versions"]["imports"])
        meta_diffs = diff_dict(left["metadata"] or {}, right["metadata"] or {})
        checks = {
            "symbol_interface_diffs": symbol_diffs, "attribute_semantic_diffs": attribute_diffs,
            "header_diffs": header_diffs, "module_metadata_diffs": meta_diffs,
            "export_set_diffs": [exports(left), exports(right)] if exports(left) != exports(right) else [],
            "version_crc_diffs": version_diffs,
            "symvers": {side: version_match(data, read_symvers(absolute(case[side+"_symvers"])) if case.get(side+"_symvers") else {})
                        for side, data in (("left", left), ("right", right))},
            "relocations": relocation_comparison(left, right),
            "sections": sections,
            "mapping_differences": maps,
            "zero_byte_plt_layout": {side: any(s["name"] == ".plt" and s["bytes"] == b"\0"
                                                  for s in model["sections"])
                                     for side, model in (("left", left), ("right", right))},
            "mapping_inputs": sources,
            "disassembly": decode_case(identity, left, right, disassemblers),
        }
        report = {"id": identity, "kind": kind, "scope": scope,
                  "left": summarize_artifact(left), "right": summarize_artifact(right), "checks": checks}
        full = {**report, "raw_map_left": left["mapping"], "raw_map_right": right["mapping"]}
        write_json(EVIDENCE / f"{identity}.json", full)
        reports.append(report)
    with (ROOT / "ELF_SIZE_COMPARISON.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, SIZE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    overview = {"cases": reports,
                "method": {"arm_mapping_symbol_reference": AAELF32, "attribute_defaults_reference": ADDENDA32,
                           "relocation_addend_method": "RELA integers compared exactly. REL compares known-width site bytes and complete origin-section digest. Known ARM relocations to SHF_MERGE string or fixed-width data compare resolved target bytes.",
                           "mapping_provenance_method": "Hash-bound GNU BFD map sections and offsets project input marker records to the intermediate object. For final artifacts map attribution also requires matching the same section payload outside relocation sites or equivalent SHF_MERGE entry contents."}}
    write_json(EVIDENCE / "raw-comparison.json", overview)
    for case in reports:
        left, right = case["left"], case["right"]
        result = {"id": case["id"], "size_delta": right["size"] - left["size"]}
        if "checks" in case:
            result["mapping_delta"] = dict(Counter(right["mapping_summary"]["counts"]) -
                                           Counter(left["mapping_summary"]["counts"]))
            result["mapping_removed"] = dict(Counter(left["mapping_summary"]["counts"]) -
                                             Counter(right["mapping_summary"]["counts"]))
            result["relocation_differences"] = case["checks"]["relocations"]["differences"]
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
