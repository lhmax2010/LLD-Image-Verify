# 08.08 · 证据等级和覆盖率

E4 需要与目标产物绑定的历史直接执行证据。E3 需要匹配的源码规则、实际输入参数、有效配置、逐目标日志和产物绑定，且没有证据支持的合理替代最终链接路径。E2 表示有元数据支持但路径不闭合。E1 表示构建意图。UNKNOWN 表示不足或未解决冲突。原 LLD 分类保持。

| 等级 | 含义 | 仓库 | 设备 | 树内 | 树外 | 
| --- | --- | --- | --- | --- | --- | 
| E4 | DIRECT_EXECUTION_CONFIRMED | 0/59 | 0/59 | 0/52 | 0/7 | 
| E3 | ENGINEERING_VERIFIED | 59/59 | 59/59 | 52/52 | 7/7 | 
| E2 | METADATA_SUPPORTED | 0/59 | 0/59 | 0/52 | 0/7 | 
| E1 | INTENT_ONLY | 0/59 | 0/59 | 0/52 | 0/7 | 
| UNKNOWN | UNKNOWN | 0/59 | 0/59 | 0/52 | 0/7 | 

| 指标 | 仓库模块 | 设备模块 | 树内模块 | 树外模块 | 
| --- | --- | --- | --- | --- | 
| Original Confirmed LLD Coverage | 0/59（0%） | 0/59（0%） | 0/52（0%） | 0/7（0%） | 
| Original LLD Evidence Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 
| E4 Direct Execution Coverage | 0/59（0%） | 0/59（0%） | 0/52（0%） | 0/7（0%） | 
| E3 Engineering Verified Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 
| E3 + E4 Engineering Acceptance Coverage | 59/59（100%） | 59/59（100%） | 52/52（100%） | 7/7（100%） | 

分母为独立 .ko 文件。E3 理由和风险逐目标记录在表中，内核中间对象和 ARM 包装器不会进入模块分母。 [逐模块矩阵](MODULE_LINKER_EVIDENCE_MATRIX.csv) · [Kernel 链接规则矩阵](08_03_linker_rule_matrix.csv)
