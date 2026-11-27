# Phase 15 · kdbus 最小功能回归方案

**方案待批准，功能用例未执行。** 目标为 Raspberry Pi 4 / ARMv7l / Non-RT，QB `20261125.130358`。优先采用发布测试包中的五个单项用例，以普通实验账号依次运行。每项测试通过已挂载 kdbusfs 的 `control` 建立独立的临时测试 bus，再通过该 bus 执行原生 ioctl。用例使用合成消息和名称。建议使用专用或独占的实验设备，因为代码以 `KDBUS_MAKE_ACCESS_WORLD` 创建测试端点，同一挂载视图内其他进程可能看到并尝试连接。已有 system/user bus 须保持完好。

## 运行前确认

1. 从已批准的 SDB Serial 复核硬件、目标 `BUILD_ID`、内核 Build ID、`/proc/version`、已安装与运行中 kdbus 身份。按[可行性报告](KDBUS_FUNCTIONAL_TEST_FEASIBILITY.md)中的摘要核对制品，只向 Owner 批准的可执行临时目录传输一个测试 ELF。
2. 核对测试账号、`CapEff` 和相关安全策略。使用现有 kdbusfs，确认 `/sys/fs/kdbus/control` 可见，不要求特权。若节点打开、创建 bus 或执行权限被拒，记录原始错误并停在 `BLOCKED_ENVIRONMENT`。
3. 在任何用例前准备设备端进程组监管。每次在独立进程组中执行，记录该组及测试节点，外部硬截止建议 20 秒，超时先 TERM，最多再等 2 秒后仅对该组 KILL，并确认该组和其 bus 已消失。已查到 `setsid`，尚未建立经 Owner 验收的设备端监管入口。目标设备缺少可用的 `timeout`，主机中断 SDB 不能作为设备端清理证据。`sync-reply` 有无限等待的同步请求和可 fork 的子用例，单项 runner 自带的 10 秒定时器无法保证回收全部后代。
4. 记录 UTC 测试窗口、`/proc/sys/kernel/random/boot_id`、`/proc/uptime` 及前置 `dmesg`。为每个用例记录命令、stdout/stderr、设备端退出值、耗时、测试 bus 名称和清理结果。原始日志按内部证据权限保存。

## 用例及验收

| 顺序及用例 | 最小验证点 | 身份、影响与清理 |
| --- | --- | --- |
| 1 `hello` | 对测试 bus 成功 `KDBUS_CMD_HELLO` 并收到返回项，`FREE` 释放其偏移。保留源测试对错误大小、标志等的预期拒绝 | 非 root 测试账号；创建端点连接后关闭 FD |
| 2 `message-basic` | 两个已连接端点的 `SEND/RECV` 路径有效，发送方和接收方均得到同一广播 cookie。测试校验请求字段错误的预期返回及 Tizen 特有行为 | 非 root 同账号；只在临时 bus 产生广播，释放接收池并断开连接 |
| 3 `sync-reply` | 同步请求通过 kdbus 得到匹配 cookie 的应答；保留用例中的超时、关闭连接、eventfd 取消以及正常完成断言 | 非 root 同账号；会创建测试线程和子进程，向自己启动的子进程发送测试信号。外部监管须清理整组 |
| 4 `name-basics` | 在临时 bus 取得测试名，检查所有者，释放后检查不再拥有；源测试验证无效名称和非所有者释放的返回值 | 非 root 同账号；测试名 `foo.bar.xxx` 等仅在临时 bus 有效，随测试连接释放 |
| 5 `byebye` | 有排队消息时断开返回预期 `-EBUSY`；接收并释放后 `BYEBYE` 成功，重复断开返回 `-ECONNRESET` | 非 root 同账号；确认映射、连接 FD 和 control FD 关闭，测试 bus 节点消失 |
| 每项后及全部结束后 | 确认测试进程组、临时 bus 和测试名称无残留；审查测试窗口新增的内核日志 | 使用已批准非 root 身份读取；只清除本次专有临时目录中的指定文件 |

每个用例须有该用例的 `CASE;PASS` 输出、设备端成功退出、监管未超时及清理成功。该版本有可能在 runner 报 `FAIL;TIMEOUT` 时从 `main` 返回 `0`。以用例输出和监管状态共同判定，退出值仅作辅助。`FAIL`、未知、跳过、超时、缺少结果行、清理未确认或日志窗口无法重建，都需保留原始输出并中止剩余用例；预期负向断言按源测试记录。完整套件、循环、benchmark 和 namespace 模式均不在五项方案范围内。

## 拟执行命令

