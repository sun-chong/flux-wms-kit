# FLUX WMS 报表构建器脚本

本目录包含 FLUX WMS 报表构建器的固化脚本，用于执行数据库查询、验证和写入操作。

## 脚本列表

### 1. check_function_exists.py

**功能**：验证功能编号（FUNCTIONID）是否存在于 `DEV_UDFFUNCFG` 表

**用途**：在生成 JSON 配置和写入数据库之前，必须先验证功能编号是否存在

**使用方法**：
```bash
# 详细模式（默认）
python scripts/check_function_exists.py C0104_ATT_TEST

# 静默模式（仅输出 JSON 结果）
python scripts/check_function_exists.py C0104_ATT_TEST --quiet

# 指定配置文件
python scripts/check_function_exists.py C0104_ATT_TEST --config /path/to/.env
```

**退出码**：
- `0`：验证通过，功能存在且激活
- `1`：功能不存在
- `2`：功能存在但未激活

**示例输出**：
```
功能 'C0104_ATT_TEST' 已存在，验证通过
```

---

### 2. query_dictionary.py

**功能**：查询表字段的中文名称

**用途**：为报表列配置生成中文标签（udfLabel）

**使用方法**：
```bash
# 查询表的所有字段（JSON 格式）
python scripts/query_dictionary.py UDF_PURCHASINGGROUP

# 查询指定字段的中文名称
python scripts/query_dictionary.py UDF_PURCHASINGGROUP --fields CUSTOMERID GROUPCODE GROUPDESCR1

# 查询并输出为表格格式
python scripts/query_dictionary.py UDF_PURCHASINGGROUP --format table

# 查询指定字段并输出为 CSV 格式
python scripts/query_dictionary.py UDF_PURCHASINGGROUP --fields CUSTOMERID GROUPCODE --format csv
```

**输出格式**：
- `json`（默认）：JSON 格式
- `table`：表格格式
- `csv`：CSV 格式

**示例输出（JSON 格式）**：
```json
{
  "CUSTOMERID": "货主",
  "GROUPCODE": "采购组",
  "GROUPDESCR1": "采购组描述"
}
```

---

### 3. insert_widget.py

**功能**：将 JSON 配置写入 `DEV_UDFFUNCFG_WIDGET` 表，并同步更新版本号和多语言标签

**用途**：执行完整的列配置写入流程，包括版本更新、Widget 写入、多语言标签写入

**写入顺序**：
1. `DEV_UDFFUNCFG` — 更新版本号（乐观锁）
2. `DEV_UDFFUNCFG_WIDGET` — 插入/更新列表字段配置
3. `BSM_MULTILANG_TEXT` — 插入/更新多语言标签主表
4. `BSM_MULTILANG_TEXT_ML` — 插入/更新多语言标签明细（中/英）

**使用方法**：
```bash
# 写入主表头报表配置
python scripts/insert_widget.py C0104_ATT_TEST config.json --widget-name headerGrid

# 写入明细报表配置
python scripts/insert_widget.py C0104_ASN_DETAIL config.json --widget-name detailsGrid

# 强制覆盖已有记录
python scripts/insert_widget.py C0104_ATT_TEST config.json --widget-name headerGrid --force

# 指定组织ID
python scripts/insert_widget.py C0104_ATT_TEST config.json --org-id ND

# 跳过版本号更新（用于调试）
python scripts/insert_widget.py C0104_ATT_TEST config.json --skip-version-update
```

**参数说明**：
- `function_id`：功能编号（必填）
- `json_file`：JSON 配置文件路径（必填）
- `--widget-name`：组件名称，可选 `headerGrid` 或 `detailsGrid`（默认：headerGrid）
- `--org-id`：组织ID（默认：ND）
- `--config`：数据库配置文件路径（可选）
- `--force`：强制覆盖已有记录
- `--skip-version-update`：跳过版本号更新（用于调试）

**关键特性**：
- **实时获取版本号**：写入前自动查询 `DEV_UDFFUNCFG` 的 `currentversion` 和 `oprseqflag`
- **乐观锁机制**：使用旧的 `oprseqflag` 作为 UPDATE 的 WHERE 条件，防止并发冲突
- **多语言标签写入**：自动为每个字段创建中文和英文标签
- **事务完整性**：所有写入在同一事务中，失败时自动回滚
- **自动验证**：写入完成后自动验证所有表的数据

