---
name: flux-report-builder
description: >-
  FLUX WMS 报表构建器。将简化SQL转换为FLUX WMS合规报表，包含信息收集、SQL转换、功能验证、数据源写入、JSON生成、列配置写入、表单写入、验证和清理。
  仅通过 `/flux-report-builder` 斜杠命令触发，不自动触发。
  覆盖从简化SQL到数据库落盘的完整9步流程。
disable-model-invocation: true
---

# FLUX WMS 报表构建器

将用户输入的简化 SQL 转换为 FLUX WMS 系统合规报表，经过信息收集、SQL转换、功能验证、数据源配置写入、JSON列配置生成、列配置写入、表单配置写入、完成度验证、清理九阶段处理，最终完成自定义报表的全量数据库落盘。

---

## 流程概览

```
步骤 1: 收集输入信息 → 向用户询问功能编号、组织、简化SQL、报表结构、V6/V9版本
步骤 2: SQL 转换 → 生成完整 SQL（含系统字段）
步骤 3: 功能验证 → 验证 FUNCTIONID 存在（不存在则停止）
步骤 4: 数据源SQL写入 → 写入 DEV_UDFFUNCFG_QUERY + 多表联动（数据源SQL配置）
步骤 5: JSON 生成 → 基于 SQL 字段生成列配置 JSON
步骤 6: 列配置写入 → 写入 DEV_UDFFUNCFG_WIDGET 表（列表字段配置）
步骤 7: 表单生成并写入 → 生成表单配置 JSON，写入 DEV_UDFFUNCFG_FORM 表（表单字段配置）
步骤 8: 验证任务完成度 → 验证从步骤2~步骤7的所有任务是否均已写入正确完成
步骤 9: 清理临时文件 → 清理所有过程中产生的临时文件（全目录覆盖）
```

---

## 前提条件

1. **数据库连接**：配置在项目根目录 `.env` 的 `DB_CONNECTION` 字段
2. **Python 依赖**：`pip install oracledb`
3. **操作人署名**：配置在项目根目录 `.env` 的 `CLAUDE_CODE_AUTHOR` 字段，用于 ADDWHO/EDITWHO
4. **项目根目录**：所有脚本路径相对于项目根目录执行

---

## 步骤1：收集输入信息

**必须**先向用户逐一询问以下参数，**禁止假设默认值**。一次问完所有参数，避免反复追问。

### 需要向用户询问的参数

| 参数 | 说明 | 必填 |
|:---|:---|:---:|
| 功能编号 (FUNCTIONID) | 构建报表的功能编号，如 `C0104_MY_REPORT` | 是 |
| 组织编号 (ORGANIZATIONID) | 所属组织编码，如 `ND` | 是 |
| 简化SQL | 报表的SQL数据源（SELECT + FROM + WHERE） | 是 |
| 报表结构 | 表头结构还是明细结构 | 是 |
| 系统版本 | V6版本还是V9版本 | 是 |

### 自动获取的参数

| 参数 | 来源 |
|:---|:---|
| ADDWHO (操作人) | 从上下文 `[作者署名]` 或项目根目录 `.env` 的 `CLAUDE_CODE_AUTHOR` 字段自动获取 |

### 版本逻辑（关键）

- **V9 版本** → 列表字段 `type` 默认为 `"edtxt"`（可编辑文本框）
- **V6 版本** → 列表字段 `type` 默认为 `"ro"`（只读）

此逻辑在步骤5（JSON生成）中通过 `generate_json.py` 的 `--type` 参数实现。

### 页面描述逻辑（BSM_FUNCTION_PAGE_ML.PAGEDESCR）

多语言表 `BSM_FUNCTION_PAGE_ML` 中的 `PAGEDESCR` 字段根据报表结构决定：

| 报表结构 | 中文描述 | 英文描述 |
|:---|:---|:---|
| 表头结构 (headerGrid) | `头信息` | `Header Information` |
| 明细结构 (detailsGrid) | `明细信息` | `Detail Information` |

此逻辑在步骤4（数据源SQL写入）中通过 `insert_query_config.py` 的 `--page-descr-zh` / `--page-descr-en` 参数实现。

---

## 步骤2：SQL 转换

### 快速参考

