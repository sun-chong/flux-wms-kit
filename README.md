# FLUX WMS Kit

一套面向 **FLUX WMS（富勒仓库管理系统）Oracle 数据库二次开发**的 Agent Skills 工具集，支持 Claude Code、Codex、Pi、OpenCode 等主流 Agent 工具。针对 FLUX WMS 二次开发中最重复的环节——存储过程开发、语法检查、部署编译、测试验证、业务配置注册、报表配置——沉淀为一组可复用的 Agent Skills，让 AI 全程参与开发闭环。

> **适用对象**：基于 FLUX WMS 做定制化开发的实施顾问、数据库开发工程师。

---

## 核心特性

- **完整开发闭环**：模板生成 → 语法预检 → 部署编译 → 测试数据生成 → 自动化测试 → 代码审查，全链路 Skill 覆盖
- **业务配置自动化**：扩展配置（前后置操作/定时器/RF 端）、报表配置、RF 端 SQL 转换，直接落库
- **安全约束内建**：DML 操作强制人工确认、部署前强制语法检查、测试环节只读数据库
- **项目规范驱动**：通过 `rules/` 下的规则文件约束 AI 的编码风格与输出物管理，保证多会话产出一致

---

## 项目结构

```
flux-wms-kit/
├── agents/                  # 自定义 Agent（代码审查等）
├── skills/                  # Agent Skills 集合（本项目核心）
├── rules/                   # 项目规则（PL/SQL 规范、输出物管理、参考资料）
├── queries/                 # 常用查询脚本
├── src/                     # 数据库开发脚本目录
│   └── routine/             #   存储过程（.sql）
│   ├── table/               #   表定义
│   ├── index/ package/ view/ sequence/
└── .env.example             # 环境配置模板（复制为 .env 使用，不提交真实凭据）
```

---

## Skills 一览

### 🔧 数据库开发核心

| Skill | 核心作用 |
| --- | --- |
| `connect-oracle` | **数据库统一入口**。通过 Bash + SQLcl 连接 Oracle 执行查询、DML、编译语句，禁止直接使用 PowerShell 操作数据库 |
| `ddl-template` | **DDL 模板生成器**。按项目命名规范（`SPUDF` / `FNUDF` / `UDF_*`）与 Oracle 11g 兼容约束，生成存储过程、函数、建表的标准模板，新建对象时强制使用 |
| `sp-parser` | **语法预检查**。将存储过程转为匿名块，使用 `DBMS_SQL.PARSE` 做数据库级语法/部分语义检查，部署前拦截低级错误 |
| `sp-deploy` | **存储过程部署**。读取 `.sql` 文件执行 `CREATE OR REPLACE` 编译部署，自动进行错误检查 |
| `oracle-reviewer`（Agent） | **代码审查**。部署前对 PL/SQL 做代码质量、异常处理、Oracle 11g 兼容性、SQL 优化的多维度审查 |

### 🧪 测试验证

| Skill | 核心作用 |
| --- | --- |
| `sp-test-data-gen` | **测试数据生成**。从存储过程源码递归追踪依赖链，基于数据库真实数据生成覆盖成功/错误路径的完整测试方案（全程只读，严禁修改数据库） |
| `sp-test-run` | **自动化测试执行**。采集基线数据 → 按参数串行执行测试 → 对比分析 → 输出测试报告，形成数据驱动的测试闭环 |

### 📦 FLUX 业务配置

| Skill | 核心作用 |
| --- | --- |
| `flux-extconfig-gen` | **扩展配置生成**。解析存储过程参数声明，生成 `BSM_STDBIZ_EXTCONFIG` 的 INSERT SQL，完成前后置操作、定时器、RF 端前置操作的注册 |
| `flux-report-builder` | **报表构建器**。将简化 SQL 转换为 FLUX WMS 合规报表，覆盖数据源写入、JSON 列配置、表单配置、验证清理的完整 9 步落库流程 |
| `flux-rfsql-converter` | **RF 端 SQL 转换**。将标准 Oracle SQL 逐条规则转换为 FLUX RF 端低代码平台兼容格式（控件绑定、系统常量、参数引用） |
| `flux-newfunc-query` | **新增功能查询**。按日期查询 `BSM_FUNCTION` / `BSM_FUNCTION_ACTION` 中新增的菜单功能与按钮权限，输出树形结构清单 |
| `flux-log-analyzer` | **日志分析**。解析 FLUX WMS 系统日志（SQL、前后置操作、SP 调用、异常堆栈），生成 HTML 可视化分析报告 |

