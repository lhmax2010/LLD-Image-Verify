# Phase 13 · 复验方法

在当前 `phase13_final_acceptance/` 下先复核本次归档的哈希、统计及决策。

    sha256sum -c --quiet SHA256SUMS
    python3 -B scripts/finalize_phase13.py verify

脚本默认读取旁边工作区保留的 Phase 11 和 Phase 12。复算在独立的 Phase 13 副本中进行，以下命令会重写副本的派生文件与回执。

    python3 -B scripts/capture.py evidence/review/phase12-bundle bash -c 'cd ../phase12_controlled_benchmark && python3 -B scripts/finalize_phase12.py verify && sha256sum -c PHASE12_EVIDENCE_BUNDLE.tar.gz.sha256'
    python3 -B scripts/review_phase12.py
    python3 -B scripts/size_attribution.py
    python3 -B scripts/parse_identity.py
    python3 -B scripts/finalize_phase13.py seal

线程测量使用原生 Linux x86-64、已归档的 Phase 12 计时器和链接器，以及 bubblewrap、strace。以下命令只重放冻结的中间链接，CPU 可以按同类可用核调整。不同宿主或时间的统计值预计会变化，复用已归档结果可精确重算该次测量。

    python3 -B scripts/capture.py evidence/threads/sweep bash scripts/run_thread_sweep.sh --blocks 48 --cpus 0,1,2,3,4,5,6,7

本轮只读设备脚本仅访问已授权 serial `private-address-02:26101`。在设备仍获授权且需要采集新身份时，先在独立副本运行 `bash scripts/read_device_identity.sh` 并保留回执。离线解析脚本读取现有记录。验收范围由实际目标身份决定。 [现有记录](../../REVIEW_LIMITATIONS.md#公开归档范围与缺口)
