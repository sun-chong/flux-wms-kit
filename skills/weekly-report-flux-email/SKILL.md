---
name: weekly-report-flux-email
description: >
  将项目周报 PPTX 文件导出为 PDF 并自动生成邮件 HTML 正文。
  当用户提到"周报"、"项目周报"、"周报PPT"、"生成周报邮件"、"周报转PDF"、
  "周报邮件内容"、".pptx 周报"，或需要从 PPT 中提取"本周计划完成情况"和
  "下周工作计划"表格并转为邮件格式时，务必使用此 Skill。
  即使用户只是提到要处理或发送周报 PPT 文件，也应触发。
disable-model-invocation: true
---

# 项目周报生成器（Weekly Report Generator）

将项目周报 PPTX 文件自动转换为：
1. **PDF 文件**（通过 PowerPoint COM 自动化导出）
2. **邮件 HTML 正文**（提取"本周计划完成情况"和"下周工作计划"表格，格式与标准周报邮件一致）

## 核心特性

- **动态页码识别**：根据幻灯片标题关键词（`本周计划完成情况`、`下周工作计划`）自动定位目标页面，不依赖固定页码。即使 PPT 模板调整了页面顺序，也能正确提取。
- **全路径动态化**：输入 PPTX 路径、输出目录均由用户指定。
- **日期格式自动转换**：PPT 中的 `M/D` 格式自动转为中文 `M月D日`。

## 工作流程

### Step 1: 确认输入

向用户确认 PPTX 文件路径。如果用户未指定输出目录，默认输出到 PPTX 文件所在目录的上级目录下的 `outputs/` 文件夹（即 `../outputs` 相对于 PPTX 文件）。

### Step 2: 执行脚本

使用捆绑的 `scripts/generate_weekly_report.py` 脚本处理：

```bash
python <skill_dir>/scripts/generate_weekly_report.py "<pptx_path>" -o "<output_dir>"
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `<pptx_path>` | 必填，PPTX 文件完整路径 |
| `-o <output_dir>` | 可选，输出目录（默认 `../outputs`） |
| `--skip-pdf` | 跳过 PDF 导出，仅生成 HTML |
| `--pdf-only` | 仅导出 PDF，不生成 HTML |

### Step 3: 确认输出

脚本执行完毕后，向用户报告生成的文件路径：
- `<output_dir>/<文件名>.pdf`
- `<output_dir>/<文件名>-邮件内容.html`

## 依赖要求

脚本运行时自动检查依赖，如缺少则通过 pip 安装：

- **python-pptx**: PPTX 文件读取与表格提取（必需）
- **pywin32**: PowerPoint COM 自动化 — 仅 PDF 导出时需要（`--skip-pdf` 模式下可不装）

## 动态页码识别逻辑

脚本不会硬编码页码，而是遍历 PPTX 的所有幻灯片，根据形状中的文本内容匹配：

```
本周计划完成情况  ← 匹配关键词: "本周计划完成情况" / "本周工作计划" / "本周计划"
下周工作计划      ← 匹配关键词: "下周工作计划" / "下周计划"
```

这意味着即使 PPT 模板调整、页面增删，只要标题文字不变，提取就能正常工作。

## 邮件 HTML 格式

生成的 HTML 与标准周报邮件完全一致：

- **字体**：微软雅黑
- **表头颜色**：`#B40000`（深红色）
- **表格宽度**：545pt
- **表头行**：字号 11pt，加粗，下边框 1.5pt 实线
- **数据行**：字号 10pt，常规，下边框 1.0pt 实线
- **"本周计划完成情况"表**：5 列 — 序号 / 阶段 / 任务描述 / 时间 / 状态
- **"下周工作计划"表**：4 列 — 序号 / 阶段 / 任务描述 / 时间
- 包含标准签名块（FLUX 公司信息）

## 注意事项

1. **PDF 转换需要本机安装 Microsoft PowerPoint**。如果 PowerPoint 不可用，使用 `--skip-pdf` 仅生成 HTML。
2. 输出的文件编码为 UTF-8，可直接粘贴到邮件客户端（如 Outlook、QQ邮箱）。
3. 表格提取要求 PPT 中的表格包含"序号"和"阶段"列头，否则会跳过。

## 异常处理指引

当脚本执行遇到问题时，按以下策略处理：

| 场景 | 脚本表现 | 模型应如何告知用户 |
|------|---------|------------------|
| PPTX 文件不存在 | 脚本抛出 `FileNotFoundError` | 提示用户检查文件路径是否正确，文件是否在 `inputs/` 目录中 |
| PPTX 文件损坏 | 脚本抛出 `PackageNotFoundError` 或 `InvalidFileException` | 建议用户用 PowerPoint 重新打开并另存为新 PPTX 文件 |
| PowerPoint 未安装 | `pptx_to_pdf()` 抛出 `ModuleNotFoundError` 或 COM 错误 | 建议用户使用 `--skip-pdf` 跳过 PDF，仅生成邮件 HTML |
| PDF 保存失败 | `pptx_to_pdf()` 抛出 COM 异常（如磁盘满、目录只读） | 提示用户检查输出目录的写入权限，或使用 `--skip-pdf` 跳过 PDF 导出 |
| 未找到"本周/下周"页面 | 脚本打印 `[警告]`，生成空表格的 HTML | 告知用户 PPT 中未匹配到目标页面，检查幻灯片标题是否包含"本周计划完成情况"/"下周工作计划"关键词 |
| 表格数据为空 | HTML 显示"（暂无数据）" | 提醒用户确认 PPT 表格中是否有数据行（序号列需为数字） |
| python-pptx 未安装 | `import` 失败 | 脚本会自动尝试 pip 安装；若安装失败，提示用户手动执行 `pip install python-pptx` |
