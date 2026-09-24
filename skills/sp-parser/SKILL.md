---
name: sp-parser
description: |
  Oracle 存储过程语法检查工具
  触发场景：检查存储过程语法、验证存储过程代码、预检查存储过程错误
  功能：将存储过程代码转换为内部匿名块，使用 DBMS_SQL.PARSE 进行语法检查
compatibility: ["Bash + SQLcl + Python"]
---

# sp-parser - Oracle 存储过程语法检查

## 概述

sp-parser 用于在部署存储过程之前进行语法预检查，避免因语法错误导致部署失败。
使用 DBMS_SQL.PARSE 进行真正的数据库级别语法检查，能检测语法错误和部分语义错误。

## 快速开始

### 方式一：检查项目文件中的存储过程（推荐）

```bash
# 一站式语法检查（自动清理临时文件和 __pycache__）
python ".claude/skills/sp-parser/scripts/syntax_check.py" "src/WMS_FTEST/routine/procedure_name.sql"
```

### 方式二：通过存储过程名称

```bash
# 传入存储过程名称，脚本自动在项目中查找对应的 .sql 文件
python ".claude/skills/sp-parser/scripts/syntax_check.py" "DONGCHENG_SPBCD_SKU"
```

### 方式三：仅转换（不执行检查）

```bash
# 仅做代码转换，输出转换后的匿名块（供调试用）
python ".claude/skills/sp-parser/scripts/transform.py" "src/WMS_FTEST/routine/procedure_name.sql"
```

---

## 使用流程

### 步骤 1-4：一站式执行

调用 `syntax_check.py` 脚本，自动完成以下全部步骤：

1. **获取代码**：根据文件路径/存储过程名/直接代码获取源码
2. **转换**：将存储过程封装为匿名块
3. **执行**：通过 SQLcl 执行 DBMS_SQL.PARSE 语法检查
4. **清理**：自动清理临时 `.sql` 文件和 `__pycache__` 目录

### 查看结果

- **通过**：输出 `✅ SYNTAX_CHECK_PASSED`
- **失败**：显示 Oracle 错误信息（ORA-/PLS- 错误码），退出码为 1

---

## 临时文件管理

### 自动清理机制

`syntax_check.py` 内置自动清理，无需手动干预：

- **临时 SQL 文件**：写入系统临时目录（`tempfile.mkstemp`），`finally` 块确保删除
- **`__pycache__` 目录**：每次执行完毕（无论成功/失败/异常）自动调用 `cleanup_pycache()` 删除
- **清理时机**：`try/finally` 结构保证即使发生异常也会执行清理

### 清理覆盖范围

| 临时文件 | 位置 | 清理时机 |
|----------|------|----------|
| `sp_check_*.sql` | 系统临时目录 | `finally` 块，执行完毕后立即删除 |
| `__pycache__/` | `scripts/` 目录 | `finally` 块 + 异常处理中，始终删除 |

---

## 完整的检查流程示例

### 示例 1：检查文件中的存储过程

```bash
python ".claude/skills/sp-parser/scripts/syntax_check.py" "src/WMS_FTEST/routine/DONGCHENG_SPBCD_SKU.sql"
```

### 示例 2：通过存储过程名称检查

```bash
python ".claude/skills/sp-parser/scripts/syntax_check.py" "DONGCHENG_SPBCD_SKU"
```

### 存储过程名称查找规则

当输入是存储过程名称时，脚本会按以下顺序查找文件：

1. `[名称].sql`（当前目录）
2. `src/WMS_FTEST/routine/[名称].sql`
3. `WMS_FTEST/routine/[名称].sql`
4. `outputs/[名称].sql`
5. `PROCEDURES/[名称].sql`
6. `procedures/[名称].sql`
7. 递归搜索项目中所有 `[名称].sql` 文件

注意：查找的是**项目文件夹中**的文件，而不是数据库中的代码，因为项目文件才是最新修改后的代码。

---

## 代码转换逻辑

转换脚本 `scripts/transform.py` 的核心功能：

