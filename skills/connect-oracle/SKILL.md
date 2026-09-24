---
name: connect-oracle
description: |
  Oracle database SQL execution skill. Trigger on: Oracle query, SQL execution, PL/SQL compile, stored procedure deploy, database connection.
  触发场景：Oracle查询、执行SQL、编译存储过程、连接数据库、查询表数据。
  Must use Bash+SQLcl, never PowerShell.
compatibility: ["Bash + SQLcl"]
user-invocable: false
---

# Connect Oracle Database

## 快速开始（推荐方式）

当用户需要执行任何数据库操作时，**立即按以下步骤执行**：

### 步骤 1：获取数据库连接信息

连接字符串配置在**项目根目录的 `.env` 文件**中（`DB_CONNECTION` 字段）。

> Bash 工具每次调用不保留 shell 状态，因此**加载连接串与执行 SQL 必须写在同一条命令中**。标准加载前缀：

```bash
cd "项目根目录" && DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r')
```

**⚠️ 禁止将 .env 内容读入对话上下文**：
- 禁止使用 Read 工具读取 `.env`（该文件被 Read deny 规则保护）
- 禁止 `cat .env`、`echo "$DB_CONNECTION"` 等回显密码的命令
- 正确方式：如上所示，通过命令替换在同一条 Bash 命令内完成取值和使用，密码值不进入对话记录

### 步骤 2：执行 SQL 命令

**⚠️ 必须使用 Bash 工具执行，禁止使用 PowerShell！**

使用以下命令格式执行 SQL：
```bash
cd "项目根目录" && DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r') && echo '你的SQL语句; EXIT;' | sql -S "$DB_CONNECTION"
```
**注意：必须使用双引号包裹，变量才能正确展开！单引号不会展开变量**

**完整示例：**
```bash
# 1. 连接串从项目根目录 .env 加载（同一条命令内完成）
# 文件: .env
# 典型值: DB_CONNECTION=WMS_FTEST/密码@172.16.10.171:61521/wmstest

# 2. 加载并执行（必须用双引号，变量才能展开）
cd "项目根目录" && DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r') && echo 'SELECT 1 FROM DUAL; EXIT;' | sql -S "$DB_CONNECTION"
```

---

## 命令执行标准模板

以下模板中的加载前缀 `DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r')` 必须与 SQL 执行写在**同一条命令**中（Bash 工具不保留 shell 状态）。为简洁起见，后续示例以 `[$DB_CONNECTION 已从 .env 加载]` 表示该前缀。

### 模板 1：管道方式（推荐）

```bash
cd "项目根目录" && DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r') && echo 'SQL语句; EXIT;' | sql -S "$DB_CONNECTION"
```

### 模板 2：HEREDOC 方式（适合多行 SQL）

```bash
cd "项目根目录"; DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r'); sql -S "$DB_CONNECTION" <<'EOF'
SELECT * FROM 表名 WHERE ROWNUM <= 10;
EXIT;
EOF
```

### 模板 3：执行 SQL 文件

```bash
cd "项目根目录"; DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r'); sql -S "$DB_CONNECTION" <<'EOF'
@文件路径.sql
EXIT;
EOF
```

**注意**：必须使用 `@` 方式执行 SQL 文件，不能使用 `<` 重定向。使用 `<` 重定向会导致 UTF-8 编码的 SQL 文件中文乱码。

> **已知问题（SQLcl stdin 编码）**：SQLcl 在 Windows 上通过 **任何 stdin 方式**（`echo | sql`、`cat << | sql`、`< file`）接收非 ASCII 字符时，JVM 会将 UTF-8 字节误解码为 Latin-1 后重新编码为 UTF-8 写入数据库，造成**双重编码**（中文变为乱码）。仅 `@` 文件方式可规避此问题。当 INSERT/UPDATE 语句包含中文字符串时，必须先写入临时 `.sql` 文件，再通过 `@` 方式执行。

**⚠️ DDL 部署请使用 Python oracledb**：SQLcl 在 Windows 上存在 UTF-8 编码问题，CREATE/ALTER PROCEDURE 等 DDL 操作请使用 `sp-deploy` skill（Python oracledb thick mode）。部署命令：`python .agents/skills/sp-deploy/scripts/oracle_deploy.py "SQL文件路径"`

---

## 常用操作速查

> 以下示例中的 `$DB_CONNECTION` 均需按模板 1 的方式，在同一条命令中先从项目根目录 `.env` 加载（完整示例见"测试连接"）。

### 测试连接
```bash
cd "项目根目录" && DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r') && echo 'SELECT 1 FROM DUAL; EXIT;' | sql -S "$DB_CONNECTION"
```

### 查询表数据
```bash
echo 'SELECT * FROM BAS_CUSTOMER WHERE ROWNUM <= 5; EXIT;' | sql -S "$DB_CONNECTION"
```

