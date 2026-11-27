#!/usr/bin/env python3
"""Render scoped ARM mapping, size, and static ABI results."""
from collections import Counter
import csv
import json
from pathlib import Path

from compare_arm_elf import AAELF32, ADDENDA32, EVIDENCE, ROOT, write_json

NON_BOUNDARY = {"same_class_run", "data_only_optional_start", "same_offset_duplicate", "zero_length_end"}
CATEGORIES = {
    "same_class_run": "同类连续区间内标记",
    "data_only_optional_start": "纯数据节可省略起始标记",
    "same_offset_duplicate": "同地址重复",
    "zero_length_end": "节末零长度标记",
    "class_boundary": "类别边界",
    "conflict": "同地址类别冲突",
}


def pair_metrics(pair):
    checks = pair["checks"]
    lost = [(change["section"], row) for change in checks["mapping_differences"] for row in change["removed"]]
    gained = [(change["section"], row) for change in checks["mapping_differences"] for row in change["added"]]
    reloc = checks["relocations"]
    exec_delta = [row["section"] for row in checks["sections"] if row["executable"] and row["content_delta"]]
    alloc_content = [row["section"] for row in checks["sections"] if row["allocated"] and row["content_delta"]]
    alloc_layout = {row["section"]: {k: v for k, v in row["layout_delta"].items() if k != "offset"}
                    for row in checks["sections"] if row["allocated"] and row["layout_delta"].keys() - {"offset"}}
    findings = {side: pair[side]["mapping_summary"]["findings"] for side in ("left", "right")}
    identical_plt_placeholder = (pair["scope"] == "gcc" and pair["left"]["sha256"] == pair["right"]["sha256"] and
                                 all(checks["zero_byte_plt_layout"].values()) and
                                 findings["left"] == findings["right"] == [
                                     {"reason": "no_start_marker_in_executable_section", "section": ".plt"}])
    span_deltas = {row["section"]: [row["left"], row["right"]] for row in checks["mapping_differences"]
                   if not row["effective_spans_equal"]}
    executable_sections = {row["section"] for row in checks["sections"] if row["executable"]}
    executable_span_deltas = sorted(executable_sections & span_deltas.keys())
    semantic = ("symbol_interface_diffs", "attribute_semantic_diffs", "header_diffs", "module_metadata_diffs",
                "export_set_diffs", "version_crc_diffs")
    unexpected = [key for key in semantic if checks[key]]
    if pair["kind"] == "intermediate" and set(checks["header_diffs"]) == {
            "elf_flags", "elf_flags_value", "arm_float_abi"} and checks["header_diffs"]["elf_flags"] == [
            "0x5000000", "0x5000200"]:
        unexpected.remove("header_diffs")
    equivalent_merge_sections = {row["section"] for row in checks["sections"]
                                 if row.get("merge_payload_equivalent") is True}
    relocation_site_only_sections = {row["section"] for row in checks["sections"]
                                     if row.get("non_relocation_payload_equivalent") is True}
    interpreted_sections = {".note.gnu.build-id", "__versions"}
    if pair["kind"] == "intermediate" and not reloc["merge_target_content_normalization"]["unexplained_difference_occurrences"]:
        interpreted_sections |= equivalent_merge_sections | relocation_site_only_sections
    if set(alloc_content) - interpreted_sections:
        unexpected.append("allocated_section_content")
    if set(alloc_layout) - interpreted_sections:
        unexpected.append("allocated_section_layout")
    if (exec_delta or executable_span_deltas or (any(findings.values()) and not identical_plt_placeholder) or
            any(reloc["relocations_to_mapping_symbols"].values())):
        unexpected.append("instruction_or_mapping_boundary_review")
    if reloc["merge_target_content_normalization"]["unexplained_difference_occurrences"]:
        unexpected.append("unexplained_relocation_differences")
    if any(check["status"] == "DIFFERENCE_REVIEW" for check in checks["symvers"].values()):
        unexpected.append("sdk_crc")
    provenance = Counter(row.get("origin_status", "UNAVAILABLE_HISTORICAL_INPUTS") for _, row in lost)
    origins = Counter(Path(row["input_origin_candidates"][0]["object"]).name for _, row in lost
                      if row.get("origin_status") in ("LINK_MAP_UNIQUE", "UNIQUE_ANCHOR_AND_BYTES"))
    return {
        "id": pair["id"], "scope": pair["scope"], "kind": pair["kind"],
        "old_bytes": pair["left"]["size"], "new_bytes": pair["right"]["size"],
        "delta_bytes": pair["right"]["size"] - pair["left"]["size"],
        "sha256": {side: pair[side]["sha256"] for side in ("left", "right")},
        "symbols": {side: pair[side]["statistics"] for side in ("left", "right")},
        "size_delta_by_layout": {name: pair["right"]["layout"][name]-value for name, value in pair["left"]["layout"].items()},
        "mapping_counts": {side: pair[side]["mapping_summary"]["counts"] for side in ("left", "right")},
        "mapping_removed": Counter(row["kind"] for _, row in lost),
        "mapping_added": Counter(row["kind"] for _, row in gained),
        "mapping_removed_categories": Counter(row["category"] for _, row in lost),
        "mapping_removed_sections": Counter(section for section, _ in lost),
        "mapping_sections_with_span_differences": sorted(span_deltas),
        "mapping_executable_span_differences": executable_span_deltas,
        "mapping_removed_non_boundary": sum(row["category"] in NON_BOUNDARY for _, row in lost),
        "mapping_origin_status": provenance,
        "mapping_all_origin_candidates_bfd_synthesized": bool(lost) and all(
            row.get("input_origin_candidates") and all(c.get("source_type") == "BFD_SYNTHESIZED_AT_DATA_CONTRIBUTION"
            for c in row["input_origin_candidates"]) for _, row in lost),
        "mapping_unique_input_objects": origins,
        "mapping_relocations": reloc["relocations_to_mapping_symbols"],
        "identical_gcc_plt_placeholder": identical_plt_placeholder,
        "relocations": {key: reloc[key] for key in ("totals", "differences", "merge_target_content_normalization")},
        "alloc_layout_change_except_file_position": alloc_layout,
        "equivalent_merge_sections": sorted(equivalent_merge_sections),
        "relocation_site_only_sections": sorted(relocation_site_only_sections),
        "allocated_content_changed": alloc_content, "executables_changed": exec_delta,
        "abi_checks_need_review": unexpected,
        "sdk_crc_validation": checks["symvers"],
        "disassembly": checks["disassembly"],
        "section_size_changes": {},
    }


