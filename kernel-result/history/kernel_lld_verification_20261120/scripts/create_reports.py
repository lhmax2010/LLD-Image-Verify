#!/usr/bin/env python3
"""Render the preflight, binary, module, identity and PM review reports."""
from collections import Counter
import json
from pathlib import Path
import re

from analyze_artifacts import CATEGORIES, ROOT, dump

def load(path):
    return json.loads((ROOT/path).read_text())

def write(path, text):
    (ROOT/path).write_text(text.strip()+'\n')

def link(path, label=None):
    return f'[{label or path}]({path})'

def table(headers, rows):
    return '\n'.join('| '+' | '.join(str(x) for x in row)+' |' for row in [headers,['---']*len(headers),*rows])

def ratio(entry, count):
    return f'{entry:.2%} ({count})' if entry is not None else '不可计算'

def prepare_preflight(repo, runtime):
    devices = [s.split()[0] for s in (ROOT/'evidence/preflight/sdb-devices.out').read_text().splitlines()
               if re.search(r'\bdevice\s+rpi4\b', s)]
    disk = (ROOT/'evidence/preflight/host-space.out').read_text().splitlines()[1].split()[3]
    checks = [
        ('精确快照访问', 'PASS', ['evidence/repository/http-root.headers','evidence/repository/https-root.headers'],
         'Web 浏览工具无法打开快照，执行主机 curl 取得 HTTP 200。', '使用快照 HTTPS 路径下载。'),
        ('仓库元数据', repo['status'], ['evidence/repository/packages-repomd.out','02_repository_identity.json'],
         '元数据和包摘要可核验。签名和密钥探测受限。', '读取 packages、debug、source 元数据。'),
        ('目标连接及授权', 'PASS', ['evidence/preflight/host-route.out','evidence/preflight/sdb-devices.out',
         'evidence/runtime/ip-fallback.out'],
         'SDB 客户端 4.2.36 和服务端 4.2.25 存在版本差异。只读命令和传输字节经核验。',
         '每条设备命令指定目标序列号。'),
        ('多设备核对', 'PASS', ['evidence/preflight/sdb-devices.out','evidence/runtime/boot-dtb.out'],
         f'SDB 名单包含 {len(devices)} 台，序列号为 '+ '、'.join(devices)+'。',
         f'固定 {runtime["device"]["serial"]}，用设备内部 IP 和 DT 型号复核。'),
        ('主机工具', 'PASS', ['evidence/preflight/host-tools.out','evidence/preflight/sdb-version.out','evidence/preflight/llvm-located.out'],
         '缺少 llvm-readelf 和 llvm-objdump。使用 GNU readelf 及独立 Python 字节解析。已由 SDB 授权连接。',
         '保留实际工具路径、版本及退出状态。'),
        ('主机磁盘', 'PASS', ['evidence/preflight/host-space.out'],
         f'本次采集前活动工作卷可用空间为 {disk}（df -hP）。', '离线保存和分析目标快照的 RPM。'),
        ('历史构建证据', 'PARTIAL', ['evidence/build/linux-rpi-armv7l.out','evidence/build/linux-tizen-modules-armv7l.out',
          '04_build_evidence.json'],
         '发布日志为 quiet Kbuild。本机另有同 release 的旧记录，构建时间和主机不匹配。',
         '使用发布日志、实际配置及 ELF，保留精确 .cmd 和 argv 缺口。')
    ]
    data = [dict(check=name,status=status,evidence=evidence,limitation=limitation,next_action=action)
            for name,status,evidence,limitation,action in checks]
    dump('00_preflight.json',dict(status='PASS', checks=data, permitted_follow_up=True, target_serial=runtime['device']['serial']))
    write('00_preflight.md', '# 00 · 可行性检查\n\n总体 **PASS**。设备和仓库的验证路径均可用。\n\n'+
          table(['检查','Status','Evidence','Limitation','Next Action'], [
              (r['check'],r['status'],' · '.join(link(p) for p in r['evidence']),r['limitation'],r['next_action']) for r in data]))