### 查看表结构
```bash
echo 'DESCRIBE DOC_ASN_HEADER; EXIT;' | sql -S "$DB_CONNECTION"
```

### 编译存储过程
```bash
echo 'ALTER PROCEDURE DC_CLEAN_UP_DATA COMPILE; EXIT;' | sql -S "$DB_CONNECTION"
```

### 检查编译错误
```bash
echo "SELECT line, text FROM user_errors WHERE name = 'DC_CLEAN_UP_DATA' ORDER BY sequence; EXIT;" | sql -S "$DB_CONNECTION"
```

### Schema 对象查询（参考 Oracle Skills `db/agent/schema-discovery.md`）

> 以下查询基于 ALL_* 视图，符合权限最小化原则，均为 11g 完全兼容。
> 详细查询参考：`.claude/skills/db/agent/schema-discovery.md`

**查看表结构和列信息：**
```bash
echo "SELECT column_name, data_type, data_length, nullable, data_default FROM all_tab_columns WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND table_name = UPPER('DOC_ASN_HEADER') ORDER BY column_id; EXIT;" | sql -S "$DB_CONNECTION"
```

**查看表的索引：**
```bash
echo "SELECT i.index_name, i.uniqueness, LISTAGG(ic.column_name, ',') WITHIN GROUP (ORDER BY ic.column_position) AS columns FROM all_indexes i JOIN all_ind_columns ic ON i.owner = ic.index_owner AND i.index_name = ic.index_name WHERE i.owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND i.table_name = UPPER('DOC_ASN_HEADER') GROUP BY i.index_name, i.uniqueness; EXIT;" | sql -S "$DB_CONNECTION"
```

**查看表的约束（主键、外键、唯一、检查）：**
```bash
echo "SELECT constraint_name, constraint_type, search_condition, status FROM all_constraints WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND table_name = UPPER('DOC_ASN_HEADER'); EXIT;" | sql -S "$DB_CONNECTION"
```

**查看表的触发器：**
```bash
echo "SELECT trigger_name, trigger_type, triggering_event, status FROM all_triggers WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND table_name = UPPER('DOC_ASN_HEADER'); EXIT;" | sql -S "$DB_CONNECTION"
```

**查看 Schema 对象汇总：**
```bash
echo "SELECT object_type, COUNT(*) AS cnt FROM all_objects WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND object_type NOT IN ('INDEX','INDEX PARTITION','TABLE PARTITION','LOB','LOB PARTITION') GROUP BY object_type ORDER BY object_type; EXIT;" | sql -S "$DB_CONNECTION"
```

**查看无效对象：**
```bash
echo "SELECT object_name, object_type, last_ddl_time FROM all_objects WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND status = 'INVALID' ORDER BY object_type, object_name; EXIT;" | sql -S "$DB_CONNECTION"
```

**查看会话信息（Agent 标识）：**
```bash
echo "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS current_user, SYS_CONTEXT('USERENV','DB_NAME') AS db_name FROM DUAL; EXIT;" | sql -S "$DB_CONNECTION"
```

---

## 防错检查清单

在执行任何数据库操作前，验证以下几点：

1. ✅ 使用 Bash 工具（不是 PowerShell）
2. ✅ 连接串已从项目根目录 `.env` 加载，且加载与 SQL 执行在同一条命令中
3. ✅ 变量引用使用双引号：`"$DB_CONNECTION"`
4. ✅ SQL 语句末尾有 `EXIT;`

---

## 错误排查

> 完整 ORA- 错误目录参考：`.claude/skills/db/agent/ora-error-catalog.md`（25 种常见错误的根因 + 诊断 + 修复方案，11g 完全兼容）

| 错误码 | 原因 | 解决方案 |
|--------|------|----------|
| ORA-01017 | 用户名/密码无效 | 检查 .env 中的密码是否正确 |
| ORA-12154 | 无法解析服务名 | 检查 DB_CONNECTION 配置格式 |
| ORA-12541 | no listener | 检查监听器服务 |
| ORA-12543 | host unreachable | 检查网络连接 |
| ORA-00942 | 表或视图不存在 | 查 `all_tables` + `all_synonyms` 确认名称和权限 |
| ORA-00001 | 唯一约束违反 | 改用 MERGE 或检查现有数据 |
| ORA-02291 | 父键未找到 | 先插入父表记录 |
| ORA-02292 | 子记录存在 | 先删除子表记录 |

---

## 配置文件位置

配置文件：`项目根目录\.env`

典型配置内容：
```dotenv
DB_CONNECTION=WMS_FTEST/密码@172.16.10.171:61521/wmstest
CLAUDE_CODE_AUTHOR=SUNC
```
