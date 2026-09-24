# AI输出物管理

## 输出物目录

- 所有AI生成的输出物（分析文档、优化方案、SQL脚本、备份文件等）统一存放在 `outputs/` 目录
- 文件命名规范：`[功能]_[日期]_[类型].[扩展名]`
  - 例如：`SPIDX_ASRS_PUTAWAY_20260227_ANALYSIS.md`
  - 例如：`SPUDF_TSK_CANCEL_PA_TSK_20260227_OPTIMIZED.sql`

## 输出物类型

- `.md`：分析报告、优化方案、设计文档
- `.sql`：优化后的存储过程、索引创建脚本
- `_BAK[日期].sql`：原文件备份