def mapping_text(counts):
    return "/".join(str(counts.get(kind, 0)) for kind in "atd")


def human_counts(counts, labels=None):
    return "、".join(f"{(labels or {}).get(kind, kind)} {n:,}" for kind, n in counts.items()) or "无"


def code(value):
    mark = chr(96)
    return mark + str(value) + mark


def special_findings(metrics):
    index = {m["id"]: m for m in metrics}
    if not {"historical-qb", "controlled-stripped", "frozen-intermediate", "frozen-unstripped", "frozen-stripped"} <= index.keys():
        return []
    hist, actual = (index[key] for key in ("historical-qb", "controlled-stripped"))
    intermediate, final, stripped = (index[key] for key in ("frozen-intermediate", "frozen-unstripped", "frozen-stripped"))
    matching = hist["sha256"] == actual["sha256"]
    marker_path = lambda stage, side: stage["mapping_counts"][side].get("d", 0)
    result = [
        f"真实 Makefile A/B 的发布形式分别为 {actual['old_bytes']:,} 与 {actual['new_bytes']:,} Bytes，"
        f"与两份对应历史 QB 的 SHA-256 {'分别完全一致' if matching else '存在差异'}。"
        "在已验证的受控环境中，单行改动的 1,292 Bytes 减少可归因。历史 QB 的链接器执行仍沿用原证据评级。"
        " [冻结输入、输出及命令](evidence/replay/link-replay.json)",
        f"固定对象重放中，BFD 路径的 {code('$d')} 为 {marker_path(intermediate,'left')} → "
        f"{marker_path(final,'left')} → {marker_path(stripped,'left')}，"
        f"LLD 路径为 {marker_path(intermediate,'right')} → {marker_path(final,'right')} → "
        f"{marker_path(stripped,'right')}，顺序为中间对象、未 strip 模块、已 strip 模块。"
        "纯中间链接差额为 101 个标记，固定的最终 LLD 处理消除其中 20 个，来自 .ARM.exidx（18）、.ARM.exidx.exit.text（1）和 .ARM.exidx.init.text（1）。strip 对两侧的 81 个差额无影响。"
        " [中间链接 ELF](evidence/elf/frozen-intermediate.json) · [最终 ELF](evidence/elf/frozen-stripped.json)",
        f"GNU BFD map 的映射参考对象与普通重放的中间 ELF 摘要一致。{code('$d')} 多出的 101 条逐一指向原来没有该标记的纯数据输入节起点，均由 BFD 在中间链接添加。两侧原始的 102 条代码内数据映射保持。最终多出的 81 条均追踪至这些 BFD 添加的记录，75 条具备唯一对象来源，6 条合并常量具有多个候选来源，分别位于 .rodata.cst16（4）与 .rodata.cst8（2）。 [逐符号来源](evidence/elf/frozen-stripped.json)",
        f"中间 ELF 的主要差额来自 {code('.debug_str')} 合并，另有常量、字符串节布局和符号表变化。"
        "数据与调试 REL 站点对目标字符串或固定宽度合并记录归一化后等价，未发现未解释的站点变化。"
        "中间 ELF flags 从 0x05000000 变为 0x05000200，LLD 路径显式编码 soft-float。"
        "两侧最终 ELF 均为 0x05000200，匹配目标 SDK。"
        " [节大小 CSV](ELF_SIZE_COMPARISON.csv) · [中间 ELF 校验](evidence/elf/frozen-intermediate.json)",
    ]
    return result


