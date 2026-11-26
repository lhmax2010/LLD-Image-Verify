# 验证方法

## 1. 确定镜像、源码和 RPM

从目标 QuickBuild 记录确定发布的 Unified 快照，再从该快照的 `build.xml` 读取 `base_id`。把 Base 与 Unified 的源码 manifest 和本轮 `project@SHA` 清单逐项对账。校验镜像归档的发布 SHA256。扫描各分区时，用 MIC `.packages`、`.files` 和 RPM repodata 建立文件归属，再比较镜像文件与发布 RPM 内对应文件的 SHA256。

来源对账应保留架构、镜像、分区、路径、RPM EVR、源码 SHA、文件 SHA256 和实际证据。主机上的 Clang 版本或镜像内是否装有 `ld.lld` 只能提供排查线索。

## 2. 单 ELF 与 debuginfo

先查看运行 ELF 的 `.comment`。如果标记在打包时被剥离，用 GNU Build ID 或 `.gnu_debuglink` CRC32 与同架构 debuginfo 配对，再查看调试 ELF 的 `.comment`。LLD ELF writer 会写入形如 `Linker: LLD 22.1.8` 的标记。仅出现 GCC、Clang 编译器字符串或 GNU Build ID 时继续查原始目标日志。 [LLD 22.1.8 的标记实现](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/lld/ELF/SyntheticSections.cpp#L65)

### 公开 RPM 示例

在有 Bash、Python 3、curl、binutils、RPM 和 cpio 的 Linux 上执行。示例使用后续轮 armv7l 的 `deviced` 和对应 debuginfo，检查运行 ELF SHA256、调试配对 CRC 和实际标记。实际镜像验证还要用 `cmp` 将解包后的同路径 ELF 与示例中的 `deviced` 对账。

~~~bash
(
  set -eu
  set -o pipefail
  work=$(mktemp -d)
  cd "$work"
  base=https://download.tizen.org/RBS/TIZEN/Tizen/Tizen-Unified-Toolchain/tizen-unified-toolchain_20261120.082536/repos/standard
  curl -fsSL "$base/packages/armv7l/deviced-10.1.0-1.armv7l.rpm" -o runtime.rpm
  curl -fsSL "$base/debug/deviced-debuginfo-10.1.0-1.armv7l.rpm" -o debuginfo.rpm
  rpm2cpio runtime.rpm | cpio -i --quiet --to-stdout ./usr/bin/deviced > deviced
  rpm2cpio debuginfo.rpm | cpio -i --quiet --to-stdout ./usr/lib/debug/usr/bin/deviced.debug > deviced.debug
  printf '%s  %s\n' a21d8d6d24e7a3148f14d0ac9cd1bd9ac49ba595d62a3f5bb1eb77f4e1e670e5 deviced | sha256sum -c -
  python3 - <<'PY'
from pathlib import Path
import re
import subprocess
import zlib

sections = subprocess.check_output(["readelf", "-SW", "deviced"], text=True)
match = re.search(r"\.gnu_debuglink\s+PROGBITS\s+\w+\s+(\w+)\s+(\w+)", sections)
if not match:
    raise SystemExit("Missing .gnu_debuglink")
offset, size = (int(value, 16) for value in match.groups())
section = Path("deviced").read_bytes()[offset:offset + size]
if len(section) != size or size < 8 or section.split(b"\0", 1)[0] != b"deviced.debug":
    raise SystemExit("Unexpected .gnu_debuglink")
expected = int.from_bytes(section[-4:], "little")
actual = zlib.crc32(Path("deviced.debug").read_bytes())
if actual != expected:
    raise SystemExit(f"Debug CRC mismatch: expected {expected:08x}, got {actual:08x}")
print(f"Matched debug CRC32: {actual:08x}")
PY
  readelf -p .comment deviced.debug | grep -F 'Linker: LLD 22.1.8'
)
~~~

历史预期为 `deviced: OK`、CRC32 `5716cbd5` 和 `Linker: LLD 22.1.8`。

## 3. 目标日志和 BFD/LLD 对照重放

- **目标链接日志。** 将真实 linker 路径或版本、最终链接目标、安装路径、发布 RPM 和镜像 SHA256 串起来。若用 Meson 的 host linker 配置作证，应和目标语言、实际链接行、安装路径一起确认。对于内核模块，使用该架构的 Kbuild 配置、目标的 `LD [M]`、安装路径和 RPM 文件哈希。只有 configure 探测行时证据仍不足。 [Kbuild 的 LLVM 参数](https://docs.kernel.org/kbuild/llvm.html#the-llvm-argument)
- **对照重放。** 固定源 RPM、架构、工具链、链接输入和参数。对同一批目标文件分别用 `-fuse-ld=bfd` 与 `-fuse-ld=lld` 链接，并用 `-Wl,-v` 记录实际 linker。按历史调试拆包方式处理输出后比较完整 SHA256。如果差异只在 `.gnu_debuglink` CRC，可单独将这四字节清零比较，同时保留完整哈希与差异原因。
- **结构线索。** `readelf -V` 的版本定义父节点在这里可以排除 LLD 22.1.8。`readelf -lW` 的 `PT_LOAD` 与 `GNU_RELRO` 布局可用于筛选目标。两项都需要结合特定版本与架构的对照实验。 [LLD 22.1.8 的版本节点实现](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/lld/ELF/SyntheticSections.cpp#L1226)
- **预编译文件。** 对比镜像、运行时 RPM、SRPM 或 TPK 内成员的 SHA256。匹配预编译成员能说明它从哪里打入镜像。确认其原始链接器还需要生产方的目标日志或已配对调试文件。Dart AOT ELF 可用其生成算法重算 Build ID，并核对 TPK 成员。 [Dart ELF writer](https://github.com/dart-lang/sdk/blob/3.12.0/runtime/vm/elf.cc)

## 4. ABI 和运行检查

用同架构、同源码提交和同 RPM EVR 的 GCC 与 LLVM 产物，对比动态导出、SONAME、`DT_NEEDED`、版本定义和开发包契约。用镜像的动态加载器在 QEMU 下核对启动依赖，必要时运行 `dlsym` 或 `dlvsym`。真实设备的开机、业务运行、安装卸载、升级和性能另需记录。
