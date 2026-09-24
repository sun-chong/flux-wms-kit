---
name: database-dictionary
description: |
  生成数据库字典的Markdown文件。为Oracle数据库生成每表一个独立.md文件的数据库字典。
  当用户要求生成数据库字典、导出表结构说明、创建数据字典文档时使用此技能。
  支持两种数据来源：
  1. BSM_DATA_DICTIONARY_FIELD 系统字典表
  2. COMMENT ON COLUMN/TABLE 数据库注释（通用方式）
  自动识别未在数据字典中维护的表并使用 COMMENT ON 方式补充。
---

# 数据库字典生成器

为Oracle数据库生成每表一个独立Markdown文件的数据库字典。

## 使用前提

1. **数据库连接配置**：项目根目录的 `.env` 文件中需要配置：
   ```dotenv
   DB_CONNECTION=用户名/密码@host:port/service
   ```

2. **输出目录**：字典文件将生成在 `docs/dictionaries/tables/` 目录下

## 执行步骤

### 步骤1：读取数据库配置

从项目根目录 `.env` 获取 `DB_CONNECTION` 字段（完整连接字符串）。

使用 connect-oracle skill 执行 SQL，传入 `$DB_CONNECTION` 环境变量。

### 步骤2：查询 BSM_DATA_DICTIONARY_FIELD 字典表

适用于在 BSM_DATA_DICTIONARY_FIELD 和 BSM_DATA_DICTIONARY_FIELD_ML 表中维护字典的项目。

**导出数据（使用 | 分隔符避免解析问题）**：
```sql
SET LINESIZE 500
SET PAGESIZE 1000
SET FEEDBACK OFF
SET HEADING OFF

SELECT
    TM.TABLENAME || '|' ||
    NVL(TM.TABLEDESCR, ' ') || '|' ||
    F.FIELDNAME || '|' ||
    NVL(FM.FIELDDESCR, ' ') || '|' ||
    NVL(FM.UDFFIELDDESCR, ' ') || '|' ||
    NVL(FM.NOTETEXT, ' ') || '|' ||
    F.KEYFLAG || '|' ||
    F.FIELDTYPE || '|' ||
    F.NULLFLAG || '|' ||
    NVL(F.DEFAULTVALUE, ' ')
FROM BSM_DATA_DICTIONARY_FIELD F
LEFT JOIN BSM_DATA_DICTIONARY_TABLE_ML TM ON TM.ORGANIZATIONID=F.ORGANIZATIONID
    AND TM.WAREHOUSEID=F.WAREHOUSEID AND TM.TABLENAME=F.TABLENAME
    AND TM.LANGUAGEID='zh_CN'
LEFT JOIN BSM_DATA_DICTIONARY_FIELD_ML FM ON FM.ORGANIZATIONID=F.ORGANIZATIONID
    AND FM.WAREHOUSEID=F.WAREHOUSEID AND FM.TABLENAME=F.TABLENAME
    AND FM.FIELDNAME=F.FIELDNAME AND FM.LANGUAGEID='zh_CN'
WHERE F.ORGANIZATIONID='DONGCHENG' AND F.WAREHOUSEID='*'
ORDER BY TM.TABLENAME, F.SHOWSEQUENCE;
```

### 步骤3：查询 COMMENT ON 字典表（补充表）

适用于使用数据库 COMMENT ON 存储表和字段说明的项目，以及未在 BSM_DATA_DICTIONARY_FIELD 中维护的表。

**重要**：Oracle 11g 中 user_col_comments.comments 是 LONG 类型，无法在 SQL 中直接使用字符串函数，必须使用 PL/SQL 游标处理。

