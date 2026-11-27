# 08.09 · 身份匹配范围修正

| 对象 | 判定 | 实际比较 | 证据 | 
| --- | --- | --- | --- | 
| Repository RPM ↔ Released zImage | EXACT_MATCH | zImage 文件 SHA256 | [查看](../evidence/repository/image-profile-verification.json) | 
| Released Kernel Notes ↔ Runtime Kernel Notes | EXACT_MATCH | 84 字节 GNU/Linux notes | [查看](BUILD_ID_COMPARISON.json) | 
| Released Kernel ↔ Running Kernel Identity | STRONG_MATCH | GNU Build ID、完整 notes、banner、发布快照和架构相符。运行内核的完整内存映像未采集。 | [查看](BUILD_ID_COMPARISON.json) | 
| Repository Modules ↔ Device Modules | EXACT_MATCH | 同 release 的 59 个文件逐路径逐 SHA256 比较 | [查看](08_01_evidence_integrity_review.json) | 
| Released zImage ↔ Device Boot File | UNVERIFIABLE | 设备会话未暴露启动卷 zImage，设备文件 SHA256 无记录。 | [查看](../../../REVIEW_LIMITATIONS.md#公开归档范围与缺口) | 
| Repository RPM ↔ Active RPM Database | UNVERIFIABLE | 设备活动数据库查询无目标条目。NEVRA、install time 和 owner 无法实测。 | [查看](../evidence/runtime/pinned-rpm-device-queries.out) | 

第一轮底层比较保持有效。EXACT_MATCH 细化到实际比较的字节对象，完整运行内核身份关联为 STRONG_MATCH。两个设备侧未验证项保留。本轮未重新访问设备或挂载启动卷。 [结构化身份](08_09_identity_review.json)