以下涉及设备写入及测试 IPC 的命令须在审批完成后执行。`SERIAL` 在内部记录绑定，`APPROVED_EXEC_ROOT` 由实验室确认可写且可执行。`STAGE` 必须来自本次 `mktemp`，只接受批准目录下的单一路径及安全字符。检查每条 SDB 命令的返回与输出，再进入下一步。原始证据目录由主机侧预先创建。

```bash
# 主机提取已校验的制品，运行位置为本次证据工作目录
RPM=linux-tizen-modules-tests-11.0.0-0.armv7l.rpm
printf '%s  %s\n' 1c607b3d98d1cdfd811612d8ea634ec9deed32259c01570a1011b0973db28882 "$RPM" | sha256sum -c -
set -o pipefail
rpm2cpio "$RPM" | cpio -i --quiet --to-stdout \
  './usr/libexec/linux-tizen-modules-source/tests/kdbus-test' > kdbus-test
printf '%s  %s\n' c9df48f29c59562b3bc6b755c5ed89d90ab879334e0c032eeb6ed5fd6ea751fe kdbus-test | sha256sum -c -

# 设备操作，仅在批准本次 staging 后执行
STAGE=$(sdb -s "$SERIAL" shell "umask 077; mktemp -d '$APPROVED_EXEC_ROOT/kdbus-phase15.XXXXXX'" | tr -d '\r')
# 校验 STAGE 属于已批准目录，并确认仅返回一个绝对路径
sdb -s "$SERIAL" push ./kdbus-test "$STAGE/kdbus-test"
sdb -s "$SERIAL" shell "chmod 0700 '$STAGE/kdbus-test' && sha256sum '$STAGE/kdbus-test'"
# 核对设备摘要与上面的 ELF 摘要相同后继续
sdb -s "$SERIAL" shell 'cat /proc/sys/kernel/random/boot_id /proc/uptime; dmesg' > before.log
```

设备端监管器的启动入口和超时处置须由实验室写入审批单。将下列五行分别交给该入口执行，每项均用已批准的单独进程组；`TEST_BIN` 是已验过摘要的 `$STAGE/kdbus-test`。未取得监管入口、范围及清理验证方法时，本命令组保持待执行。

```sh
"$TEST_BIN" -R /sys/fs/kdbus -f -t hello
"$TEST_BIN" -R /sys/fs/kdbus -f -t message-basic
"$TEST_BIN" -R /sys/fs/kdbus -f -t sync-reply
"$TEST_BIN" -R /sys/fs/kdbus -f -t name-basics
"$TEST_BIN" -R /sys/fs/kdbus -f -t byebye
```

用例默认自建唯一命名的 `<uid>-test-bus-…`，日志记录创建的名称。按精确节点检查 `/sys/fs/kdbus`，按实验室监管回执确认进程组退出，并核对已有系统和用户 bus 快照。所有用例结束或中止后，留存 `after.log` 再清理临时文件。关闭 bus owner 持有的 control FD 及其继承副本后，内核撤销该测试节点。若仍有节点，保持现场，提交设备 Owner 处理。

```bash
sdb -s "$SERIAL" shell 'cat /proc/sys/kernel/random/boot_id /proc/uptime; dmesg' > after.log
sdb -s "$SERIAL" shell "rm -- '$STAGE/kdbus-test' && rmdir -- '$STAGE'"
```

对比相同 boot ID 下的前后日志，按内核单调时间界定测试区间，检查新增 kdbus 相关错误、Oops/WARN、锁死、符号或模块异常及策略拒绝。记录任何日志缺口与原因。Phase 14 旧 QB 只有可比的启动和模块层证据。若需要新旧功能对照，须另有已获批的旧 QB 独立设备、相同用例及相应 ABI 匹配工具；缺少可比结果时保留这一证据缺口。 [Phase 14 基线](../phase14_product_runtime_acceptance/PHASE14_RUNTIME_REGRESSION_REPORT.md)

## 产品 D-Bus 或 IPC 用例

如果产品验收要求指定服务，先由产品 QA 提供既有用例 ID、可重复命令、调用身份和预期结果。执行前确认选用已获批的 transport 取证手段。对同一次测试请求，将客户端或服务进程的 kdbusfs FD、成功的 `KDBUS_CMD_HELLO`、关联的 `KDBUS_CMD_SEND/RECV`、请求和应答标记绑定起来，并检查该次交换有没有切换到 `AF_UNIX`。如采用 syscall 跟踪，限制在获批测试进程，记录必要的端点、FD、ioctl 编号和结果，避免采集消息载荷。当前设备无 `strace`，此证据路径的工具和权限需要单独确认。仅观察选定应用通过 Unix socket 往返时，按 Unix socket 覆盖处理。 [可行性调查](KDBUS_FUNCTIONAL_TEST_FEASIBILITY.md)