**导出脚本**：
```sql
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 500
SET FEEDBACK OFF

SPOOL output_path/comment_dict.txt

DECLARE
    -- 游标获取所有 COMMENT 表
    CURSOR t IS
        SELECT t.table_name, t.comments AS table_desc
        FROM user_tab_comments t
        WHERE t.table_name NOT IN (
            SELECT DISTINCT f.TABLENAME
            FROM BSM_DATA_DICTIONARY_FIELD f
            WHERE f.ORGANIZATIONID = 'DONGCHENG' AND f.WAREHOUSEID = '*'
        )
        AND t.table_name NOT LIKE 'BIN$%'
        AND t.table_name NOT LIKE 'DR$%'
        AND t.table_type = 'TABLE'
        AND t.comments IS NOT NULL
        ORDER BY t.table_name;

    -- 游标获取表字段信息（LONG类型需要用游标）
    CURSOR col_c(p_table_name VARCHAR2) IS
        SELECT col.column_name, col.data_type, col.nullable, cc.comments AS col_desc
        FROM user_tab_columns col
        LEFT JOIN user_col_comments cc ON col.table_name = cc.table_name AND col.column_name = cc.column_name
        WHERE col.table_name = p_table_name
        ORDER BY col.column_id;
BEGIN
    FOR t_rec IN t LOOP
        DBMS_OUTPUT.PUT_LINE('===START===');
        DBMS_OUTPUT.PUT_LINE('TABLE:' || t_rec.table_name || '|' || t_rec.table_desc);

        FOR col_rec IN col_c(t_rec.table_name) LOOP
            DBMS_OUTPUT.PUT_LINE(col_rec.column_name || '|' || col_rec.data_type || '|' || col_rec.nullable || '|' || NVL(col_rec.col_desc, ''));
        END LOOP;
    END LOOP;
END;
/

SPOOL OFF
```

### 步骤4：生成Markdown文件

使用 Python 脚本处理导出的数据，生成每表一个 .md 文件：

**BSM_DATA_DICTIONARY_FIELD 格式**：
```markdown
# {表名}

**表描述**: {表描述}

## 字段列表

| 字段名称 | 字段描述 | 自定义描述 | 备注 | 主键标记 | 字段类型 | 允许为空 | 默认值 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 字段名 | 字段说明 | 自定义说明 | 备注 | Y/N | VARCHAR2 | Y/N | 默认值 |
```

**COMMENT ON 格式**：
```markdown
# {表名}

**表描述**: {表描述}

## 字段列表（来自 COMMENT ON）

| 字段名称 | 字段描述 | 字段类型 | 允许为空 |
| :--- | :--- | :--- | :--- |
| 字段名 | 字段说明 | VARCHAR2 | Y/N |
```

### 步骤5：生成索引文件

最后生成 00_表索引.md：
```markdown
# 数据库字典表索引

共 XXX 张表

| 表名 | 表描述 |
| :--- | :--- |
| [表名](tables/表名.md) | 表描述 |
```

**注意**：每次更新字典文件后都需要重新生成索引。

## 关键路径

- 数据库配置：`项目根目录/.env`
- 字典输出目录：`docs/dictionaries/tables/`
- 索引文件：`docs/dictionaries/00_表索引.md`

## 注意事项

1. **组织ID**：不同项目的 ORGANIZATIONID 可能不同（如东成是 'DONGCHENG'，其他可能是 'ND'）

2. **Oracle LONG 类型问题**：
   - `user_col_comments.comments` 是 LONG 类型，无法在 SQL 中使用 NVL、字符串拼接
   - `user_tab_columns.data_default` 也是 LONG 类型
   - 必须使用 PL/SQL 游标处理，参考步骤3的脚本

3. **分隔符格式**：导出 SQL 结果时使用 `||'|'||` 分隔符格式，避免固定列宽解析问题

4. **字符编码**：确保 SQL*Plus 输出编码为 UTF-8

5. **文件命名**：生成的 .md 文件名需要清理 Windows 文件名非法字符（`<>:"/\|?*`）

6. **两种方式的区别**：
   - BSM_DATA_DICTIONARY_FIELD：包含完整字段信息（自定义描述、备注、主键标记、默认值）
   - COMMENT ON：包含字段描述、字段类型、允许为空，无默认值和主键信息
