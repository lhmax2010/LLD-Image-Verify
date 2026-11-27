# 11F · ARMv7l RPi4 非 RT 树外模块 ELF 比较

**`PASS_STATIC_CHECKS`。** 比较旧 QB `tizen-unified-toolchain_20261120.082536` 与新 QB `tizen-unified-toolchain_20261125.130358` 的同一组七个 `.ko`。六个同包模块逐字节一致，只有 `kdbus.ko` 的 ELF 文件发生变化。已检查的模块 ABI 接口、ARM 属性有效值、重定位和版本 CRC 未发现不兼容信号。结论限于发布文件的静态检查，运行时验证仍待新镜像部署。 [结构化结果](11F_MODULE_ABI_SUMMARY.json) · [检查命令记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

| 模块 | 旧/新文件字节数 | 差值 | 旧/新重定位条目 | 每版 CRC 匹配数 |
| --- | ---: | ---: | ---: | ---: |
| `dm-bow.ko` | 31,868 / 31,868 | 0 | 541 / 541 | 56 |
| `extcon-usb-fixed.ko` | 6,156 / 6,156 | 0 | 32 / 32 | 9 |
| `inform-reboot.ko` | 7,052 / 7,052 | 0 | 59 / 59 | 16 |
| `kdbus/kdbus.ko` | 162,584 / 161,292 | −1,292 | 2,972 / 2,972 | 154 |
| `logger.ko` | 23,664 / 23,664 | 0 | 294 / 294 | 42 |
| `proc-tsm.ko` | 10,680 / 10,680 | 0 | 95 / 95 | 26 |
| `zlogger/zlogger.ko` | 31,628 / 31,628 | 0 | 658 / 658 | 53 |

14 个被比较的 ELF 均为 ARM ELF32、little-endian、`ET_REL`、EABI5，`e_flags=0x05000200` 标记 soft-float ABI。新旧 `kdbus.ko` Build ID 分别为 `b85657c98fa68ebf43a90520861cd8f461c0abad` 和 `9527dadadaaf6aae09ce7fb483d2878b857375f6`。其旧文件 SHA-256 为 `1186ce63d4c7c5f995fd0099becfe8834d52da35939d285f5c0bd9d62042a576`，新文件 SHA-256 为 `1f851deb321d6f9fde822d67ffa17ff0eb3b443349f3ce210c737327116fe860`。 [完整尺寸和摘要](11F_MODULE_SIZE_COMPARISON.csv) · [旧 ELF 原始输出](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [新 ELF 原始输出](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

## `kdbus.ko` 节区差异

| 节区或记录 | 旧字节 | 新字节 | 差值 | 内容检查 |
| --- | ---: | ---: | ---: | --- |
| `.text` | 67,428 | 67,428 | 0 | SHA-256 相同 |
| `.rodata` | 1,256 | 1,256 | 0 | SHA-256 相同 |
| `.data` | 52 | 52 | 0 | SHA-256 相同 |
| `.bss` | 29 | 29 | 0 | `SHT_NOBITS`，各占 0 文件字节 |
| `.init.text` | 160 | 160 | 0 | SHA-256 相同 |
| `.exit.text` | 48 | 48 | 0 | SHA-256 相同 |
| `.modinfo` | 221 | 221 | 0 | SHA-256 相同 |
| `.symtab` | 14,032 | 12,736 | −1,296 | 少 81 条各 16 字节的本地 `$d` 映射符号 |
| `.strtab` | 7,692 | 7,692 | 0 | SHA-256 相同 |
| `.ARM.attributes` | 50 | 54 | +4 | 多两个显式的零值属性 |
| `.BTF` | 26,749 | 26,749 | 0 | SHA-256 相同 |
| `.BTF.base` | 937 | 937 | 0 | SHA-256 相同 |
| `__versions` | 9,856 | 9,856 | 0 | 记录顺序变化，154 个名称与 CRC 对全部一致 |
| 14 个 `.rel*` 节区合计 | 23,776 | 23,776 | 0 | 13 节原始记录字节变化，按符号解析后均等价 |
| `.rela*` | 0 | 0 | 0 | 两版本均无 |

`.ARM.attributes` 新记录 `Tag_ABI_PCS_R9_use=V6` 和 `Tag_ABI_FP_exceptions=Unused` 的编码值均为零，旧版省略这两个文件级公有标签。两份 ELF 均未记录 `Tag_nodefaults`，根据 Arm Addenda32 的缺省规则，两处属性的有效值相同。其余已记录标签相同。 [Arm 文件级属性缺省规则](https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst#default-values-for-public-tags) · [Arm PCS 与浮点属性定义](https://github.com/ARM-software/abi-aa/blob/main/addenda32/addenda32.rst#the-procedure-call-related-attributes)

## 符号、重定位和模块元数据

- `kdbus.ko` 定义的本地符号由 565 个降至 484 个。唯一符号差异分组为 `LOCAL / NOTYPE / DEFAULT` 的 `$d`，从 183 个变为 102 个。158 个已定义全局符号和 153 个未定义全局符号保留相同类型、绑定、可见性及尺寸。七个模块的弱符号和导出集合均无变化，均未发现 `__ksymtab` 导出。 [符号差异](11F_MODULE_SYMBOL_DIFF.csv) · [旧完整符号数据](evidence/binary/parsed/old/extra/kdbus/kdbus.ko.json) · [新完整符号数据](evidence/binary/parsed/new/extra/kdbus/kdbus.ko.json)
- `kdbus.ko` 的 2,972 条重定位按链接节区、源节区、偏移、类型、目标符号和目标值比较后均等价。14 个重定位源节区内容 SHA-256 逐一相同，覆盖 ARM REL 在原地存储的隐式 addend 字节。原始 `.rel*` 记录的符号表索引及文件布局有变化。七个模块合计 4,651 条记录，新旧均未发现新类型、目标或异常类型。差异 CSV 仅有表头，完整的旧/新重定位条目保存在各模块的解析 JSON。 [重定位差异](11F_MODULE_RELOCATION_DIFF.csv) · [旧完整重定位数据](evidence/binary/parsed/old/extra/kdbus/kdbus.ko.json) · [新完整重定位数据](evidence/binary/parsed/new/extra/kdbus/kdbus.ko.json)
- `kdbus.ko` 的 ARM 类型及计数为 `R_ARM_CALL` 1,379、`R_ARM_ABS32` 340、`R_ARM_PREL31` 333、`R_ARM_MOVW_ABS_NC` 301、`R_ARM_MOVT_ABS` 292、`R_ARM_NONE` 193、`R_ARM_REL32` 89、`R_ARM_JUMP24` 45。 [每模块类型统计](11F_MODULE_ABI_SUMMARY.json)
- 七个模块的新旧 `vermagic`、`depends`、`license`、`srcversion` 和签名状态一致。`vermagic` 为 `6.12.80-arm-rpi4-v7l SMP mod_unload modversions ARMv7 p2v8`，七个模块均为 `GPL`、`depends` 为空且无追加模块签名。`kdbus.ko` 的 `srcversion` 为 `82BF5E4477A92EF05AD9A1B`。两份 SDK 的 `Module.symvers` 各有 14,130 个导出名，SHA-256 均为 `fd1bf28f859933424c88f0e65c224bf4992c18e78cd0c5d0e59b1f72e8beb28c`。模块内 `__versions` 的 356 个 CRC 每版全部匹配相应 SDK，其中 `kdbus.ko` 占 154 个，包含 `module_layout`。 [元数据和逐符号 CRC 结果](11F_MODULE_ABI_SUMMARY.json) · [SDK 版本表输入记录](evidence/binary/sdk-symvers-inputs.json)

## 基线与复验

两份 QB 的内核和外部模块 wrapper 源码版本相同，内核配置逐字节相同。外部源码 provider 从 `25797e8af7ed95a5783bbe84c11959560aaf7e92` 变为 `1c26a4781d7813abd9ab2fb4c3fad35c52ec8fc8`，provider 成员比较只发现根 `Makefile` 变更，`include/uapi/linux/kdbus.h` 内容相同。Base QB 快照、构建主机和时间不同。虽然 SDK 都报告 Clang/LLD 22.1.8，构建日志中的实际 Tizen 工具 RPM 发行号不同，包括 LLVM/Clang `22.1.8-1.6 → 22.1.8-4.1`、加速包 `0.4-1.1 → 0.4-2.3`、Binutils `2.43-1.8 → 2.43-1.16`、GNU Make `4.4.1-1.6 → 4.4.1-1.14`。静态文件差值仅描述这两份已发布包，单行修改的独立因果贡献及运行时效果尚未测量。 [人员可读身份输入](11A_QB_IDENTITY.json) · [实际源码成员差异](11B_SOURCE_PROVENANCE.json)

从本目录运行下面的两个命令即可使用工作区原始输入复验。要求 Python 3.11+、`rpm`、`rpm2cpio` 和 GNU `readelf`。扫描先校验仓库元数据、目标 RPM 及新旧 `.ko` 的各自摘要，再解析 ELF 并对照匹配 SDK 的版本表。第二步复核有效 ARM 属性与内核规则，写入 11F 和 11G 机器可读结论。 [扫描脚本](scripts/compare_qb_modules.py) · [ELF 解析器](scripts/elf32_module.py) · [结果复核脚本](scripts/review_qb_binary.py) · [扫描命令记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)

```bash
python3 -B scripts/record_review.py evidence/binary/module-scan \
  python3 -B scripts/compare_qb_modules.py \
  --new-symvers evidence/repository/sdk/boot/kernel/devel/kernel-devel-arm-rpi4/Module.symvers
python3 -B scripts/record_review.py evidence/binary/binary-review \
  python3 -B scripts/review_qb_binary.py
```