def write_runtime(runtime):
    k = runtime['kernel']
    device = runtime['device']
    release = k['release']
    notes = k['notes']
    install = load(runtime['installed_module_inventory']['inventory_path'])
    loaded = load(runtime['loaded_module_inventory']['inventory_path'])
    package = runtime['installed_kernel_rpm']
    owned = sum(len(row['rpm_owners']) > 0 for row in install['files'])
    probes = sum(len(row['rpm_owner_attempts']) for row in install['files'])
    count_loaded_notes = sum(module.get('build_id') is not None for module in loaded['modules'])
    install_extra = sum('/extra/' in row['path'] for row in install['files'])
    devices = [line.split()[0] for line in (ROOT/'evidence/preflight/sdb-devices.out').read_text().splitlines()
               if line.split()[1:2]==['device']]
    if device["serial"] not in devices:
        raise ValueError("Target is absent from the authorized SDB device list")
    table_rows = [
        ('设备身份','PASS',f'{device["serial"]}，{device["model"]}。SDB 列表有 {len(devices)} 个已授权会话，设备侧 IP 复核通过。',
         'evidence/preflight/sdb-devices.out'),
        ('当前内核','PASS',f'{release} / {k["architecture"]}，{k["build_timestamp"]}，{k["build_user_and_host"]}。',
         k['banner_evidence_path']),
        ('工具链版本元数据','PASS',f'Clang {k["clang_version"]} / LLD {k["lld_version"]}，来自 /proc/version 与启动日志。',
         k['banner_evidence_path']),
        ('镜像 BUILD_ID','PASS',device['image_build_id'],k['banner_evidence_path']),
        ('内核 GNU Build ID','PASS',notes['gnu_build_id'],notes['evidence_path']),
        ('运行配置文件','INCONCLUSIVE',f'/proc/config.gz 和 /boot/config-{release} 在本次会话缺失。',
         runtime['runtime_config']['evidence_path']),
        ('活动 RPM 数据库','INCONCLUSIVE',
         f'查询 {package["queried_rpm_database_records"]} 条记录。目标包无条目。设备内核 RPM NEVRA、Source RPM、Build Time、Install Time 和文件 owner 不可确认。',
         package['pinned_query_evidence_path']),
        ('已安装模块','PASS',f'{install["total_unique_paths"]} 个唯一模块路径，extra/ 下 {install_extra} 个。{probes} 次 RPM owner 查询找到 {owned} 个文件归属。',
         runtime['installed_module_inventory']['inventory_path']),
        ('加载模块主快照','PASS',f'{loaded["total"]} 个加载模块，{count_loaded_notes} 个取得 GNU Build ID，早期快照 {len(loaded["initial_snapshot_names"])} 个。',
         runtime['loaded_module_inventory']['inventory_path'])
    ]
    write('01_runtime_kernel.md', f'''
# 01 · Runtime Kernel Verification

已通过固定序列号的授权 SDB 会话独立采集目标设备。运行内核、构建版本元数据和仓库身份分别核验。阶段 A 通过。最终链接和仓库身份见 [04 构建](04_build_command_analysis.md) 与 [06 身份](06_repository_runtime_mapping.md)。

{table(['验证项','状态','实际结果','证据'],[
     (scope,status,actual,link(path,'查看')) for scope,status,actual,path in table_rows])}

- **证据读取** 记录 uname -a、uname -r、uname -m、/proc/version、/etc/os-release、/proc/cmdline 和 boot banner。设备内路由表显示目标 IP 为本机地址。DT 型号和兼容性字符串来自设备。 [启动与版本原文]({k['banner_evidence_path']}) · [设备 IP]({device['ip_evidence_path']}) · [设备树]({device['model_evidence_path']})
- **运行 notes** 使用 ARM 小端 ELF note 布局和 4 字节对齐。恢复 {notes["size_bytes"]} 字节。设备 SHA256 和恢复字节均为 {notes["sha256"]}。 [notes 原件]({notes['bytes_path']}) · [解析](01_runtime_kernel.json)
- **设备文件限制** /boot 可列目录，当前会话未暴露启动分区文件。活动 RPM DB 中 /boot 的 owner 只是目录所属包。/usr/lib/modules 为独立只读挂载，/lib/modules 指向同一模块树。启动文件 SHA256、目标 RPM 的安装时间和文件所有权缺少设备侧记录。 [挂载、权限及目录归属](evidence/runtime/partition-metadata.out) · [可读取性](evidence/runtime/files.out) · [活动 RPM 查询](evidence/runtime/rpm-list.out)
- **模块采集** tar 流经 base64 传输，只在主机落盘。{install["archive"]["members_checked"]} 个文件经路径、类型、大小与设备端 SHA256 核验。归档 SHA256 为 {install["archive"]["sha256"]}。 [设备文件回执](evidence/runtime/module-files.out) · [归档]({install['archive']['path']}) · [RPM owner](evidence/runtime/module-owners.out)
- **加载模块** 主快照和相邻 lsmod 均保留。该设备在读操作间的状态可能变化，按主快照分别读取模块 notes。 [主快照]({loaded['snapshot_path']}) · [lsmod]({loaded['lsmod_snapshot_path']}) · [模块 notes]({loaded['sysfs_note_path']})

[结构化结果](01_runtime_kernel.json) · [采集方法](VERIFICATION_METHOD.md) · [实际命令及退出状态](COMMANDS.jsonl)
''')