**注意：** 用户信息（`ADDWHO`/`EDITWHO`）从配置文件项目根目录 `.env` 中的 `CLAUDE_CODE_AUTHOR` 字段获取。

**示例输出**：
```
操作用户: ZHOUTT
功能编号: C0104_ATT_TEST
组件名称: headerGrid
组织ID: ND

[步骤1] 获取功能的当前版本号和乐观锁...
  当前版本: 100.00000000 → 新版本: 101.00000000
  旧乐观锁: 20260605102350000175RA010...
  新乐观锁: 20260605102730000275RA010...
[步骤1] DEV_UDFFUNCFG 版本号更新成功: 100.00000000 → 101.00000000

[步骤2] INSERT 执行成功！功能编号: C0104_ATT_TEST, 组件: headerGrid

[步骤3] 写入多语言标签配置...
  ✓ 已写入 6 个多语言标签

✓ 事务已提交，所有写入完成。

============================================================
写入验证报告
============================================================

1. DEV_UDFFUNCFG（功能主表）:
   版本号: 101.00000000
   乐观锁: 20260605102730000275...

2. DEV_UDFFUNCFG_WIDGET（列表配置）:
   功能编号: C0104_ATT_TEST
   组件名称: headerGrid
   JSON 长度: 1234 字节
   第一个字段的 udfLabel: 货主
   包含 addWho: True
   包含 addTime: True
   包含 editWho: True
   包含 editTime: True

3. 多语言标签:
   BSM_MULTILANG_TEXT 记录数: 6
   BSM_MULTILANG_TEXT_ML (zh_CN) 记录数: 6
   示例标签:
     - headerGrid_ORGANIZATIONID: 组织
     - headerGrid_CUSTOMERID: 货主
     - headerGrid_GROUPCODE: 采购组编码

============================================================
```

---

### 4. insert_query_config.py

**功能**：将数据源SQL写入系统，涉及多表联动写入

**用途**：执行数据源SQL配置的写入，严格按系统处理顺序操作 4 张表

**写入顺序**：
1. `DEV_UDFFUNCFG` — 更新版本号（乐观锁）
2. `DEV_UDFFUNCFG_QUERY` — 插入/更新SQL配置
3. `BSM_FUNCTION_PAGE` — 删除旧的再插入新的
4. `BSM_FUNCTION_PAGE_ML` — 删除旧的再插入新的多语言

**使用方法**：

**推荐用法（使用 --sql-file 参数，避免命令行转义问题）**：
```bash
# 步骤1：将转换后的 SQL 保存到文件
# （在 SQL 转换步骤中，将结果保存为 .sql 文件）

# 步骤2：使用 --sql-file 参数执行写入
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql-file outputs/C0104_AZTT_PURSGROUP.sql \
  --table-name UDF_PURCHASINGGROUP \
  --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE"

# 指定页面描述
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql-file outputs/C0104_AZTT_PURSGROUP.sql \
  --table-name UDF_PURCHASINGGROUP \
  --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \
  --page-descr-zh "主信息" \
  --page-descr-en "Main Information"

# 指定组织ID
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql-file outputs/C0104_AZTT_PURSGROUP.sql \
  --table-name UDF_PURCHASINGGROUP \
  --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \
  --org-id ND

# 仅预览，不执行
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql-file outputs/C0104_AZTT_PURSGROUP.sql \
  --table-name UDF_PURCHASINGGROUP \
  --pkey "ORGANIZATIONID,CUSTOMERID,GROUPCODE" \
  --dry-run
```

**不推荐用法（仅适用于简单 SQL，无特殊字符）**：
```bash
# 直接传递 SQL（可能因特殊字符导致截断）
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql "SELECT A.ORGANIZATIONID, A.CUSTOMERID FROM UDF_PURCHASINGGROUP A WHERE 1=1 \${WHERE}" \
  --table-name UDF_PURCHASINGGROUP \
  --pkey "ORGANIZATIONID,CUSTOMERID"
```