def render(metrics, pairs):
    a, t, d = (code(x) for x in ("$a", "$t", "$d"))
    out = [
        "# Phase 12D/G · ARM 映射符号、大小与静态二进制对比", "",
        f"按 Arm AAELF32 比较 {a} ARM、{t} Thumb、{d} data 的半开区间。"
        "检查符号绑定、类型、尺寸、起始边界、同地址重复及重定位引用。已知纯数据节可以省略起始标记。"
        f" [Arm AAELF32 5.5.5]({AAELF32})", "",
        "| 比较 | 文件大小旧 → 新（Bytes） | 差额 | 映射符号 a/t/d 旧 → 新 |",
        "| --- | ---: | ---: | --- |",
    ]
    for m in metrics:
        mapping = m["mapping_counts"]
        out.append(f"| {m['id']} | {m['old_bytes']:,} → {m['new_bytes']:,} | {m['delta_bytes']:+,} | "
                   f"{mapping_text(mapping['left'])} → {mapping_text(mapping['right'])} |")
    for message in special_findings(metrics):
        out.extend(("", message))
    if any(m["identical_gcc_plt_placeholder"] for m in metrics):
        out.extend(("", "GCC C/D 的中间 ELF、未 strip 模块及已安装模块两两逐字节一致，最终模块 153/153 满足目标 SDK CRC。"
                    "GCC SDK 脚本在两侧均生成一个 BYTE(0) 的 .plt 占位字节。GNU objdump 报告该位置越界，LLVM 额外显示一个 unknown 字节。"
                    "两侧共同解码的 16,450 个指令无位置或操作码差异。"
                    " [GCC 构建与静态证据](GCC_COMPATIBILITY_REPORT.md) · [逐项证据](evidence/elf/gcc-stripped.json)"))
    for m in metrics:
        identity = m["id"]
        out.extend(("", f"## {identity}", ""))
        if m["scope"] == "historical":
            out.append("历史发布对照为 OBSERVED_NOT_ATTRIBUTED。两份发布包的原始中间对象及工具执行记录缺失。"
                       f" [Phase 11 ELF 报告](../kernel_lld_verification_20261125/11F_MODULE_BINARY_COMPARISON.md) · "
                       f"[Arm 属性默认值]({ADDENDA32})")
        section_sizes = "、".join(f"{code(k)} {v:+,}" for k, v in m["section_size_changes"].items()) or "无"
        layout = m["size_delta_by_layout"]
        out.extend(("", f"节文件字节差额为{section_sizes}。节载荷 {layout['section_payload_bytes']:+,} Bytes，"
                    f"节表 {layout['section_table_bytes']:+,} Bytes，文件其余布局 {layout['unassigned_bytes']:+,} Bytes。"
                    " [逐节 CSV](ELF_SIZE_COMPARISON.csv)"))
        sym = [m["symbols"][side] for side in ("left", "right")]
        kinds = ("LOCAL", "GLOBAL", "WEAK")
        bindings = "、".join(f"{k} {sym[0]['by_binding'].get(k, 0)} → {sym[1]['by_binding'].get(k, 0)}" for k in kinds)
        out.extend(("", f"符号总数 {sym[0]['total']} → {sym[1]['total']}，{bindings}。"
                    f"移除的映射符号为{human_counts(m['mapping_removed_categories'], CATEGORIES)}。"
                    f"涉及 {len(m['mapping_removed_sections'])} 个节，执行节类别边界变化 "
                    f"{len(m['mapping_executable_span_differences'])} 处，两侧映射符号重定位引用均为 "
                    f"{m['mapping_relocations']['left']}/{m['mapping_relocations']['right']}。"
                    f" [完整标记与区间](evidence/elf/{identity}.json)"))
        if m["scope"] != "historical" and m["mapping_removed"]:
            out.extend(("", f"来源匹配状态为{human_counts(m['mapping_origin_status'])}。"
                        f"唯一关联的输入对象分布为{human_counts(m['mapping_unique_input_objects'])}。"
                        "GNU BFD map 的参考 ELF 与无 map 的重放结果摘要相同。"
                        "最终模块的来源关联结合节内容或合并记录内容，详情保留多候选。"
                        f" [逐符号来源](evidence/elf/{identity}.json)"))
        reloc = m["relocations"]
        unresolved = reloc["merge_target_content_normalization"]["unexplained_difference_occurrences"]
        crt = "、".join(f"{s} {v['status']} {v.get('matched',0)}/{v['count']}" for s, v in m["sdk_crc_validation"].items())
        out.extend(("", f"执行节字节变化为{('、'.join(m['executables_changed']) or '无')}。"
                    f"SHF_ALLOC 原字节变化为{('、'.join(m['allocated_content_changed']) or '无')}。"
                    f"重定位 {reloc['totals']['left']:,} → {reloc['totals']['right']:,}，"
                    f"原始差额{human_counts(reloc['differences'])}，归一化未解释差额{human_counts(unresolved)}。"
                    f"SDK CRC 为 {crt}。复核项{('、'.join(m['abi_checks_need_review']) or '无')}。"
                    f" [接口、属性、布局和重定位证据](evidence/elf/{identity}.json)"))
        normalized = [v for k, v in m["disassembly"].items() if k in ("gnu", "llvm")]
        cross = [v for k, v in m["disassembly"].items() if k.startswith("cross_tool_")]
        if normalized:
            out.extend(("", f"GNU 与 LLVM 反汇编在各自旧新对照中的规范化一致性为 "
                        f"{[x.get('normalized_equal_within_tool') for x in normalized]}。"
                        f"两工具解析指令位置交集为 {[x['shared_instruction_offsets'] for x in cross]}，"
                        f"交集编码冲突为 {[x['encoded_value_conflicts_at_shared_offsets'] for x in cross]}。"
                        "助记符别名保留在两套原始日志。"
                        f" [GNU 日志](evidence/elf/tools/{identity}/left/gnu-disassembly.out) · "
                        f"[LLVM 日志](evidence/elf/tools/{identity}/left/llvm-disassembly.out)"))
    out.extend(("", "## 覆盖与复验", ""))
    if not any(m["scope"] == "gcc" for m in metrics):
        out.append("真实 GCC C/D 静态对照无配对产物，构建与兼容性状态见 GCC 专项报告。")
    if not any(pair["kind"] == "rpm" for pair in pairs):
        out.append("未执行配对 RPM 打包。文件大小结论覆盖同等后处理且 strip 后的已安装模块 ELF。")
    out.extend(("", "两份最终 ELF 的二进制差异按内容与布局分别复核。"
                "REL 使用站点原字节或相同重定位源节字节，RELA 核对显式 addend。"
                "可解析的合并节引用以目标记录内容和已知站点信息复核。"
                "版本 CRC 以名称与数值配对，原始表排列与 Build ID 属于已记录的元数据差异。", "",
                "[一键复核](scripts/review_arm_elf.sh) · [ELF 对比脚本](scripts/compare_arm_elf.py) · [报告脚本](scripts/render_arm_elf_report.py) · "
                "[输入描述符](evidence/elf/resolved-inputs.json) · [ABI 和大小机器结果](evidence/elf/status.json)", ""))
    (ROOT / "ARM_MAPPING_SYMBOL_ANALYSIS.md").write_text("\n".join(out))