| # | 规则 | 操作 | 位置 |
|:-|:---|:---|:---:|
| 1 | 语法检查 | Oracle SQL 语法验证，错误则终止 | 最先执行 |
| 2 | 自动别名 | 表无别名时分配 A、B、C… 并更新所有字段引用 | FROM/JOIN/SELECT/WHERE |
| 3 | 保留字段 | SELECT 字段原样保留（仅更新别名前缀） | SELECT 子句 |
| 4 | 补充固定字段 | 追加 13 个系统固定字段到 SELECT 末尾 | SELECT 末尾 |
| 5 | 注入动态条件 | WHERE 开头插入 `1=1 ${WHERE}` | WHERE 开头 |
| 6 | 注入日期范围 | **仅主表头报表**，追加 addTime 日期过滤 | WHERE 末尾 |
| 7 | 大小写规范 | addWho/addTime/editWho/editTime 严格小驼峰 | 全局 |

### 规则 1：语法检查（最先执行，不通过则终止）

检查项：关键字拼写、逗号位置、JOIN ON 完整性、括号匹配。**发现错误 → 立即停止并报告。**

### 规则 2：自动别名分配

当用户 SQL 中表无显式别名时：
- 主表（FROM 第一个表）→ `A`
- 后续 JOIN 表 → `B`、`C`、`D`...
- 更新 SELECT/WHERE/ON/GROUP BY/ORDER BY 中所有字段引用
- **若用户已定义别名，跳过此规则。**

### 规则 3：保留用户 SELECT 字段

字段名、别名（AS）、顺序、大小写均保持不变，包括计算表达式和函数调用。

### 规则 4：补充固定字段

在 SELECT 末尾追加 13 个系统字段，使用**主表别名**（通常为 `A`）作前缀：

| # | 字段表达式 | 说明 |
|:-|:---|:---|
| 1 | `DBMS_LOB.SUBSTR({alias}.noteText,2000) AS noteText` | 备注（必须用 DBMS_LOB.SUBSTR） |
| 2-7 | `{alias}.udf01` ~ `{alias}.udf06` | 自定义字段 |
| 8 | `{alias}.currentVersion` | 版本号 |
| 9 | `{alias}.oprSeqFlag` | 操作流水标记 |
| 10 | `{alias}.addWho` | 新增人员 |
| 11 | `{alias}.addTime` | 新增时间 |
| 12 | `{alias}.editWho` | 编辑人员 |
| 13 | `{alias}.editTime` | 编辑时间 |

### 规则 5：注入动态条件

WHERE 子句最开头插入 `1=1 ${WHERE}`：
- 有 WHERE → 放在所有条件之前
- 无 WHERE → 新增 `WHERE 1=1 ${WHERE}`

### 规则 6：注入默认日期范围过滤

**仅主表头报表（headerGrid）** WHERE 末尾追加：
```sql
AND {alias}.addTime>=TO_DATE('${FMDATE}','YYYY-MM-DD HH24:MI:SS')
AND {alias}.addTime<=TO_DATE('${TODATE}','YYYY-MM-DD HH24:MI:SS')
```

**明细报表（detailsGrid）不注入日期范围。**

### 规则 7：字段名大小写规范

- **固定字段**：`addWho`、`addTime`、`editWho`、`editTime` **必须小驼峰**，禁止大写形式
- **用户字段**：保持原样（通常 UPPERCASE）

### 转换后的 SQL 保存

转换后的 SQL 必须保存到文件 `outputs/{功能编号}_CONVERTED.sql`，供后续步骤使用。

---

## 步骤3：功能验证

**在 JSON 生成前必须执行。验证未通过则禁止继续。**

### 执行方式

使用脚本 `scripts/check_function_exists.py` 验证：

```bash
python scripts/check_function_exists.py {FUNCTIONID} --org-id {ORGANIZATIONID}
```

### 验证流程

1. 执行验证脚本
2. 不存在 → 停止，告知用户先在系统创建，创建成功后告诉我
3. 存在 → 验证通过，继续步骤4
4. 用户回复"已创建" → 重新执行验证脚本 → 通过后继续

### 退出码说明

| 退出码 | 含义 | 处理方式 |
|:---:|:---|:---|
| 0 | 验证通过，功能存在且激活 | 继续执行 |
| 1 | 功能不存在 | 停止，告知用户先创建 |
| 2 | 功能存在但未激活 | 警告，询问用户是否继续 |

---

## 步骤4：数据源SQL写入（多表联动）

