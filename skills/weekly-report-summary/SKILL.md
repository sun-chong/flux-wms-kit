---
name: weekly-report-summary
description: |
  根据 Git 提交历史生成一句话周报工作总结。支持单周和多周范围，多周时合并为一条周报。
  适用于：用户提到"生成周报"、"本周工作总结"、"周报一句话"、"代码提交统计"、"上周周报"等场景。
  手动触发，执行完成后同时输出完整版和压缩版（70字以内），供用户选择。
  Make sure to use this skill whenever the user mentions weekly report,
  work summary, git commit statistics, or weekly standup notes.
triggers:
  - "生成周报"
  - "本周工作总结"
  - "周报一句话"
  - "代码提交统计"
  - "git周报"
disabled-model-invocation: true
---

# Weekly Report Skill

根据 Git 提交历史生成一句话周报工作总结。

## 工作流程

### Step 1: 获取 Git 提交记录

根据用户请求的时间范围获取提交记录。

**默认范围**：本周（周一至周日）

```bash
# Windows PowerShell 计算本周日期范围
$weekStart = (Get-Date).AddDays(-((Get-Date).DayOfWeek.Value__ - 1)).ToString('yyyy-MM-dd')
$weekEnd = (Get-Date).AddDays(7 - (Get-Date).DayOfWeek.Value__).ToString('yyyy-MM-dd')
git log --since="$weekStart" --until="$weekEnd" --all --pretty=format:"%h|%s|%an|%ad" --date=short
```

**多周范围**：当用户指定多周（如"上周和本周"、"最近两周"），分别获取每周的提交记录，最后合并生成**一条**周报。

```bash
# 示例：获取上周和本周的提交
# 上周
git log --since="2026-04-27" --until="2026-05-04" --all --pretty=format:"%h|%s|%an|%ad" --date=short
# 本周
git log --since="2026-05-04" --until="2026-05-10" --all --pretty=format:"%h|%s|%an|%ad" --date=short
```

注意：
- 周一为一周开始，周日为结束
- 使用 PowerShell 计算日期时，`DayOfWeek.Value__` 中周一=1，周日=0
- 如果当天是周日，`--since` 是本周一，`--until` 是下周一
- 多周场景下，将所有周的功能点汇总后合并为一条周报，不分别输出

### Step 2: 过滤非开发类提交

过滤掉以下类型的提交（不计入周报）：
- "同步其他成员修改"
- "CLAUDE.md" 相关提交
- "Merge" 合并提交
- "docs:" 文档类提交（除非与开发功能直接相关）

### Step 3: 分析提交内容

对于每个有效提交：
1. 从 commit message 提取关键信息
2. 列出修改的 SQL 文件（`git show --name-only --pretty=format: <hash> | grep -E "\.(sql|pkg)$"`）
3. 读取存储过程开头的文档注释获取功能描述（每次都要读取）

### Step 4: 合并同类项

将相关提交合并为一个功能点描述：
- 同一存储过程的多次提交（如 SPIDX_ASRS_PUTAWAY 的多次优化）
- 同一功能模块的多个相关改动（如 SN复核区域拣货改造 + 兜底校验）
- 使用括号展示主要改动细节

**合并判断规则（重要）**：
- **信息非常明确、无歧义**：直接合并，Agent自行判断
  - 例如：同一存储过程的多个commit message都是关于同一个功能的优化
  - 例如：多个提交都涉及同一个表/存储过程，且目的清晰
- **存在歧义或不够明确**：通过 AskUserQuestion 向用户确认后再合并
  - 例如：两个提交的存储过程名称不同，无法确定是否是同一功能
  - 例如：commit message 模糊，无法判断是否相关

### Step 5: 生成完整周报

将所有时间范围内的功能点汇总，输出为**一条**周报。

输出格式：
> 系统开发，完成[功能点1]（[子功能细节]）、[功能点2]、[功能点3]。

示例：
> 系统开发，完成立库入库计算目标库位优化（计算空库位、兄弟库位优先分配同批同SKU）、SN复核拣货区域校验优化（区域拣货改造、兜底校验）、宗义AGV原材料绑定功能调优、条码解析SKU前后空格过滤。

### Step 6: 输出压缩版

生成周报后，**始终同时输出压缩版**，供用户选择使用：

1. 统计完整版字数
2. 尝试压缩至70字以内，压缩策略：
   - 移除括号内的细节描述
   - 使用更简洁的词汇（如"调优"代替"功能和接口调优"）
   - 合并相似功能点
3. **无论压缩是否损失信息，都要输出压缩版**，格式如下：

```
完整版（XX字）：
> [完整周报内容]

压缩版（XX字）：
> [压缩后周报内容]
```

4. 如果压缩版损失了关键信息，在压缩版后加注说明，如："注：压缩版省略了XXX细节"