1. **清理末尾斜杠**：移除 `/` 和多余空白
2. **移除 CREATE 前缀**：移除 `CREATE [OR REPLACE] [EDITIONABLE|NONEDITIONABLE]`
3. **保留完整声明**：保留 PROCEDURE/FUNCTION/PACKAGE 及其参数、 AUTHID 等
4. **封装为匿名块**：包装进 `DECLARE...BEGIN...END;` 结构

### 转换示例

**输入：**
```sql
CREATE OR REPLACE PROCEDURE test_proc(
    p_id    IN  INT,
    p_name  OUT VARCHAR2,
    p_date  IN OUT DATE
) AUTHID CURRENT_USER IS
BEGIN
    NULL;
END test_proc;
/
```

**输出：**
```sql
DECLARE
PROCEDURE test_proc(
    p_id    IN  INT,
    p_name  OUT VARCHAR2,
    p_date  IN OUT DATE
) AUTHID CURRENT_USER IS
BEGIN
    NULL;
END test_proc;
BEGIN
  NULL;
END;
```

---

## 支持的对象类型

| 类型 | 示例 | 支持状态 |
|------|------|----------|
| PROCEDURE | `CREATE PROCEDURE` | ✅ 支持 |
| FUNCTION | `CREATE FUNCTION` | ✅ 支持 |
| PACKAGE | `CREATE PACKAGE` | ✅ 支持 |
| PACKAGE BODY | `CREATE PACKAGE BODY` | ✅ 支持 |
| TRIGGER | `CREATE TRIGGER` | ✅ 支持 |
| TYPE | `CREATE TYPE` | ✅ 支持 |
| TYPE BODY | `CREATE TYPE BODY` | ✅ 支持 |

---

## 错误处理

### 常见错误类型

| 错误类型 | 示例 | 说明 |
|----------|------|------|
| 语法错误 | 缺少分号、括号不匹配 | DBMS_SQL.PARSE 会捕获 |
| 语义错误 | 表/列不存在 | 依赖检查时可能捕获 |
| 类型错误 | 类型不匹配 | 依赖检查时可能捕获 |

### 错误信息示例

```
ORA-06550: 第 5 行, 第 12 列:
PLS-00103: 出现符号 ")" 在需要下列之一时：
   ( begin case declare end exception exit for goto if loop mod
   null pragma raise return select update while with <an identifier>
```

---

## 注意事项

1. **只读检查**：此操作不会实际创建或修改存储过程
2. **长文本支持**：支持上千行甚至几千行的大存储过程
3. **需要 DBMS_SQL**：确保数据库用户有 DBMS_SQL 包执行权限
4. **网络依赖**：需要能够连接到 Oracle 数据库
5. **自动清理**：`syntax_check.py` 内置 `try/finally` 清理机制，无需手动清理临时文件
6. **退出码**：通过为 0，失败为 1（可用于 CI/CD 集成）

---

## 复用其他 SKILL

此 SKILL 复用以下 SKILL：

- **connect-oracle**：获取数据库连接配置并执行 SQL
  - 使用方式：在需要数据库操作时，调用 `connect-oracle` skill

---

## 配置文件位置

项目数据库配置（由 connect-oracle 读取）：
- `项目根目录/.env`
- 字段：`DB_CONNECTION`（完整连接字符串，用户名/密码@host:port/service）

典型配置示例：
```dotenv
DB_CONNECTION=WMS_FTEST/密码@172.16.10.171:61521/wmstest
```

> 注：密码包含特殊字符时，请在配置时正确处理，skill 执行时会通过 connect-oracle 读取配置并展开变量。

---

## 与 sp-deploy 的关系

sp-parser 与 sp-deploy 配合使用：

- **sp-parser**：部署前的语法预检查
- **sp-deploy**：实际部署存储过程到数据库

工作流程：
```
编写存储过程 → sp-parser 语法检查（含清理临时文件）→ 修复错误 → sp-deploy 部署
```

> **注意**：sp-parser 执行后**必须清理临时文件**再进入下一步，避免残留文件干扰后续操作。