**参数说明**：
- `function_id`：功能编号（必填）
- `--sql`：数据源SQL，必须含 `${WHERE}` 占位符（与 `--sql-file` 二选一）
- `--sql-file`：从文件读取 SQL（推荐，避免命令行转义问题，与 `--sql` 二选一）
- `--table-name`：数据源表名（必填）
- `--pkey`：主键字段列表，逗号分隔（必填）
- `--widget-name`：组件名称，可选 `headerGrid` 或 `detailsGrid`（默认：headerGrid）
- `--page-descr-zh`：中文页面描述（默认：主信息）
- `--page-descr-en`：英文页面描述（默认：Main Information）
- `--page-size`：每页行数（默认：100）
- `--org-id`：组织ID（默认：ND）
- `--config`：数据库配置文件路径（可选）
- `--dry-run`：仅预览JSON内容，不执行写入
- `--skip-validation`：跳过 SQL 完整性校验（不推荐）

**关键特性**：
- **实时获取版本号**：写入前自动查询 `DEV_UDFFUNCFG` 的 `currentversion` 和 `oprseqflag`
- **乐观锁机制**：使用旧的 `oprseqflag` 作为 UPDATE 的 WHERE 条件，防止并发冲突
- **多表联动事务**：4 张表的写入在同一个事务中，失败时自动回滚
- **SQL 完整性校验**：默认检查 SQL 长度、关键字和 `${WHERE}` 占位符，防止命令行转义导致 SQL 截断

**⚠️ 避免 SQL 截断问题**：
在 PowerShell 环境下，SQL 语句包含特殊字符（`${WHERE}`、`${FMDATE}`、单引号、反引号等）时，命令行传递过程中会被转义或截断，导致插入数据库的 SQL 不完整。

**推荐做法**：
1. 在 SQL 转换步骤中，将结果保存为 `.sql` 文件
2. 使用 `--sql-file` 参数从文件读取 SQL，完全避免命令行转义问题

**临时跳过校验**（不推荐）：
```bash
python scripts/insert_query_config.py C0104_AZTT_PURSGROUP \
  --sql "..." \
  --table-name TABLE_NAME \
  --pkey "KEY1" \
  --skip-validation
```
- **自动验证**：写入完成后自动验证所有表的数据

**示例输出**：
```
[步骤1] 获取功能 C0104_AZTT_PURSGROUP 的当前版本号和乐观锁...
  当前版本: 100.00000000 → 新版本: 101.00000000
  旧乐观锁: 20260605102350000175RA010...
  新乐观锁: 20260605102730000275RA010...

[步骤2] 更新 DEV_UDFFUNCFG 版本号（乐观锁更新）...
  ✓ 更新成功，影响 1 行

[步骤3] 写入 DEV_UDFFUNCFG_QUERY（数据源SQL配置）...
  ✓ INSERT 执行成功

[步骤4] 写入 BSM_FUNCTION_PAGE（页面注册 + 多语言）...
  ✓ 旧记录已清理
  ✓ BSM_FUNCTION_PAGE INSERT 成功
  ✓ BSM_FUNCTION_PAGE_ML (zh_CN) INSERT 成功
  ✓ BSM_FUNCTION_PAGE_ML (en) INSERT 成功

✓ 事务已提交，所有写入完成。

============================================================
写入验证报告
============================================================
1. DEV_UDFFUNCFG（功能主表）:
   版本号: 101.00000000
   布局模式: SINGLE
   ...

2. DEV_UDFFUNCFG_QUERY（数据源SQL）:
   组件名: headerGrid
   版本号: 101.00000000
   JSON长度: 1234 字节
   ...

3. 保存的SQL内容:
   SQL预览: SELECT A.ORGANIZATIONID, A.CUSTOMERID, A.GROUPCODE FROM UDF_PURCHASINGGROUP A WHERE 1=1 ${WHERE}...
   数据源表: UDF_PURCHASINGGROUP
   主键字段: ORGANIZATIONID,CUSTOMERID,GROUPCODE
   ...
============================================================
```

**注意：** 用户信息（`ADDWHO`/`EDITWHO`）从配置文件项目根目录 `.env` 中的 `CLAUDE_CODE_AUTHOR` 字段获取。