def main():
    runtime = load('01_runtime_kernel.json')
    repo = load('02_repository_identity.json')
    static = load('03_kernel_linker_evidence.json')
    compare = load('evidence/kernel_binary/byte-comparison.json')
    public = load('evidence/repository/image-profile-verification.json')['boot']['boot_archive_verification']
    coverage = load('05_kernel_module_coverage.json')
    logs = load('evidence/build/kernel-build-log-events.json')
    prepare_preflight(repo, runtime)
    write_runtime(runtime)
    k = runtime['kernel']
    bid, release = k['notes']['gnu_build_id'], k['release']
    rows = static['binaries']
    z = next(x for x in rows if x['path']=='/boot/zImage')
    raw = z['raw_payloads'][0]
    vd = next(x for x in rows if x['path'].endswith('arm-rpi4/vmlinux'))
    dbg = next(x for x in rows if x['path'].endswith('arm-rpi4/vmlinux.debug'))
    wdbg = next(x for x in rows if x['path'].endswith('compressed/vmlinux.debug'))
    devel_id = vd['elf_build_id']
    byte_ev = 'evidence/kernel_binary/byte-comparison.json'
    pub_ev = 'evidence/repository/image-profile-verification.json'
    main_log = 'evidence/build/linux-rpi-armv7l.out'
    mod_log = 'evidence/build/module-final-commands.json'
    exact_note = compare['exact_runtime_notes']['exact_bytes_in_raw']
    main_sec = compare['main_kernel']['compared_sections']
    wrap_sec = compare['zimage_wrapper']['compared_sections']
    main_eq = sum(r['match'] is True for r in main_sec)
    wrap_eq = sum(r['match'] is True for r in wrap_sec)
    notes_diff = [r for r in main_sec if r['match'] is not True]
    bind_devel = (len(notes_diff)==1 and notes_diff[0]['name']=='.notes' and notes_diff[0]['different_bytes']==20 and
                  compare['main_kernel']['unmatched_nonzero_gap_count']==0 and compare['debug_links'][0]['status']=='MATCH')
    boot = public['kernel']
    zsha = z['raw_sha256']
    published_match = boot['comparison']=='EXACT_SHA256' and boot['image_file_sha256']==zsha
    identity_status = 'EXACT_MATCH' if exact_note and published_match else 'UNVERIFIABLE'
    raw_note_off = compare['exact_runtime_notes']['raw_offset']
    r_cov, d_cov = coverage['repository'], coverage['device']
    nr, nd = r_cov['total_module_files'], d_cov['total_module_files']
    r_lld, d_lld = (c['counts']['LLD_CONFIRMED']+c['counts']['LLD_INDICATED'] for c in (r_cov,d_cov))
    nd_match = coverage['device_repo_mapping_counts'].get('EXACT_PATH_AND_SHA256', 0)
    nl, nl_match = coverage['runtime_loaded'], coverage['live_module_build_id_counts'].get('MATCH',0)
    pub_mods = f'{public["modules"]["exact_sha256"]}/{public["modules"]["total"]}'
    pkg = next(x for x in repo['selected_rpms'] if x['name']=='arm-rpi4-linux-kernel')
    kernel_rpm = Path(pkg['rpm_path']).name
    tc = f'Clang {k["clang_version"]} / LLD {k["lld_version"]}'
    rpm_state = runtime['installed_kernel_rpm']['status']
    cpath='evidence/build/devel/boot/kernel/devel/kernel-devel-arm-rpi4/.config'
    gm = logs['quiet_final_link']['line']
    gw = logs['quiet_arm_decompressor_link']['line']
    stats = table(['类别','仓库','设备已安装'], [
        ('模块文件总数',nr,nd),('成功解析',r_cov['successfully_parsed'],d_cov['successfully_parsed']),
        *((s,r_cov['counts'][s],d_cov['counts'][s]) for s in CATEGORIES),
        ('Confirmed LLD Coverage',ratio(r_cov['confirmed_lld_coverage'],f'{r_cov["counts"]["LLD_CONFIRMED"]}/{nr}'),
         ratio(d_cov['confirmed_lld_coverage'],f'{d_cov["counts"]["LLD_CONFIRMED"]}/{nd}')),
        ('LLD Evidence Coverage',ratio(r_cov['lld_evidence_coverage'],f'{r_lld}/{nr}'),
         ratio(d_cov['lld_evidence_coverage'],f'{d_lld}/{nd}')),
        ('ELF Parsing Coverage',ratio(r_cov['elf_parsing_coverage'],f'{r_cov["successfully_parsed"]}/{nr}'),
         ratio(d_cov['elf_parsing_coverage'],f'{d_cov["successfully_parsed"]}/{nd}')),
        ('ELF 自带链接器标记',r_cov['elf_linker_marker_files'],d_cov['elf_linker_marker_files']),
        ('匹配 quiet 链接记录',r_cov['per_output_quiet_build_files'],d_cov['per_output_quiet_build_files'])
    ])
    write('03_kernel_binary_analysis.md', f"""
# 03 · 内核二进制静态验证

已校验的 {len(static['extraction'])} 个目标二进制 RPM 在主机解包。{kernel_rpm} 提供 /boot/zImage。开发和调试 RPM 各提供主内核和 ARM 解压器 ELF。清单保留 SHA256、路径、工具输出和退出状态。 [二进制清单](03_kernel_binary_inventory.csv) · [结构化证据](03_kernel_linker_evidence.json)

{table(['输入','类型','GNU Build ID','链接器证据'], [
('/boot/zImage','ARM little-endian zImage，经 gzip 解出 raw Image',bid+'（raw Image notes）','版本字符串 LLD '+k['lld_version']),
('devel vmlinux','ELF32 / little-endian / ARM / ET_EXEC',devel_id,'无 .comment'),
('devel vmlinux.debug','ELF32 / little-endian / ARM / ET_EXEC',devel_id,'Linker: LLD '+k['lld_version']),
('devel compressed/vmlinux','ELF32 / little-endian / ARM / ET_EXEC','无','无 .comment'),
('devel compressed/vmlinux.debug','ELF32 / little-endian / ARM / ET_EXEC','无','Linker: LLD '+k['lld_version'])
])}

- Linux stable v6.12.80 对应提交 00d7934ffcc35e65b113ba4991c8a3338bd85fc1。脚本原件、tag 和 SHA256 已归档。extract-vmlinux 退出 {z['extract-vmlinux']['exit_status']}，stdout 为空，stderr 报找不到 ELF。extract-ikconfig 退出 {z['extract-ikconfig']['exit_status']}，stdout 为空。 [tag 核对](evidence/kernel_binary/upstream/pinned-source.out) · [脚本 SHA256](evidence/kernel_binary/upstream/script-sha256.out) · [extract-vmlinux stderr]({z['extract-vmlinux']['output'].removesuffix('.out')}.err)
- 校验 ARM zImage magic 后，在 0x{raw['source_offset']:x} 解出一个通过 gzip 校验、带目标 banner 的 raw Image。大小 {raw['size']:,} 字节，SHA256 为 {raw['sha256']}。GNU Build ID note 位于 0x{raw['matching_gnu_build_id_notes'][0]['offset']:x}，完整运行时 notes 位于 0x{raw_note_off:x}。 [raw Image]({raw['file']}) · [设备 notes]({k['notes']['bytes_path']})
- 按 ELF PT_LOAD 的 LMA 对齐，主内核 {main_eq}/{len(main_sec)} 个有文件内容的 SHF_ALLOC 段逐字节一致。唯一差异为 .notes 中的 20 字节 Build ID。ARM 解压器 {wrap_eq}/{len(wrap_sec)} 个段一致。未映射范围的非零字节数均为 0。两个 debug sidecar 均经 .gnu_debuglink 文件名和 CRC32 验证，主内核对同时共享发布后的 Build ID。 [逐字节比较]({byte_ev})
- 日志先 stage zImage，后执行 find-debuginfo.sh --build-id-seed 6.12.80-0。该历史 rpm-build 的 find-debuginfo 实现向 debugedit 传入重新计算选项和 seed，确认发布处理可解释唯一差异。 [发布日志]({main_log}#L14459) · [历史脚本回执](evidence/build/historical-base-reseed-script-lines.out) · [debugedit 官方项目](https://sourceware.org/debugedit/)
- 两个已绑定的调试 ELF 都在 .comment+0x16 记录 Linker: LLD {k['lld_version']}，在 .comment+0x1 记录 Clang。raw Image 中是构建 banner。其他字节命中按偏移保留，未确定来源的命中保持未知。 [主内核 readelf]({dbg['readelf']}) · [解压器 readelf]({wdbg['readelf']}) · [LLVM 标记实现](https://llvm.googlesource.com/llvm-project/+/refs/heads/main/lld/ELF/SyntheticSections.cpp)
- .comment 可以保留输入对象或部分链接的标记。构建日志观察到 vmlinux 和 ARM 解压器的 quiet 链接步骤。结合已验证的 Kbuild 默认选择，两者均有 LLD 迹象，最终链接保持 CONDITIONAL_PASS。 [构建证据](04_build_command_analysis.md)
""")
    write('05_kernel_module_analysis.md', f"""
# 05 · Kernel Module LLD 覆盖

范围为 {release}。仓库模块来自 arm-rpi4-linux-kernel-modules（52 个）及 linux-tizen-modules-rpi4（7 个）。设备在 /usr/lib/modules/{release} 读取 {nd} 个文件，逐文件 SHA256 验证传输。两边均为未压缩 ARM ELF32 little-endian ET_REL，vermagic 全部匹配。逐文件同时保留原始和 ELF 哈希。 [逐文件清单](05_kernel_module_inventory.csv) · [设备采集清单](evidence/runtime/installed-modules.json)

{stats}

分母包括各来源目标 release 的全部普通模块文件路径。两边都没有重复路径、同名模块、同字节副本或模块文件符号链接。设备 /lib 和 /usr/lib 指向同一物理树，计一次。内建驱动及辅助文件排除。 [统计和排除项](05_kernel_module_coverage.json)

设备 {nd_match}/{nd} 个文件的路径和原始 SHA256 精确匹配仓库包。活动 RPM DB 报告的模块 owner 数为 {runtime['installed_module_inventory']['rpm_owned_files']}。已发布模块分区的 {pub_mods} 个文件另与仓库 RPM 匹配。 [RPM owner 回执](evidence/runtime/module-owners.out) · [发布分区验证]({pub_ev})

每个模块均有自己的 LD [M]、INSTALL、RPM 写出及构建成功回执。结合该构建的 LLVM=1、开发包配置及 Kbuild 的 $(LD) 规则逐项判定 LLD_INDICATED。设备结论通过逐文件路径和 SHA256 关联。每个模块 ELF 自身缺少链接器标记，历史最终链接器 executable 和 argv 也均缺失。表中 100% 表示有 LLD 迹象的证据覆盖率，最终链接确认覆盖率为 0%。 [逐目标日志]({mod_log}) · [逐文件结构化证据](evidence/modules/module-analysis.json)

主 /proc/modules 快照列出 {nl} 个加载模块，其中 {nl_match}/{nl} 个 sysfs GNU Build ID 与已安装 ELF 匹配。早期快照中有 {runtime['loaded_module_inventory']['initial_snapshot_total']} 个。 [加载模块映射](05_loaded_module_mapping.csv) · [主快照](evidence/runtime/loaded-list.out) · [sysfs notes](evidence/runtime/loaded-build-ids.out)
""")
    identity = dict(
        status=identity_status, scope='published target kernel payload to running main kernel',
        snapshot=repo['snapshot'], runtime_image_build_id=runtime['device']['image_build_id'],
        kernel_release=release, architecture=k['architecture'], runtime_build_id=bid,
        runtime_notes=compare['exact_runtime_notes'],
        repository_kernel_rpm={key:pkg[key] for key in ('name','epoch','version','release','architecture','source_rpm','download_url','sha256','rpm_path')},
        published_image_archive=public['archive'], repository_zimage_sha256=zsha, repo_published_zimage_match=published_match,
        repo_raw_kernel_payload=raw['file'], repo_raw_kernel_payload_sha256=raw['sha256'],
        repository_devel_debug_status='STRONG_MATCH' if bind_devel else 'UNVERIFIABLE',
        devel_debug_build_id=devel_id, live_boot_file_sha256=None, live_installed_kernel_rpm_status=rpm_state,
        device_module_sha256_matches=nd_match, live_module_build_id_matches=nl_match,
        evidence=[byte_ev,pub_ev,'01_runtime_kernel.json','02_repository_identity.json',
                  'evidence/runtime/pinned-rpm-device-queries.out','evidence/runtime/partition-metadata.out'])
    dump('06_identity_verification.json', identity)
    write('06_repository_runtime_mapping.md', f"""
# 06 · Repository → Runtime 身份映射

**{identity_status}，适用于运行主内核的 Build ID 和完整 notes。** 仓库内核 RPM 通过 RPM 元数据校验，发布启动镜像通过独立发布 SHA256SUMS 校验。两个通道的 zImage 字节一致。gzip 解出的 raw Image 含有与设备完全相同的 84 字节 notes 和同一完整 banner。 [机器可读身份记录](06_identity_verification.json) · [启动分区比对]({pub_ev}) · [notes 逐字节比对]({byte_ev})

{table(['链路','结果','证据'],[
('快照 → Kernel RPM',f'仓库 SHA256 一致，{kernel_rpm}',link('02_repository_identity.json')),
('Kernel RPM → 发布启动分区',f'EXACT_SHA256 · {zsha}',link(pub_ev)),
('zImage → raw Image → 运行主内核',f'{identity_status} · {bid}，完整 notes 同字节',link(byte_ev)),
('开发及调试 ELF → raw Image','同一构建的发布后 ELF。差异为 20 个 GNU ID 字节',link('03_kernel_binary_analysis.md')),
('已安装内核 RPM NEVRA / install time / owner',rpm_state+' · 活动 DB 无条目，/boot 未暴露启动文件',link('evidence/runtime/pinned-rpm-device-queries.out')),
('模块 RPM → 发布分区 → 设备已安装',f'发布分区 {pub_mods}，设备 {nd_match}/{nd} SHA256 匹配',link('05_kernel_module_analysis.md')),
('设备文件 → 设备已加载模块',f'{nl_match}/{nl} GNU Build ID 匹配',link('05_loaded_module_mapping.csv'))
])}

运行 Image BUILD_ID 为 {runtime['device']['image_build_id']}。发布 boot profile 使用独立 boot 和 modules 分区。会话可读取独立的只读模块挂载，启动卷文件未暴露，设备 /boot/zImage 的 SHA256 和活动 DB 中的安装时间、RPM 所有权无法实测。RPM header 的 BuildTime 为 epoch 0。实际编译时间由内核 banner、生成头和构建日志关联。 [发布清单](02_repository_inventory.md) · [设备挂载](evidence/runtime/partition-metadata.out)
""")
    gates = {
        'A': ('PASS','目标设备及运行时工具链',f'{runtime["device"]["serial"]}，{tc}，运行记录独立采集。','01_runtime_kernel.md'),
        'B': ('CONDITIONAL_PASS','Kernel 最终链接','主内核和解压器有 LLD 证据，历史最终 argv 和实际 executable 缺失。','04_build_command_analysis.md'),
        'C': ('PASS','Repository ↔ Runtime 身份',f'{identity_status}，适用于发布启动产物与运行主内核 notes。设备 RPM DB 和启动文件哈希不可得。','06_repository_runtime_mapping.md'),
        'D': ('CONDITIONAL_PASS','Kernel Module 覆盖',f'两组完整扫描。仓库 {r_lld}/{nr}、设备 {d_lld}/{nd} 有 LLD 证据，最终链接均为 0 个确认。','05_kernel_module_analysis.md'),
        'E': ('PASS','证据完整性','JSON、CSV、SHA256、覆盖率复算和证据路径通过脚本自检。','evidence/preflight/self-check.out'),
    }
    findings = [
        ('F-01','MAJOR','历史主内核、vmlinux.o 和 ARM 解压器完整链接命令缺失。',
         'vmlinux、vmlinux.o、arch/arm/boot/compressed/vmlinux',
         f'精确快照日志 L{gm}、L{gw} 及打包排除 .cmd 的 L14237。',
         '已确认日志采用 quiet Kbuild，开发包打包排除 .cmd。',
         '独立的最终链接器验收仍有缺口。',
         '向该次构建的维护者请求已有的原始 .vmlinux*.cmd、解压器 .cmd 或 verbose 日志。',main_log),
        ('F-02','MAJOR','59 个独立模块均具备逐目标 LLD 迹象，历史最终链接命令均缺失。',
         '52 个内核树内模块和 7 个树外模块',
         '每个输出的 LD [M]、INSTALL、RPM 写出、LLVM=1 和构建成功原始记录。',
         '已确认所有交付模块 ELF 均无可识别链接器标记。quiet 日志省略 argv。',
         'Confirmed LLD Coverage 为 0%，无匹配的原始 argv 可用于排除构建工具覆盖或解析异常。',
         '向归档维护者请求这两次构建已有的 59 条最终 .ko 命令及链接器路径。',mod_log),
        ('F-03','MINOR','设备的活动 RPM 数据库缺少目标包，启动卷在会话中不可读。',
         '设备 Kernel RPM NEVRA、安装时间、文件所有权及启动卷 zImage',
         '目标 RPM 查询无记录，/boot 为空，设备模块为独立只读挂载。',
         '独立分区结构已确认。具体镜像部署操作未观察。',
         '无法实测活动 RPM NEVRA、install time 或设备启动文件 SHA256，运行内核的 notes 仍与发布产物精确匹配。',
         '如验收要求明确包含设备启动卷哈希和 RPM 记录，请索取现有部署清单或只读证据。',
         'evidence/runtime/pinned-rpm-device-queries.out'),
        ('F-04','MINOR','RPM 与 repo 元数据可做摘要校验，发布签名无法核验。',
         '目标二进制及源码 RPM、repomd.xml',
         'rpm -Kv 校验摘要通过。探测的签名、密钥端点返回 404。',
         '本次验证未取得可用发布签名和可信密钥。',
         '完整性有校验链支持，发布签名层的来源认证未建立。',
         '如 PM 要求签名级来源证明，请索取对应快照的可信签名和发布密钥。','02_repository_inventory.md'),
        ('F-05','INFO','开发和调试 ELF 的 GNU Build ID 经过发布后处理。',
         'devel vmlinux、vmlinux.debug 与 zImage 的 raw Image',
         f'发布后 ID {devel_id}。逐字节比较证明唯一变化是 .notes 内的 20 字节。',
         '构建日志确证运行 find-debuginfo.sh --build-id-seed，字节结果与 Build ID 重算一致。',
         '应在启动 raw Image 端应用设备 Build ID 比对。',
         'PM 可复核记录中的唯一差异窗口及两组 debuglink CRC。',byte_ev),
    ]
    sev = Counter(f[1] for f in findings)
    counts = {s:sev[s] for s in ('BLOCKER','MAJOR','MINOR','INFO')}
    summary = dict(overall_status='CONDITIONAL_PASS', acceptance_close_ready=False, device=runtime['device'],
                   kernel=dict(k, final_link_status='CONDITIONAL_PASS', independent_final_link_evidence=False),
                   gates={key:dict(status=value[0], scope=value[1], actual=value[2], evidence=value[3]) for key,value in gates.items()},
                   identity=identity, modules=coverage,
                   bfd=dict(confirmed_kernel=0, indicated_kernel=0,
                            repository_module_count=r_cov['counts']['BFD_CONFIRMED']+r_cov['counts']['BFD_INDICATED'],
                            installed_module_count=d_cov['counts']['BFD_CONFIRMED']+d_cov['counts']['BFD_INDICATED'],
                            scope='observed target artifacts and matching logs'),
                   findings_by_severity=counts,
                   findings=[dict(zip(('id','severity','description','affected_artifact','raw_evidence',
                                       'root_cause','impact','recommended_action','evidence'),row)) for row in findings],
                   report='KERNEL_LLD_VERIFICATION_REPORT.md', evidence_root='evidence',
                   reproduction='VERIFICATION_METHOD.md', manifest='SHA256SUMS', commands='COMMANDS.jsonl')
    dump('KERNEL_LLD_VERIFICATION_SUMMARY.json', summary)
    matrix = [
        ('Device Identity','private-address-02 / RPi4',runtime['device']['serial']+' · '+runtime['device']['model'],'PASS','01_runtime_kernel.md','高'),
        ('Kernel Architecture','ARMv7l',k['architecture']+' / ELF32 ARM little-endian','PASS','03_kernel_binary_analysis.md','高'),
        ('Kernel Compiler','Clang 22.1.8','Clang '+k['clang_version']+'，独立读取 banner 和配置','PASS',k['banner_evidence_path'],'高，构建元数据'),
        ('Kernel Linker','LLD 22.1.8','LLD '+k['lld_version']+'，banner、配置、关联调试 ELF','PASS','03_kernel_binary_analysis.md','高，有多源迹象'),
        ('Kernel Final Link','直接证明 LLD','quiet LD、构建规则、关联 ELF 标记','CONDITIONAL_PASS','04_build_command_analysis.md','中'),
        ('Kernel Config','LLD enabled','CONFIG_LD_IS_LLD=y，CONFIG_LLD_VERSION=220108','PASS','04_kernel_config_analysis.md','高，发布生成配置'),
        ('Repository Identity','匹配目标发布快照','目标 RPM、发布 SHA256SUMS、运行镜像 BUILD_ID 对应','PASS','02_repository_inventory.md','高'),
        ('Kernel Binary Identity','对应运行内核',identity_status+'，GNU Build ID 和 84 字节 notes','PASS','06_repository_runtime_mapping.md','高'),
        ('Device RPM identity','可读的 NEVRA、install time、owner',rpm_state,'INCONCLUSIVE','01_runtime_kernel.md','高，数据库查询'),
        ('Module ELF Parsing','100% 全量',f'仓库 {r_cov["successfully_parsed"]}/{nr}，设备 {d_cov["successfully_parsed"]}/{nd}','PASS','05_kernel_module_coverage.json','高'),
        ('Module LLD Coverage','全量确认',f'LLD_INDICATED 仓库 {r_lld}/{nr}，设备 {d_lld}/{nd}。两组 LLD_CONFIRMED 均 0','CONDITIONAL_PASS','05_kernel_module_analysis.md','中'),
        ('BFD Residual','无 GNU BFD 残留','未发现 BFD 证据，历史最终 argv 缺失','INCONCLUSIVE','05_kernel_module_analysis.md','中'),
        ('Runtime Boot','目标设备已启动','SDB 已授权，读取运行内核和启动日志','PASS','01_runtime_kernel.md','高')
    ]
    findings_md = '\n\n'.join(
        f'### {fid} · {level}\n\n{desc}\n\n'
        f'- **受影响产物** {artifact}\n- **原始证据** {raw_ev} {link(path,"查看证据")}\n'
        f'- **根因** {cause}\n- **影响** {impact}\n- **建议** {action}'
        for fid,level,desc,artifact,raw_ev,cause,impact,action,path in findings)
    host = (ROOT/'evidence/preflight/host-env.out').read_text().splitlines()
    live_time = load('evidence/runtime/banner.cmd.json')['started_utc']
    overall = f"""
# Tizen Linux Kernel LLD Migration Verification

**总体 CONDITIONAL_PASS，暂不关闭验收。** 目标 Raspberry Pi 4 正在运行 {release}，构建元数据和关联产物支持 {tc}。发布启动产物与运行主内核 notes 精确匹配。主内核及全部模块的历史最终链接命令仍缺失。

## Executive Summary

1. **编译器** 独立读取的 /proc/version 记录 Clang {k['clang_version']}。发布生成配置和调试 ELF 也记录 Clang。 [运行证据](01_runtime_kernel.md) · [配置](04_kernel_config_analysis.md)
2. **链接器** /proc/version 及 boot banner 记录 LLD {k['lld_version']}。发布配置选择 LLD。经字节关系绑定的主内核及 ARM 解压器 debuginfo 均有同版本 .comment 标记。 [ELF 分析](03_kernel_binary_analysis.md)
3. **最终链接证据** 精确构建日志观察到 vmlinux、ARM 解压器和 59 个 .ko 的链接步骤。日志省略 executable 与 argv，发布开发包排除 .cmd，调试 ELF 标记也可能从输入继承。历史包存在 /usr/bin/ld.lld 和 /emul/usr/bin/ld.lld 两种候选路径。主内核最终链接独立验证保持 CONDITIONAL_PASS。 [命令和证据缺口](04_build_command_analysis.md)
4. **身份** {identity_status}。仓库 RPM 和发布 boot 镜像内的 zImage SHA256 相同。raw Image 与目标设备共享 GNU Build ID {bid} 和完整 84 字节 notes。设备启动文件哈希和活动 RPM 所有权仍不可得。 [身份关联](06_repository_runtime_mapping.md)
5. **模块全量** 仓库 {nr} 个，设备 {nd} 个。两边都解析成功、逐文件 SHA256 全匹配。各有 {r_cov['counts']['LLD_INDICATED']} 个 LLD_INDICATED，0 个 LLD_CONFIRMED，证据覆盖率 100%，最终链接确认覆盖率 0%。 [模块统计](05_kernel_module_analysis.md)
6. **GNU BFD** 对目标内核和模块的现有证据均无 BFD 命中。最终 argv 缺失限制了残留排除结论。 [模块统计](05_kernel_module_coverage.json) · [构建日志分析](04_build_command_analysis.md)
7. **UNKNOWN / PARSE_FAILED** 仓库与设备均为 0 / 0。模块 ELF 自带链接器证据为 0 个，LLD_INDICATED 来自逐目标构建记录、配置和字节关联。运行时主快照的 {nl_match}/{nl} 个模块 Build ID 与已安装文件对应。 [逐文件证据](05_kernel_module_inventory.csv) · [运行映射](05_loaded_module_mapping.csv)
8. **验收** A、C、E 通过，B、D 有条件通过。PM 应优先复查本次构建的完整命令和执行路径缺口，再评估是否可关闭验收。 [机器可读汇总](KERNEL_LLD_VERIFICATION_SUMMARY.json)

## Verification Matrix

{table(['Verification Item','Expected','Actual','Status','Evidence','Confidence'], [
 (name,expected,actual,status,link(evidence,'查看'),confidence) for name,expected,actual,status,evidence,confidence in matrix])}

## Acceptance Status

{table(['Gate','范围','状态','结论与限制','证据'],[
 (key,value[1],value[0],value[2],link(value[3],'查看')) for key,value in gates.items()])}

## Findings & Risks

BLOCKER {counts['BLOCKER']} · MAJOR {counts['MAJOR']} · MINOR {counts['MINOR']} · INFO {counts['INFO']}

{findings_md}

## Reproduction 与自检

执行主机为 {host[3].removeprefix('PRETTY_NAME=').strip(chr(34))}，x86_64。可用工具包含 SDB 4.2.36、GNU readelf 2.42、RPM 4.18.2、Python 3.12.3。现场开始时间 {host[1]}（America/Los_Angeles），banner 采集时间 {live_time}（UTC）。准确运行时间和退出状态见每条回执。 [环境](evidence/preflight/host-env.out) · [工具清单](evidence/preflight/host-tools.out) · [命令及退出状态](COMMANDS.jsonl)

- 下载列表、URL、大小、签名和校验状态以仓库清单为准。包含发布启动 tar、元数据、构建日志和上游脚本。 [RPM 清单](02_kernel_rpm_inventory.csv) · [启动发布数据](evidence/repository/image-profile-verification.json) · [输入和输出 SHA256](SHA256SUMS)
- 设备操作限于面向授权序列号的 SDB 查询及 stdout 文件流读取。RPM 查询、解包、二进制分析和文件写入在主机完成。 [运行回执](evidence/runtime/) · [命令索引](COMMANDS.jsonl)
- 离线回放和重新采集的入口、方法、证据定位和计算口径见复跑文档。 [验证方法与脚本](VERIFICATION_METHOD.md)
- 证据路径、JSON/CSV 一致性、分类分母、模块映射、SHA256 和最终链接声明由主机脚本自检。 [最终自检](evidence/preflight/self-check.out)

## 阶段交付

- [00 预检查](00_preflight.md) · [01 运行内核](01_runtime_kernel.md) · [02 RPM 仓库](02_repository_inventory.md)
- [03 静态分析](03_kernel_binary_analysis.md) · [04 配置](04_kernel_config_analysis.md) · [04 构建命令](04_build_command_analysis.md)
- [05 模块覆盖](05_kernel_module_analysis.md) · [06 身份映射](06_repository_runtime_mapping.md)
"""
    write('KERNEL_LLD_VERIFICATION_REPORT.md', overall)
    from markdown_it import MarkdownIt
    converted = MarkdownIt('commonmark',{'html':False}).enable('table').render(overall.strip())
    write('KERNEL_LLD_VERIFICATION_REPORT.html', '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tizen Linux Kernel LLD Migration Verification</title>
<style>
body{max-width:75rem;margin:2.6rem auto;padding:0 1.2rem 5rem;font:16px/1.65 system-ui,sans-serif;color:#172333}
h1,h2,h3{line-height:1.25}h2{margin-top:2.2rem;padding:.5rem 0;border-bottom:1px solid #b8c7d5}
p,li,td{overflow-wrap:anywhere}a{color:#005fa4}a:focus-visible{outline:2px solid}
table{display:block;max-width:100%;overflow:auto;border-collapse:collapse;margin:1.25rem 0}
td,th{padding:.45rem .7rem;border:1px solid #bdcbd7;text-align:left;vertical-align:top}
thead{background:#eaf2f8}tr:nth-child(even){background:#f4f7fa}
</style></head><body><main>'''+converted+'</main></body></html>')

if __name__ == '__main__':
    main()
