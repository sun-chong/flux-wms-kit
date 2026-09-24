# AGENTS.md

本文件是通用 AI 智能体的项目入口文件，请在所有操作中遵循这里约定的规范。

---

## 项目概述

FLUX WMS（富勒仓库管理系统）Oracle 数据库开发项目，包含存储过程、表、索引等数据库对象的定制化开发脚本。

---

## 项目目录结构

```
src/WMS_FTEST/       # 核心 SQL 脚本目录
├── routine/         # 存储过程（.sql 文件）
├── table/           # 表定义
├── index/           # 索引定义
├── package/         # 包定义
├── view/            # 视图
├── sequence/        # 序列

docs/                # 项目文档
├── dictionaries/    # 数据库字段字典
└── superpowers/     # Superpowers 插件文档（plans/、specs/）

queries/             # 查询脚本
outputs/             # AI 辅助开发输出文件（分析报告、优化方案等）
```

---

## 项目 Skill 参考（**重要：必须遵循**）

本项目依赖以下 Skills 开发，触发关键词匹配会自动调用，也可使用 `/skill-name` 手动调用。

| Skill | 用途 | 触发关键词 | 强制要求 |
| --- | --- | --- | --- |
| `connect-oracle` | 连接 Oracle 数据库执行 SQL，查询表数据，编译存储过程 | 连接数据库、Oracle查询、执行SQL、查询表数据、数据库操作 | **必须使用**（禁止直接使用 PowerShell） |
| `sp-deploy` | 部署存储过程到 Oracle 数据库 | 部署存储过程、编译存储过程、执行存储过程 | **必须使用** |
| `sp-parser` | 预检查存储过程语法错误 | 检查存储过程语法、验证存储过程 | 推荐使用 |
| `ddl-template` | 生成符合 Oracle 规范的 DDL 模板 | 新建存储过程、新建表、DDL模板 | **必须使用**（新建对象时、规划方案时） |

> - **【安全规则】** 使用 `connect-oracle` 执行 `INSERT`、`DELETE`、`UPDATE` 脚本时，无论处于什么模式，必须先向用户申请确认，**禁止自主执行**
> - **【Skill 联动规则】** 当 `superpowers:writing-plans` 的规划内容涉及**数据库对象创建或修改**（新建存储过程、函数、表）时，必须同时调用 `ddl-template`，确保计划中包含符合项目规范的 DDL 模板与编码风格约束

---

## 规则文件说明

以下规则文件位于 `.claude/rules/` 目录，会自动加载：

| 文件 | 说明 | 触发条件 |
| --- | --- | --- |
| plsql.md | SQL 开发规范（编码、命名、Oracle 语法） | **执行规划时 + 处理 .sql 文件时** |
| output.md | AI 输出物管理规范 | 始终加载 |
| reference.md | 参考资料索引（字典、接口文档、数据库连接） | 始终加载 |

---

## Oracle Skills 参考库

Oracle 官方 Skills 仓库的 `db` 域（18 个子目录、160+ 文件）提供模式级数据库开发最佳实践，已安装至本项目：`.agents/skills/db/`

> **【兼容性约束】** Skills 基于 Oracle 19c 基线，本项目使用 11g。
> - `db/agent/`（8 文件）：**全部 11g 完全兼容**，可直接使用
> - `db/plsql/`（10 文件）：**大部分兼容**，需过滤 12c+ 特性（`ACCESSIBLE BY`、`UTL_CALL_STACK`、`FETCH FIRST N ROWS ONLY`、`GENERATED ALWAYS AS IDENTITY`、JSON 原生类型、`PRAGMA UDF`、`DBMS_SQL.RETURN_RESULT`、Unified Auditing）
> - 11g 完全可用特性：MERGE、BULK COLLECT+LIMIT、FORALL+SAVE EXCEPTIONS、NOCOPY、RESULT_CACHE、DBMS_ASSERT、FORMAT_ERROR_BACKTRACE、PRAGMA AUTONOMOUS_TRANSACTION 等

### 按场景索引

