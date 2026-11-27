# GNU Make 最小作用域实验

**通过 21 个场景、147 条变量观测和 42 条 mock argv 断言。** 直接复制封存的外部 Makefile 及 kdbus 子 Makefile 到临时目录，用简化 Kbuild 复现父进程、对象子进程、子目录递归、modpost 和 modfinal 的边界。外部入口执行复制件中的递归配方。mock 只打印参数，不运行编译器、链接器或生成 .o/.ko。 [原始 GNU Make 版本](evidence/reproducer/make-version.out) · [运行回执](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) · [全部原始命令与退出状态](evidence/reproducer/cases.json)

| 场景 | Makefile.build include 后 | 中间 kdbus.o | 最终 kdbus.ko |
| --- | --- | --- | --- |
| historical_shape_control | ld | ld | ld.lld |
| armv7l_cross_prefix | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | ld.lld |
| aarch64_cross_prefix | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld | ld.lld |
| ld_lld_command_line | ld.lld | ld.lld | ld.lld |
| ld_lld_environment | ld | ld | ld.lld |
| ld_bfd_environment | ld | ld | ld.lld |
| ld_bfd_environment_e | ld.bfd | ld.bfd | ld.bfd |
| clang_bfd_command_line | armv7l-tizen-linux-gnueabi-ld.bfd | armv7l-tizen-linux-gnueabi-ld.bfd | armv7l-tizen-linux-gnueabi-ld.bfd |
| llvm_zero | ld | ld | ld.lld |
| llvm_suffix | ld | ld | ld.lld-22 |
| gcc_armv7l_original | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld |
| gcc_aarch64_original | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld |
| remove_ld_armv7l | ld.lld | ld.lld | ld.lld |
| remove_ld_aarch64 | ld.lld | ld.lld | ld.lld |
| remove_ld_gcc_armv7l | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld |
| remove_ld_gcc_aarch64 | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld | aarch64-tizen-linux-gnu-ld |
| remove_ld_clang_bfd | armv7l-tizen-linux-gnueabi-ld.bfd | armv7l-tizen-linux-gnueabi-ld.bfd | armv7l-tizen-linux-gnueabi-ld.bfd |
| simple_replacement | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | ld.lld |
| conditional_replacement | ld.lld | ld.lld | ld.lld |
| explicit_export_replacement | armv7l-tizen-linux-gnueabi-ld | armv7l-tizen-linux-gnueabi-ld | ld.lld |
| override_with_cli | armv7l-tizen-linux-gnueabi-ld | ld.lld | ld.lld |

每条 CSV 保留 $(origin LD)、$(flavor LD)、$(value LD)、$(LD)、LLVM origin/value、CROSS_COMPILE、MAKEFLAGS、MAKEOVERRIDES、MAKELEVEL，以及适用时的模拟 argv。override_with_cli 在对象父进程观测到 origin override，但其子进程仍通过 MAKEFLAGS 接收命令行 ld.lld，说明应分别查看各作用域。LLVM=0 在当前条件中仍是非空字符串。 [完整 CSV](KDBUS_REPRODUCTION_RESULTS.csv) · [override 原始输出](evidence/reproducer/override_with_cli.out)

删除 LD 赋值后，两个架构的 LLVM 模型统一继承 ld.lld，GCC 模型保留各自前缀的 ld，显式 Clang+BFD 命令行仍生效。这是变量选择的回归矩阵，尚无真实编译、链接或 ABI 回归结论。历史作业使用 Make 4.4.1，本次运行使用 GNU Make 4.3。 [历史 Make 行](../evidence/build/linux-tizen-modules-armv7l.out#L417) · [候选方案兼容性](KDBUS_LD_FIX_PROPOSAL.md)

在本目录复跑：

    python3 -B reproducer/run.py --output /path/to/new-experiment

脚本清洗影响 Make 变量的继承环境，通过场景定义显式传入设置。历史中间链接仍为 BFD_PATH_POSSIBLE。 [脚本](reproducer/run.py) · [历史证据](KDBUS_HISTORICAL_INTERMEDIATE_LINK.md)