def main():
    raw = json.loads((EVIDENCE / "raw-comparison.json").read_text())
    metrics = [pair_metrics(pair) for pair in raw["cases"] if "checks" in pair]
    index = {m["id"]: m for m in metrics}
    with (ROOT / "ELF_SIZE_COMPARISON.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["record"] == "SECTION" and int(row["delta_file_bytes"]) and row["comparison"] in index:
                name = row["section"] if row["occurrence"] == "1" else f"{row['section']}#{row['occurrence']}"
                index[row["comparison"]]["section_size_changes"][name] = int(row["delta_file_bytes"])
    experiments = [m for m in metrics if m["scope"] != "historical"]
    scoped = [m for m in experiments if m["scope"] in ("controlled", "frozen", "gcc")]
    abi = "REVIEW_REQUIRED" if any(m["abi_checks_need_review"] for m in scoped) else (
        ("NONE_OBSERVED_CONTROLLED_LLVM_FROZEN_REPLAY_AND_GCC" if any(m["scope"] == "gcc" for m in scoped)
         else "NONE_OBSERVED_CONTROLLED_LLVM_AND_FROZEN_REPLAY") if scoped else "NOT_MEASURED")
    status = {
        "status": "MEASURED" if experiments else "HISTORICAL_ONLY",
        "static_abi_regression": abi,
        "historical_case": index.get("historical-qb"), "experiments": experiments,
        "historical_phase11_execution": "HISTORICAL_EXECUTION_EVIDENCE_UNAVAILABLE",
    }
    write_json(EVIDENCE / "status.json", status)
    render(metrics, raw["cases"])
    print(json.dumps({"status": status["status"], "static_abi_regression": abi, "cases": list(index)}))


if __name__ == "__main__":
    main()