| 场景 | 引用文件 | 核心内容 |
| --- | --- | --- |
| 编写异常处理 | `.agents/skills/db/plsql/plsql-error-handling.md` | 异常层级、自主事务日志、双捕获模式、共享异常包 |
| 优化大数据量处理 | `.agents/skills/db/plsql/plsql-performance.md` | BULK COLLECT+LIMIT（100-500/批）、FORALL+SAVE EXCEPTIONS、NOCOPY、RESULT_CACHE |
| 调试存储过程 | `.agents/skills/db/plsql/plsql-debugging.md` | DBMS_OUTPUT、DBMS_APPLICATION_INFO、SQL Trace |
| 安全 DML 操作 | `.agents/skills/db/agent/safe-dml-patterns.md` | WHERE 守卫、COUNT 前置、SAVEPOINT 干运行、LOB 处理 |
| ORA- 错误排查 | `.agents/skills/db/agent/ora-error-catalog.md` | 25 种常见 ORA- 错误的根因 + 诊断 + 修复方案 |

> 更多场景（包设计、集合类型、防注入、Schema 发现、DDL 风险评估等）详见 `.agents/skills/db/` 目录

**【重要】PL/SQL 规范必须在所有阶段遵守**

- 规划阶段制定执行计划时，必须遵循 `plsql.md` 中的关键约束：
  - **Oracle 11g 不支持 `FETCH FIRST N ROWS ONLY`**，必须使用 `ROWNUM <= N`
  - **禁止使用 `GOTO` 语法**，任何场景均不允许
  - **禁止使用游标写法**，批量数据处理必须使用 `FOR` 循环结构
  - **每个 PL/SQL 块必须包含 `WHEN OTHERS THEN` 异常处理**
  - **子查询存在性检查使用 `EXISTS` / `NOT EXISTS`**，禁止 `IN` / `NOT IN`
  - **`LISTAGG` 必须校验字符串总长度**，防止 VARCHAR2(4000) 溢出
- Subagent 执行任何代码相关任务前，应先读取 `.claude/rules/plsql.md` 了解项目约束

---

## 跟踪号 / 托盘号的字段命名规则

- **业务上"跟踪号"和"托盘号"是同一个概念**，一般都是指 `TRACEID` 字段，除非特别说明，否则两者等价

---

## 代码修改工作流

**重要规则**：修改代码后，必须确认才能部署，禁止自动部署。

完整工作流程：

1. 新建存储过程/函数/表：必须先用 `ddl-template` 生成符合规范的模板
2. 修改完成后，**展示修改内容** → 向用户确认是否执行语法检查（`sp-parser`）或部署（`sp-deploy`）
3. 确认后按客户的需求执行语法检查，或者执行部署
4. **【推荐】语法检查通过后，使用 `oracle-reviewer` agent（`.claude/agents/oracle-reviewer.md`）审查代码**
5. AI 输出物（分析报告、测试脚本、临时存储过程等）**必须存入 `outputs/`**，遵循命名规范
6. **【禁止】不得在 `src/` 目录下创建任何临时、测试或中间文件** — 违反此规则会污染源码目录

修改已有代码时，也请参考 `ddl-template` 模板保持编码风格一致。

> **文件安全提醒**
> - 对超过 100 行的文件执行编辑/写入后，比对行数是否符合预期
> - 禁止使用 PowerShell 对 .sql / .json 等非 PowerShell 文件进行文本处理

---

## 代码重构规范

重构（简化、删除、重命名）是高风险操作，必须遵守以下规则：

1. **最小改动原则** — 用户要求"修复X"时，只改X，不顺带重构周边代码
2. **删除代码路径时** — 搜索该功能的所有引用（变量、条件、注释、ELSE 分支），一并清理
3. **合并代码时** — 验证合并后的版本覆盖所有原始边界场景，不仅是常见路径
4. **完成后必须 diff 审查** — 执行 `git diff` 逐行检查变更，确认无遗漏的 END IF / END LOOP / 变量引用

---

## 文件遍历限制（重要约束）

- **禁止使用 Glob 或类似工具列出 `docs/dictionaries/tables/` 目录下的所有文件**
- **禁止无差别遍历整个项目目录结构**，仅对已知路径的文件进行针对性读取
- 当需要了解表结构时，根据已知的表名直接读取具体的字典文件，例如 `Read docs/dictionaries/tables/已知表名.md`

---

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, each label equal to its role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.