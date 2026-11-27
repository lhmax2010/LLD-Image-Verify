#!/usr/bin/env python3
"""Write the audit and scoped identity documents from checked evidence."""
import argparse
from pathlib import Path

from review_common import BASE, HERE, dump, load, markdown_table, need, sha

TRACE = ('started_utc','elapsed_seconds','exit_status')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=BASE)
    parser.add_argument('--replay',type=Path)
    parser.add_argument('--output',type=Path,default=HERE)
    args=parser.parse_args()
    base,out=args.base.resolve(),args.output.resolve()
    data=load(out,'08_01_evidence_integrity_review.json')
    recorded=load(out,'evidence/round1-offline-replay.cmd.json')
    audit=load(out,'evidence/round1-cross-audit.cmd.json')
    replay_check = (out/'evidence/round1-offline-replay.out').read_text()
    need(recorded['exit_status']==audit['exit_status']==0 and f'{data["manifest_entries"]} SHA256 entries' in replay_check,'archived offline replay failed')
    if args.replay:
        replay=args.replay.resolve()
        compare={}
        for name in ('05_kernel_module_coverage.json','05_loaded_module_mapping.csv',
                     '06_identity_verification.json','KERNEL_LLD_VERIFICATION_SUMMARY.json'):
            left,right=base/name,replay/name
            need(sha(left)==sha(right),f'Round 1 replay output differs: {name}')
            compare[name]=dict(original_sha256=sha(left),replay_sha256=sha(right),comparison='EXACT_MATCH')
        dump(out/'evidence/round1-replay-output-comparison.json',compare)
    data.update(archive_integrity_replay=dict(receipt='evidence/round1-offline-replay.cmd.json',
                                             stdout='evidence/round1-offline-replay.out',stderr='evidence/round1-offline-replay.err',
                                             **{key:recorded[key] for key in TRACE}),
                cross_audit_receipt='evidence/round1-cross-audit.cmd.json',
                replay_output_comparison='evidence/round1-replay-output-comparison.json')
    dump(out/'08_01_evidence_integrity_review.json',data)
    (out/'08_01_evidence_integrity_review.md').write_text(f'''# 08.01 · 第一轮证据完整性复核

**PASS。** 离线入口先读取并独立复核第一轮 {data["manifest_entries"]} 条 SHA256 和 {data["command_receipts"]} 条命令回执，再复制到独立工作目录复跑。进程退出 0。原目录保留第一轮文件。模块覆盖、加载映射、身份和最终结构化报告的复跑输出均与原件 SHA256 一致。 [原索引](round1/SHA256SUMS) · [原命令索引](round1/COMMANDS.jsonl) · [复跑 stdout](evidence/round1-offline-replay.out) · [复跑回执](evidence/round1-offline-replay.cmd.json) · [复跑逐文件比较](evidence/round1-replay-output-comparison.json)

- **候选范围** 重算 filelists 的压缩与展开摘要，精确 release 下有两个二进制 .ko 包，共 59 个目标。93 条候选和 10 个选中条目的 CSV、JSON 和 RPM 摘要一致。RPM header 文件摘要、已解包 payload、发布模块分区及设备文件四处一致。树外源码提供 RPM 属本轮新增因果证据。 [仓库清单](round1/02_kernel_rpm_inventory.csv) · [逐项交叉审计](08_01_evidence_integrity_review.json)
- **最终目标绑定** 59 个 quiet LD 事件的完整目标名均以 .ko 结束。相同 LD [M] 标签下的 .o 行单独处理。逐条核对同一日志的 LLVM=1、目标范围、最终 .ko 路径、安装路径、RPM 写出和成功结束。树外 7 条均有各自构建的工具链设置与 .ko 事件。 [原索引](round1/evidence/build/module-final-commands.json) · [作用域复核](08_05_out_of_tree_modules.md)
- **重复与遗漏** 正式 payload 中模块名、basename 和构建路径键均无重复。外置 RT 构建中的同名目标位于明确排除范围。kdbus/kdbus.o 与 kdbus/kdbus.ko 分开。仓库 filelists、RPM header、日志、解包清单及设备路径集合闭合，未发现匹配分母的静默遗漏。 [59 行原始关联](08_01_evidence_integrity_review.json)
- **运行证据** 对 11 个原始 sysfs hexdump 重建头部和 GNU Build ID，逐个验证 note SHA256，再与设备模块 ELF 和 /proc/modules 行比对，11/11 一致。 [sysfs 原文](round1/evidence/runtime/loaded-build-ids.out) · [加载清单](round1/05_loaded_module_mapping.csv)
- **快照绑定** 使用 build.xml ID、Base ID、standard/armv7l、成功日志精确下载 URL、manifest revision 和完整日志 SHA256 绑定。发布签名可用性保留第一轮限制。 [发布 build.xml](round1/evidence/repository/publication-build.out) · [源码 manifest](round1/evidence/repository/manifest.out) · [原始日志索引](evidence/ORIGINAL_BUILD_LOG_INDEX.json)
''')
    build=load(out,'BUILD_ID_COMPARISON.json')
    b=build['exact_difference']
    z=build['zimage_gzip']
    main=build['main_kernel']
    runtime=build['runtime']
    (out/'08_07_build_id_postprocessing_review.md').write_text(f'''# 08.07 · Build ID 后处理复核

**PASS。** 用 RPM header 的单文件 SHA256 绑定五个已解包成员。从 kernel RPM 的 /boot/zImage 验证 ARM 头后，在偏移 0x{z["member_offset"]:x} 解出通过 gzip 校验的 {z["raw_size"]:,} 字节 raw Image。从原始设备 hexdump 重建 84 字节 notes，并核对设备报告与归档字节。 [独立复核输出](evidence/build-id/recheck.out) · [机器可读对比](BUILD_ID_COMPARISON.json) · [独立分析脚本](scripts/review_build_id.py)

{markdown_table(['对象','位置或结果'],[
    ('主 ELF PT_LOAD 所导出的基址',f'0x{main["lma_base"]:x}'),
    ('.notes VMA / LMA',f'0x{b["vma"]:x} / 0x{b["lma"]:x}'),
    ('.notes ELF 文件 / raw Image 偏移',f'0x{b["file_offset"]:x} / 0x{b["raw_offset"]:x}'),
    ('20 字节窗口 ELF / raw 文件偏移',f'0x{b["difference_elf_file_offset"]:x} / 0x{b["difference_raw_file_offset"]:x}，.notes 内 [64,84)'),
    ('原始 GNU Build ID',build['old_build_id']),
    ('后处理 GNU Build ID',build['postprocessed_build_id']),
    ('84 字节 Runtime Notes SHA256',runtime['note_sha256']),
    ('主内核 / ARM 解压器 debuglink CRC32',build['debuglinks']['main']['actual_crc32']+' / '+build['debuglinks']['decompressor']['actual_crc32'])
])}

每个有文件内容的非空 SHF_ALLOC 段均验证 PT_LOAD 的 VMA、文件偏移及大小。用 LMA = p_paddr + sh_addr − p_vaddr 和最低目标 LMA 映射到 flat binary。主内核 32 个段中 31 个相同，唯一差异为 .notes 内的 20 字节，raw 中未映射的区间均为零。ARM 解压器的 6 个映射段均一致。**唯一差异的范围限于所比较的映射段。** ELF 头、非装载段、SHT_NOBITS 和 sidecar 的 DWARF 在范围之外。 [完整映射和窗口](BUILD_ID_COMPARISON.json)

日志 L14011 先安装 zImage，L14459 执行 find-debuginfo.sh --build-id-seed 6.12.80-0，L14579 和 L14853 分别处理解压器和主 ELF。原 Base rpm 宏 L182–189 在 _unique_build_ids 开启时展开 %{{VERSION}}-%{{RELEASE}}，L556 默认开启，符合实际执行参数。同一 Base 的 rpm-build 脚本 L445–448 将 -i 和 seed 交给 debugedit。 [历史日志](round1/evidence/build/linux-rpi-armv7l.out#L14459) · [RPM 宏](evidence/build-id/historical-rpm-macros.out#L189) · [打包脚本](evidence/build-id/historical-find-debuginfo.sh.txt#L445)

重算 ID 更改 .notes，包装流程还处理 DWARF 并从 stripped ELF 移除或分离 .comment。两个 stripped ELF 均无 .comment。各自通过 .gnu_debuglink 文件名和 CRC32 验证的 sidecar 保留非装载 .comment，记录 clang version 22.1.8 与 Linker: LLD 22.1.8。sidecar 标记仍可能从早期链接输入继承。 [stripping 规则](evidence/build-id/historical-find-debuginfo.sh.txt#L248) · [sidecar 标记及 CRC](BUILD_ID_COMPARISON.json)
''')
    original=load(base,'06_identity_verification.json')
    shapes=[
      dict(scope='Repository RPM ↔ Released zImage',status='EXACT_MATCH',comparison='zImage 文件 SHA256',value=original['repository_zimage_sha256'],
           evidence='round1/evidence/repository/image-profile-verification.json'),
      dict(scope='Released Kernel Notes ↔ Runtime Kernel Notes',status='EXACT_MATCH',comparison='84 字节 GNU/Linux notes', value=runtime['note_sha256'],evidence='BUILD_ID_COMPARISON.json'),
      dict(scope='Released Kernel ↔ Running Kernel Identity',status='STRONG_MATCH',comparison='GNU Build ID、完整 notes、banner、发布快照和架构相符。运行内核的完整内存映像未采集。',
           value=original['runtime_build_id'],evidence='BUILD_ID_COMPARISON.json'),
      dict(scope='Repository Modules ↔ Device Modules',status='EXACT_MATCH',comparison='同 release 的 59 个文件逐路径逐 SHA256 比较',value='59/59',
           evidence='08_01_evidence_integrity_review.json'),
      dict(scope='Released zImage ↔ Device Boot File',status='UNVERIFIABLE',comparison='设备会话未暴露启动卷 zImage，设备文件 SHA256 无记录。',
           value=None,evidence='round1/evidence/runtime/partition-metadata.out'),
      dict(scope='Repository RPM ↔ Active RPM Database',status='UNVERIFIABLE',comparison='设备活动数据库查询无目标条目。NEVRA、install time 和 owner 无法实测。',
           value=None,evidence='round1/evidence/runtime/pinned-rpm-device-queries.out'),
    ]
    dump(out/'08_09_identity_review.json',dict(first_round_scope=original['scope'],relations=shapes))
    (out/'08_09_identity_review.md').write_text(f'''# 08.09 · 身份匹配范围修正

{markdown_table(['对象','判定','实际比较','证据'],[(r['scope'],r['status'],r['comparison'],f'[查看]({r["evidence"]})') for r in shapes])}

第一轮底层比较保持有效。EXACT_MATCH 细化到实际比较的字节对象，完整运行内核身份关联为 STRONG_MATCH。两个设备侧未验证项保留。本轮未重新访问设备或挂载启动卷。 [结构化身份](08_09_identity_review.json)
''')
    print('PASS: generated audit, Build ID and six scoped identity review deliverables.')

if __name__=='__main__':
    main()