**目标**：将用户配置的数据源SQL写入系统，涉及 4 张表的联动写入。

### 涉及的表（严格按此顺序写入）

| 顺序 | 表名 | 操作 | 说明 |
|:---:|:---|:---:|:---|
| 1 | `DEV_UDFFUNCFG` | UPDATE | 版本号递增 + 乐观锁更新 |
| 2 | `DEV_UDFFUNCFG_QUERY` | INSERT/UPDATE | 数据源SQL配置（核心） |
| 3 | `BSM_FUNCTION_PAGE` | DELETE + INSERT | 页面注册（先删旧的再插新的） |
| 4 | `BSM_FUNCTION_PAGE_ML` | DELETE + INSERT | 多语言页面描述（中/英） |

**关键约束**：DELETE + INSERT 必须作为事务执行，不能分开提交。

### 执行方式

使用脚本 `scripts/insert_query_config.py` 执行写入，**必须使用 `--sql-file` 参数**避免SQL截断：

```bash
python scripts/insert_query_config.py {FUNCTIONID} \
  --sql-file outputs/{FUNCTIONID}_CONVERTED.sql \
  --table-name {主表名} \
  --pkey "{主键字段,逗号分隔}" \
  --widget-name {headerGrid 或 detailsGrid} \
  --page-descr-zh "{头信息 或 明细信息}" \
  --page-descr-en "{Header Information 或 Detail Information}" \
  --org-id {ORGANIZATIONID}
```

**参数说明**：
- `--page-descr-zh` / `--page-descr-en`：根据步骤1收集的报表结构决定（表头→"头信息"/"Header Information"，明细→"明细信息"/"Detail Information"）
- `--table-name`：数据源主表名（从SQL的FROM子句获取）
- `--pkey`：主键字段列表（从数据字典或表结构获取）
- `--widget-name`：**必须与步骤1收集的报表结构一致**，明细报表必须显式传递 `--widget-name detailsGrid`，否则默认 `headerGrid` 会导致覆盖表头记录

### 版本号和乐观锁

脚本会自动处理：实时查询版本号 → 乐观锁更新 → 多表联动写入 → 事务提交 → 验证结果。**禁止手动拼接SQL。**

---

## 步骤5：JSON 生成

**必须从转换后的 SQL 文件生成，确保字段名与 SQL 完全一致。**

### 使用脚本生成 JSON

```bash
# V9 版本（默认 type=edtxt）
python scripts/generate_json.py --sql-file outputs/{FUNCTIONID}_CONVERTED.sql \
  --function-id {FUNCTIONID} \
  --widget-name {headerGrid 或 detailsGrid} \
  --output outputs/{FUNCTIONID}_config.json \
  --org-id {ORGANIZATIONID}

# V6 版本（type=ro）
python scripts/generate_json.py --sql-file outputs/{FUNCTIONID}_CONVERTED.sql \
  --function-id {FUNCTIONID} \
  --widget-name {headerGrid 或 detailsGrid} \
  --type ro \
  --output outputs/{FUNCTIONID}_config.json \
  --org-id {ORGANIZATIONID}
```

**`--type` 参数**：根据步骤1收集的系统版本决定，V9默认 `edtxt`，V6使用 `ro`。

### 字段命名一致性规则

- JSON 中的 `field` 字段名必须与**转换后完整的 SQL** 字段名**完全一致**
- 保留用户定义的别名（AS）
- 去掉表别名前缀（如 `A.CUSTOMERID` → `CUSTOMERID`）
- 系统字段 `addWho`/`addTime`/`editWho`/`editTime` 必须小驼峰

### items 数组结构

每个元素必填字段：