---

### 5. generate_json.py

**功能**：生成报表列配置 JSON

**用途**：从转换后的 SQL 文件生成列配置 JSON，用于写入 `DEV_UDFFUNCFG_WIDGET` 表

**使用方法**：
```bash
# 从 SQL 文件生成 headerGrid 配置（V9 版本，默认 type=edtxt）
python scripts/generate_json.py --sql-file outputs/query_converted.sql --function-id C0104_TEST --output outputs/config.json

# 从 SQL 文件生成 detailsGrid 配置
python scripts/generate_json.py --sql-file outputs/query_converted.sql --function-id C0104_TEST --widget-name detailsGrid --output outputs/config.json

# V6 版本（只读字段 type=ro）
python scripts/generate_json.py --sql-file outputs/query_converted.sql --function-id C0104_TEST --type ro --output outputs/config.json

# 打印到标准输出（不保存文件）
python scripts/generate_json.py --sql-file outputs/query_converted.sql --function-id C0104_TEST
```

**参数说明**：
- `--sql-file`：转换后的 SQL 文件路径（推荐，确保字段名一致）
- `--function-id`：功能编号（必填）
- `--widget-name`：组件名称，可选 `headerGrid` 或 `detailsGrid`（默认：headerGrid）
- `--type`：字段类型，V9 用 `edtxt`，V6 用 `ro`（默认：edtxt）
- `--output`：输出文件路径（可选）
- `--org-id`：组织 ID（默认：ND）

**V6/V9 版本说明**：
- V9 版本 → `type` 默认为 `edtxt`（可编辑文本框）
- V6 版本 → `type` 使用 `ro`（只读）

---

### 6. verify_widget.py

**功能**：验证 `DEV_UDFFUNCFG_WIDGET` 表中的 JSON 配置

**用途**：验证写入后的配置是否正确

**使用方法**：
```bash
# 验证主表头报表配置
python scripts/verify_widget.py C0104_ATT_TEST --widget-name headerGrid

# 验证明细报表配置
python scripts/verify_widget.py C0104_ASN_DETAIL --widget-name detailsGrid

# 导出 JSON 到文件
python scripts/verify_widget.py C0104_ATT_TEST --export verified_config.json

# 指定配置文件
python scripts/verify_widget.py C0104_ATT_TEST --config /path/to/.env
```

**验证内容**：
1. 记录是否存在
2. JSON 结构是否有效
3. 中文字符是否正常
4. 字段名是否使用小驼峰形式

**示例输出**：
```
============================================================
FLUX WMS 报表配置验证报告
============================================================
功能编号: C0104_ATT_TEST
组件名称: headerGrid
============================================================

1. 记录存在性验证:
   ✓ 记录存在

2. JSON 结构验证:
   ✓ JSON 结构有效

3. 中文字符验证:
   ✓ 中文字符正常

4. 字段名验证:
   ✓ 字段名正确

5. 统计信息:
   - 列数: 6
   - 网格类型: headerGrid
   - 小驼峰字段: addWho, addTime, editWho, editTime

============================================================
```

---

## 配置文件

所有脚本都从项目根目录 `.env` 读取数据库连接配置和用户配置：

```dotenv
DB_CONNECTION=username/password@host:port/service_name
CLAUDE_CODE_AUTHOR=USERNAME
```

**配置项说明**：
- `DB_CONNECTION`：数据库连接字符串
- `CLAUDE_CODE_AUTHOR`：操作用户，用于 `ADDWHO` 和 `EDITWHO` 字段

可以通过 `--config` 参数指定其他配置文件路径。

---

## 依赖项

- Python 3.7+
- oracledb（thin mode，不需要 Oracle Client）

安装依赖：
```bash
pip install oracledb
```

---

## 注意事项

1. **中文编码**：所有脚本都使用 `json.dumps(ensure_ascii=False)` 确保中文正确编码
2. **小驼峰命名**：验证脚本会检查 `addWho`、`addTime`、`editWho`、`editTime` 是否使用小驼峰形式
3. **事务控制**：写入脚本会自动提交事务
4. **CLOB 类型**：验证脚本会自动处理 CLOB 类型的 `.read()` 调用