### 🛠 效率工具

| Skill | 核心作用 |
| --- | --- |
| `database-dictionary` | **数据库字典生成**。基于 `BSM_DATA_DICTIONARY_FIELD` 字典表或 `COMMENT ON` 注释，为每张表生成独立的 Markdown 字典文件 |
| `review-document` | **多视角文档评审**。并行启动多个 subagent 从不同角度评审文档，按严重程度汇总结构化报告 |
| `weekly-report-summary` | **周报总结**。根据 Git 提交历史生成一句话工作总结，支持多周合并 |
| `weekly-report-flux-email` | **周报邮件**。将周报 PPTX 导出 PDF 并提取"本周/下周计划"表格，生成标准格式的邮件 HTML 正文 |

---

## 快速开始

### 前置要求

- 任一支持的 Agent 工具：Claude Code、Codex、Pi、OpenCode 等
- Oracle SQLcl（`connect-oracle` 依赖）
- Python 3.10+（`oracledb` 等依赖，见各 Skill 说明）
- 可访问的 FLUX WMS Oracle 数据库（推荐测试环境）

### 安装

```bash
git clone https://github.com/your-org/flux-wms-kit.git
cd flux-wms-kit
```

### 配置数据库连接

项目不包含任何真实凭据，通过 `.env.example` 模板创建本地配置文件：

```bash
cp .env.example .env
```

然后编辑 `.env`，填入以下配置项：

| 配置项 | 说明 | 示例 |
| --- | --- | --- |
| `DB_CONNECTION` | Oracle 连接串（EZCONNECT 格式） | `username/password@host:port/service_name` |
| `CLAUDE_CODE_AUTHOR` | 操作人署名，写入 ADDWHO / EDITWHO 审计字段 | `your-name` |

> `.env` 已被 `.gitignore` 排除，真实凭据不会进入版本库。

### 使用示例

在 Agent 工具会话中直接用自然语言触发，或使用 `/skill-name` 手动调用：

```
# 新建一个波次分配存储过程（自动走 ddl-template 模板）
> 帮我新建一个拣货波次分配的存储过程

# 语法检查 + 部署（部署前会请求确认）
> 检查 routine/UDF_ALLOC_WAVE.sql 的语法，没问题就部署

# 生成测试方案并执行测试
> /sp-test-data-gen routine/UDF_ALLOC_WAVE.sql
> /sp-test-run outputs/UDF_ALLOC_WAVE_TEST_PLAN.md

# 注册为出库后置操作
> /flux-extconfig-gen 将 UDF_ALLOC_WAVE 注册为出库单后置操作
```

---

## 安全机制

本项目针对生产数据库场景内置了多层防护：

1. **DML 强制确认**——`INSERT` / `UPDATE` / `DELETE` 执行前必须经过人工确认，AI 禁止自主执行
2. **部署前预检**——推荐流程为 `sp-parser` 语法检查 → `oracle-reviewer` 代码审查 → `sp-deploy` 部署
3. **测试只读**——`sp-test-data-gen` 全程仅允许 `SELECT`，任何修改数据库的操作即判定任务失败
4. **连接信息隔离**——数据库凭据仅存于 `.env`，不入版本库
5. **输出物隔离**——AI 产物统一存入 `outputs/`，禁止污染 `src/` 源码目录

---

## 许可证

[MIT](LICENSE)

## 免责声明

FLUX WMS 是富勒科技的商业产品，本项目与其无隶属关系，仅为面向该系统二次开发场景的效率工具集。使用本项目产生的任何数据库变更请务必在测试环境验证后操作。