| 字段 | 类型 | 说明 | 示例 |
|:---|:---|:---|:---:|
| `id` | Number | 自增数字 | `20001` |
| `field` | String | 字段名（与SQL完全一致） | `"CUSTOMERID"` |
| `label` | String | 固定空字符串 | `""` |
| `udfLabel` | String | 中文列标题 | `"货主"` |
| `width` | String | 列宽（像素，字符串类型） | `"100"` |
| `sort` | String | 固定 `"str"` | `"str"` |
| `align` | String | 固定 `"left"` | `"left"` |
| `type` | String | V9→`"edtxt"`, V6→`"ro"` | `"edtxt"` |
| `filterType` | String | 固定 `""` | `""` |
| `calTpl` | String | 固定 `"0000.00"` | `"0000.00"` |
| `isCal` | String | 固定 `"N"` | `"N"` |
| `udfFormat` | String | 固定 `""` | `""` |
| `conFormName` | String | 固定 `""` | `""` |
| `conFormField` | String | 固定 `""` | `""` |
| `connector` | String | 固定 `""` | `""` |
| `systemCode` | String | 固定 `""` | `""` |
| `udfFlag` | String | 固定 `"Y"` | `"Y"` |
| `isUdf` | String | 固定 `"Y"` | `"Y"` |
| `cid` | String | 唯一标识，格式 `"c" + 数字` | `"c5001"` |
| `readonly` | String | 固定 `"Y"` | `"Y"` |

---

## 步骤6：列配置写入

**目标**：将 JSON 配置写入 `DEV_UDFFUNCFG_WIDGET` 表，并同步更新版本号和多语言标签。

### 执行方式

使用脚本 `scripts/insert_widget.py` 执行写入：

```bash
python scripts/insert_widget.py {FUNCTIONID} outputs/{FUNCTIONID}_config.json \
  --widget-name {headerGrid 或 detailsGrid} \
  --org-id {ORGANIZATIONID} \
  --force
```

涉及的表（严格按此顺序写入）：

| 顺序 | 表名 | 操作 | 说明 |
|:---:|:---|:---:|:---|
| 1 | `DEV_UDFFUNCFG` | UPDATE | 版本号递增 + 乐观锁更新 |
| 2 | `DEV_UDFFUNCFG_WIDGET` | INSERT/UPDATE | 列表字段配置（核心） |
| 3 | `BSM_MULTILANG_TEXT` | INSERT/UPDATE | 多语言标签主表 |
| 4 | `BSM_MULTILANG_TEXT_ML` | INSERT/UPDATE | 多语言标签明细（中/英） |

---

## 步骤7：表单生成并写入

**目标**：生成表单字段配置 JSON 并写入 `DEV_UDFFUNCFG_FORM` 表，同时更新版本号和多语言标签。

### 执行方式

使用脚本 `scripts/generate_form_config.py` 执行，脚本自动完成所有步骤：

```bash
# 从 SQL 文件生成并写入
python scripts/generate_form_config.py {FUNCTIONID} \
  --sql-file outputs/{FUNCTIONID}_CONVERTED.sql \
  --widget-name {headerGrid 或 detailsGrid} \
  --org-id {ORGANIZATIONID}
```

### 表单区块 ID 命名规则

**表头结构报表（headerGrid）**：
| 区块 | id / schemeTmpName |
|:---|:---|
| 主信息区块 | `{功能编号}HeaderForm` |
| 自定义区块 | `{功能编号}HeaderUdfForm` |
| 其他区块 | `{功能编号}HeaderOtherForm` |

**明细结构报表（detailsGrid）**：
| 区块 | id / schemeTmpName |
|:---|:---|
| 主信息区块 | `{功能编号}DetailForm` |
| 自定义区块 | `{功能编号}DetailUdfForm` |
| 其他区块 | `{功能编号}DetailOtherForm` |

### FORMNAME 字段规则

- **主表头报表**：`FORMNAME = 'headerGridFormEditorForm'`
- **明细报表**：`FORMNAME = 'detailsGridFormEditorForm'`

脚本已内置此逻辑，AI 无需手动处理。

---

## 步骤8：验证任务完成度

在所有写入完成后，**必须**验证从步骤2到步骤7的所有任务是否均已正确完成。

### 验证清单

执行以下查询验证：

