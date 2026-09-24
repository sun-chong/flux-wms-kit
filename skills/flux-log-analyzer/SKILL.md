---
name: flux-log-analyzer
description: FLUX WMS 日志分析工具，解析系统日志文件并生成 HTML 分析报告。仅通过 /flux-log-analyzer 命令调用，不响应自然语言触发。生成报告后自动在浏览器中打开。
user-invocable: true
disable-model-invocation: true
---

# FLUX WMS 日志分析器

**路径约定**: 本文中所有 `scripts/` 和 `templates/` 路径均相对于本 Skill 的根目录（即 SKILL.md 所在目录）。执行时根据当前 Skill 上下文拼接完整路径。

自动解析 FLUX WMS 系统日志文件，提取关键信息（SQL 查询、前后置操作、SP 调用、自定义服务步骤、异常堆栈等），并生成美观的 HTML 分析报告页面。

## 调用方式

此 Skill 仅通过 `/flux-log-analyzer` 命令调用：

```
/flux-log-analyzer log/xxx.log
```

自然语言提及"分析日志"等不会触发，用户必须显式使用命令。

## 功能特性

- **SQL 查询分析**: 提取所有 SQL 查询，统计执行次数、平均耗时、慢查询
- **DML 语句分析**: 提取 INSERT/UPDATE/DELETE 语句，统计影响行数
- **前后置操作流程**: 按时间线展示前置/后置事务操作
- **SP 调用追踪**: 记录存储过程调用、参数、返回值、耗时
- **自定义服务步骤**: 解析 UDF 自定义事务步骤（校验、判断、SELECT、JAVA 等）
- **异常堆栈解析**: 提取异常类型、错误消息、Caused by 链
- **WCO 参数匹配**: 展示配置参数匹配结果
- **HTML 报告生成**: 单文件 HTML 报告，支持明暗主题

## 执行流程

### 步骤 1: 验证日志文件

```bash
ls -la <日志文件路径>
```

### 步骤 2: 解析日志

```bash
py scripts/parser.py <日志文件路径> --output outputs/<文件名>_data.json
```

解析器提取的内容：
- SQL 查询和 DML 语句
- 前后置操作事件
- SP 调用记录
- 自定义服务步骤
- 异常堆栈信息
- WCO 参数配置
- 登录信息和业务数据

### 步骤 3: 生成 HTML 报告

```bash
py scripts/generator.py outputs/<文件名>_data.json --template templates/report.html
```

生成的文件名格式：`<文件名>_analysis_YYYYMMDD.html`（YYYYMMDD 为当天日期）

### 步骤 4: 自动打开报告

generator.py 会输出生成的文件路径，直接打开（Windows 用 `start`，macOS 用 `open`）：

```bash
start <generator输出的文件路径>
```

### 步骤 5: 清理临时文件

```bash
rm outputs/<文件名>_data.json
```

### 步骤 6: 返回结果

告知用户报告已打开，并简要说明日志中的关键发现。

## 输出格式

- **输出目录**: `outputs/html/`
- **文件名格式**: `{原文件名}_analysis_{日期}.html`
- **格式**: 自包含单文件 HTML，零外部依赖

## 报告内容

生成的 HTML 报告包含以下选项卡：

1. **概览**: 统计卡片（SQL 查询数、DML 语句数、SP 调用数、异常数）
2. **前后置信息**: 时间线展示前置/后置事务操作流程
3. **SQL 查询**: 表格展示所有 SQL 查询，支持搜索和按耗时排序
4. **异常分析**: 异常卡片展示堆栈信息
5. **配置参数**: WCO 参数配置
6. **自定义服务**: 步骤卡片展示 UDF 自定义事务执行流程，卡票头含步骤描述、时间范围、耗时、操作数；展开显示前后置调用（时间线卡片样式）、SQL 代码块（支持复制）、判断结果

## 设计规范

报告遵循品牌红配色设计规范：
- 主色调: `#CD0000`（品牌红）
- 暗色主题: 纯黑底 + 高对比文字
- 玻璃态效果: `backdrop-filter: blur()`
- 语法高亮: SQL 关键字、字符串、数字
- 复制功能: 一键复制 SQL 和 JSON 数据

## 示例

### 示例 1: 分析日志文件

**用户输入**:
```
/flux-log-analyzer log/Untitled-1.log
```

**执行过程**:
1. 验证 `log/Untitled-1.log` 存在
2. 解析日志 → `outputs/Untitled-1_data.json`
3. 生成报告 → `outputs/html/Untitled-1_data_analysis_20260702.html`（日期为当天）
4. 自动打开报告
5. 清理临时 JSON 文件
6. 返回摘要："报告已生成，包含 145 个 SQL 查询、7 个 DML 语句、16 个前后置操作、3 个 SP 调用"

### 示例 2: 排查问题

**用户输入**:
```
/flux-log-analyzer log/errors.log
```

**执行过程**:
1. 验证 `log/errors.log` 存在
2. 解析日志 → `outputs/errors_data.json`
3. 生成报告 → `outputs/html/errors_data_analysis_20260702.html`（日期为当天）
4. 自动打开报告
5. 清理临时 JSON 文件
6. 返回："发现 2 个异常，根因是 RowDataException，建议检查..."

## 依赖

- Python 3.6+（标准库，无第三方依赖）
- 日志文件格式: FLUX WMS 标准格式

## 相关文件

- `scripts/parser.py` - 日志解析器
- `scripts/generator.py` - HTML 生成器
- `templates/report.html` - HTML 模板（基于品牌红设计规范）
- `scripts/test_integration.py` - 集成测试
