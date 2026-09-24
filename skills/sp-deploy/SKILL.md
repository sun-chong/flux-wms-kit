---
name: sp-deploy
description: Oracle 存储过程部署 skill。用于编译和部署 Oracle 数据库中的存储过程。当用户提到部署存储过程、编译存储过程、执行存储过程脚本、运行 CREATE PROCEDURE/CREATE OR REPLACE 语句时触发此 skill。必须使用此 skill 进行 DDL 部署，禁止直接使用 SQLcl 执行 DDL。
compatibility:
  - Python oracledb (DDL 部署)
  - connect-oracle (查询操作)
---

# Oracle 存储过程部署

此 skill 用于将存储过程部署到 Oracle 数据库，包括编译和错误检查。

## 输入

用户需要提供存储过程文件路径（.sql 文件）。

## 执行步骤

### 步骤 1：读取存储过程文件

使用 Read 工具读取存储过程文件内容。

### 步骤 2：提取存储过程名称

从文件内容中提取存储过程名称：

1. 查找 `CREATE [OR REPLACE] PROCEDURE procedure_name` 或 `CREATE [OR REPLACE] FUNCTION function_name`
2. 提取过程/函数名称并转换为大写
3. 如果文件名包含存储过程名称，也可以从文件名提取

### 步骤 3：预部署合规检查

> 参考：`.claude/skills/db/agent/idempotency-patterns.md`、`.claude/skills/db/agent/destructive-op-guards.md`（均为 11g 完全兼容）

部署前对脚本进行基础校验，降低编译失败风险。

- **Oracle 标识符长度 ≤ 30 字符**
   - 过程名、函数名、包名等超过 30 字符会触发 `PLS-00114` 编译错误
   - 若超限：提示用户 → 显示超出字符数 → 建议缩短 → 终止部署。

- **幂等性检查**（参考 `.claude/skills/db/agent/idempotency-patterns.md`）：
   - 使用 `CREATE OR REPLACE` 确保脚本可重复执行
   - DDL 脚本中的 `ALTER TABLE ADD COLUMN`、`CREATE INDEX` 应包含存在性检查
   - INSERT 语句评估是否可改为 MERGE（upsert 模式）

- **破坏性操作检查**（参考 `.claude/skills/db/agent/destructive-op-guards.md`）：
   - 脚本中若包含 `DROP TABLE`、`DROP INDEX`、`TRUNCATE TABLE`，必须：
     1. 显示警告：操作不可逆（DROP 进回收站、TRUNCATE 不可回滚）
     2. 要求用户确认后方可继续
   - 若包含 `DELETE` 无 WHERE 子句或 `WHERE 1=1`，显示受影响行数并确认

### 步骤 4：检查现有编译错误

使用 connect-oracle skill 执行以下查询，检查该对象是否已有编译错误：

```sql
SELECT * FROM USER_ERRORS WHERE NAME = UPPER('存储过程名称') ORDER BY SEQUENCE
```

### 步骤 5：检查存储过程是否存在

执行以下查询检查存储过程是否已存在于数据库中：

```sql
SELECT OBJECT_NAME, OBJECT_TYPE, STATUS
FROM USER_OBJECTS
WHERE OBJECT_NAME = UPPER('存储过程名称')
  AND OBJECT_TYPE IN ('PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY')
```

### 步骤 6：自动转换语法（如需要）

如果满足以下条件，需要将 `CREATE PROCEDURE` 转换为 `CREATE OR REPLACE PROCEDURE`：
1. SQL 脚本使用 `CREATE PROCEDURE` 或 `CREATE FUNCTION`（不包含 `OR REPLACE`）
2. 存储过程已在数据库中存在

转换规则：
- `CREATE PROCEDURE proc_name` → `CREATE OR REPLACE PROCEDURE proc_name`
- `CREATE FUNCTION func_name` → `CREATE OR REPLACE FUNCTION func_name`

使用 Edit 工具将文件中的 CREATE 语句替换为 CREATE OR REPLACE 形式。

### 步骤 7：执行存储过程脚本

**必须使用 Python oracledb thick mode 执行 DDL，禁止使用 SQLcl。**

SQLcl 在 Windows 上存在 UTF-8 编码双重转换问题（UTF-8 字节被当作 Latin-1 解读后重新编码为 UTF-8），导致中文注释和字符串乱码。Python oracledb thick mode 通过 Oracle Instant Client 直接连接数据库，编码正确。

执行命令：

```bash
cd "项目根目录" && python .agents/skills/sp-deploy/scripts/oracle_deploy.py "SQL文件绝对路径或相对路径"
```

脚本自动完成：
1. 从项目根目录 `.env` 读取数据库连接配置（`DB_CONNECTION`）
2. 使用 Oracle Instant Client 19.24 thick mode 连接 Oracle 11g（目录缺失时自动运行 setup_instantclient.py 下载）
3. 执行 SQL 文件中的 DDL 语句（CREATE/ALTER PROCEDURE 等）
4. 检查编译错误
5. 可选：验证中文 UTF-8 编码正确性

**可选参数：**
- `--check-only`：仅检查编译错误，不执行部署
- `--verify`：部署后验证中文编码（通过 RAWTOHEX 检测"功能描述"的 UTF-8 编码）

### 步骤 8：检查新编译错误

再次执行步骤 4 的查询（`USER_ERRORS`），检查部署后是否存在新的编译错误。

### 步骤 9：处理结果

- **若存在编译错误**：显示错误信息并终止执行
- **若检测到乱码**：显示警告信息，但继续执行（让用户确认）
- **若无误且无乱码**：显示成功信息，部署完成

## 错误处理

如果用户提供的文件不存在或无法读取，返回错误信息并终止执行。

如果 Python 脚本执行失败，检查以下常见问题：
- `oracledb` 未安装：`pip install oracledb`
- Oracle Instant Client 目录缺失：脚本会自动运行 setup_instantclient.py 下载（约 76MB，需网络）；下载失败时手动执行 python skills/sp-deploy/scripts/oracle-instant-client/setup_instantclient.py
- 数据库连接失败：检查项目根目录 `.env` 中的 `DB_CONNECTION` 配置

## 成功输出格式

```
存储过程 [名称] 部署成功
编译状态：无错误
[可选] 中文编码检查：正常 / ⚠️ 检测到潜在乱码
```

## 乱码检测规则

脚本通过以下方式检测乱码：
- 字符串特征检测：`锟`（UTF-8 → GBK 转换失败）、`?`（未知字符占位符）、`�`（Unicode 替换字符）
- RAW 编码验证：`RAWTOHEX(UTL_RAW.CAST_TO_RAW(SUBSTR(TEXT, 1, 30)))` 检查"功能描述"的 UTF-8 编码是否为 `E58A9FE883BDE68F8FE8BFB0`