| # | 验证项 | 说明 |
|:---:|:---|:---|
| 1 | `outputs/{FUNCTIONID}_CONVERTED.sql` 文件存在 | 确认SQL转换已保存 |
| 2 | `outputs/{FUNCTIONID}_config.json` 文件存在 | 确认JSON已生成 |
| 3 | 版本号已递增 | `SELECT currentversion FROM DEV_UDFFUNCFG WHERE functionid = '{FUNCID}'` |
| 4 | SQL已保存到数据源 | `SELECT JSON_VALUE(jsondata, '$.sqlMain') FROM DEV_UDFFUNCFG_QUERY WHERE functionid = '{FUNCID}'` |
| 5 | 页面已注册 | `SELECT tableid FROM BSM_FUNCTION_PAGE WHERE functionid = '{FUNCID}'` |
| 6 | 多语言页面描述已写入 | `SELECT languageid, pagedescr FROM BSM_FUNCTION_PAGE_ML WHERE functionid = '{FUNCID}'` |
| 7 | Widget配置已写入 | `SELECT COUNT(*) FROM DEV_UDFFUNCFG_WIDGET WHERE FUNCTIONID = '{FUNCID}'` |
| 8 | Form配置已写入 | `SELECT COUNT(*) FROM DEV_UDFFUNCFG_FORM WHERE FUNCTIONID = '{FUNCID}'` |
| 9 | 多语言标签已写入 | `SELECT COUNT(*) FROM BSM_MULTILANG_TEXT WHERE textkey LIKE '{FUNCID}%'` |

### 验证失败处理

| 场景 | 处理方式 |
|:---|:---|
| 某一步未执行 | 重新执行该步骤 |
| 写入但数据不正确 | 分析原因，修复后重新执行 |
| 所有验证通过 | 报告完成，进入步骤9 |

---

## 步骤9：清理临时文件

**所有步骤完成后自动执行，无需用户确认。**

```bash
python scripts/cleanup_temp_files.py --function-id {FUNCTIONID}
```

### 清理范围（安全清理）

| 区域 | 清理内容 | 安全策略 |
|:---|:---|:---:|
| 项目主 outputs/ | 仅清理 `{FUNCTIONID}_*` 前缀的文件（如 `_CONVERTED.sql`、`_config.json`） | **仅匹配本次功能编号** |
| Skill 本地 outputs/ | 所有中间产物 | 专属目录，安全 |
| Skill scripts/ 缓存 | `__pycache__/`、`.pyc` 文件 | 专属目录，安全 |
| 系统临时目录 | `flux_report_*`、`tmp*.sql`、`tmp*.json` 等 | 全局临时文件 |

### 保留内容

- outputs/ 下**非本次任务**的所有文件（用户其他功能的历史文件不受影响）
- `.claude/` 下的配置文件（SKILL.md、scripts/*.py 源码本身）
- `src/` 下的源码文件
- `docs/` 下的文档
- `outputs/.gitkeep` 等占位文件

> **为什么必须清理**：所有报表配置已写入数据库，本地中间文件只是过程产物。保留它们会污染项目目录，占用磁盘空间，且可能在下一次执行时造成字段名冲突。
>
> **安全策略**：清理脚本通过 `--function-id` 限定文件名前缀，**仅删除本次任务生成的文件**，不会误删其他功能的历史文件。

> **执行时机**：步骤8验证通过后立即执行。如果清理脚本报错，记录错误但继续完成整体流程，不得中断。

---

## 核心注意事项

### 通用规则

1. **字段命名一致性（最重要）**：JSON 中的 `field` 字段名必须与转换后完整的 SQL 字段名完全一致
2. **小驼峰命名法**：`addWho`/`addTime`/`editWho`/`editTime` 在 SQL 和 JSON 中必须小驼峰
3. **明细报表判断**：用户提到"明细"/"子表"/"detailsGrid" → widgetName 使用 `detailsGrid`
4. **功能验证**：写入前必须验证 FUNCTIONID 存在，不存在则停止等待用户创建
5. **编码处理**：使用 Python oracledb，不使用 SQLcl（UTF-8 问题）
6. **SQL 截断防范**：始终使用 `--sql-file` 参数传递 SQL，避免命令行转义
7. **乐观锁**：脚本自动处理版本号和乐观锁，禁止手动拼接 SQL

### 脚本执行路径

所有脚本路径相对于项目根目录：
```bash
python .claude/skills/flux-report-builder/scripts/{脚本名}.py ...
```

或在项目根目录执行（推荐）：
```bash
python scripts/insert_query_config.py ...  # 如果脚本在项目 scripts/ 中
```

实际路径取决于脚本部署位置，确保从正确的相对路径执行。

### 写入顺序约束

写入数据库时严格按以下顺序：
1. 先更新 DEV_UDFFUNCFG 版本号（乐观锁）
2. 再写入具体配置表（QUERY / WIDGET / FORM）
3. 最后维护多语言表（TEXT / TEXT_ML / PAGE_ML）

所有写入必须在同一事务中，失败时自动回滚。