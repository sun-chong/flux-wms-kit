---
name: ddl-template
description: Oracle DDL 模板生成器。自动生成符合 Oracle 规范的存储过程、函数和建表 DDL。必须使用此 Skill 当：用户或 Agent 需要创建新的存储过程（CREATE PROCEDURE）、创建函数（CREATE FUNCTION）、创建表（CREATE TABLE），或提到 SPUDF、FNUDF、UDF_ 等命名规范时。也必须在规划新建存储过程、规划新建表、设计数据库对象方案、使用 writing-plans 制定包含数据库对象的实施计划时调用。
user-invocable: false
---

# Oracle DDL 模板生成器

本 Skill 用于生成 Oracle 数据库对象的模板代码，包括存储过程、函数和表创建。

## 触发场景

- 用户或 Agent 需要创建新的存储过程
- 用户或 Agent 需要创建新的函数
- 用户或 Agent 需要创建新的表
- 提到 SPUDF、FNUDF、UDF_* 等命名规范
- 请求 DDL 模板、模板代码

## 变量命名规范

- `IN_*`：入参
- `OUT_*`：出参
- `V_*`：局部变量
- `ITEM`：循环变量

## 空值判断规范

- 文本字段：`NVL(V_FIELD,'*')='*'`，使用 '*' 作为备用字段值
- 数量字段：`NVL(V_QTY,0)<=0`
- LOTATT 字段和 TRACEID 必须使用 `NVL(字段,'*')='*'` 判断

---

## 模板库

### 1. 存储过程模板（CREATE OR REPLACE）

```sql
CREATE OR REPLACE PROCEDURE SPUDF_业务标识_功能名称(
    IN_PARAM1 IN VARCHAR2,
    IN_PARAM2 IN VARCHAR2,

    IN_USERID IN VARCHAR2,
    OUT_CODE OUT VARCHAR2
)
IS
    /*
    ******************************************************************
    作者：		[使用 CLAUDE_CODE_AUTHOR 环境变量，未配置则使用 Git 用户名缩写]
    日期：		[YYYY/MM/DD 格式的当前日期]
    功能描述：	[简要说明存储过程的功能]
    ******************************************************************
    *							CHANGE LOG							 *
    ******************************************************************
    DATE		CR/EN NO.		PROGRAMMER		DESCR
    ------------------------------------------------------------------
    [YYYY/MM/DD]  V1.0        [作者署名]            初始版本
    ******************************************************************
    */

BEGIN

    -- 业务逻辑实现

    OUT_CODE := '000#';

EXCEPTION
    WHEN OTHERS THEN
        OUT_CODE := '999#'||SQLERRM||DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        ROLLBACK;
END;
/
```

### 2. 函数模板（CREATE OR REPLACE）

```sql
CREATE OR REPLACE FUNCTION FNUDF_业务标识_功能名称(
    IN_PARAM1 IN VARCHAR2,
    IN_PARAM2 IN VARCHAR2
) RETURN VARCHAR2
IS
    /*
    ******************************************************************
    作者：		[使用 CLAUDE_CODE_AUTHOR 环境变量，未配置则使用 Git 用户名缩写]
    日期：		[YYYY/MM/DD 格式的当前日期]
    功能描述：	[简要说明函数的功能]
    ******************************************************************
    *							CHANGE LOG							 *
    ******************************************************************
    DATE		CR/EN NO.		PROGRAMMER		DESCR
    ------------------------------------------------------------------
    [YYYY/MM/DD]  V1.0        [作者署名]            初始版本
    ******************************************************************
    */

BEGIN

    -- 业务逻辑实现

    RETURN '返回值';

END;
/
```

### 3. 建表模板（CREATE TABLE）

> 建表规范：
> - 自定义表使用 `UDF_*` 前缀
> - 数量字段使用 `NUMBER(18,8)`
> - 扩展字段：`UDF01-UDF06`

```sql
CREATE TABLE UDF_表名
(
    ORGANIZATIONID VARCHAR2(20)                  NOT NULL,
    WAREHOUSEID    VARCHAR2(20)                  NOT NULL,
    -- 业务字段（主键字段必须加 NOT NULL）
    [主键字段]     [数据类型]                     NOT NULL,
    [其他字段]     [数据类型],
    -- 数量字段示例：QTY NUMBER(18,8)
    -- 审计字段
    ACTIVEFLAG     VARCHAR2(1)  DEFAULT 'Y'      NOT NULL,
    UDF01          VARCHAR2(500),
    UDF02          VARCHAR2(500),
    UDF03          VARCHAR2(500),
    UDF04          VARCHAR2(500),
    UDF05          VARCHAR2(500),
    UDF06          VARCHAR2(500),
    NOTETEXT       CLOB,
    CURRENTVERSION NUMBER       DEFAULT 100      NOT NULL,
    OPRSEQFLAG     VARCHAR2(65) DEFAULT '2026' NOT NULL,
    ADDWHO         VARCHAR2(40),
    ADDTIME        DATE,
    EDITWHO        VARCHAR2(40),
    EDITTIME       DATE,
    PRIMARY KEY (ORGANIZATIONID, WAREHOUSEID, [主键字段])
)
/
```

### 使用说明

1. **选择模板类型**：根据需要创建的对象类型选择对应模板
2. **替换占位符**：
   - `SPUDF_业务标识_功能名称`：替换为实际的存储过程名称
   - `IN_PARAM1, IN_PARAM2`：替换为实际的参数名称和类型
   - `[作者署名]`：替换为作者姓名缩写
   - `[YYYY/MM/DD]`：替换为当前日期
   - `[功能描述]`：简要说明功能
3. **添加业务逻辑**：在 BEGIN 和 EXCEPTION 之间编写实际业务逻辑

## 批量数据处理

对于批量数据的处理，使用 FOR 循环结构，不使用游标：

```sql
FOR ITEM IN (
    SELECT COL1, COL2
    FROM SOME_TABLE
    WHERE CONDITION = 'VALUE'
) LOOP
    -- 处理每条记录
    V_RESULT := ITEM.COL1 || ITEM.COL2;
END LOOP;
```

## 注释规范

```sql
    /*
    ******************************************************************
    作者：		[作者]
    日期：		[YYYY/MM/DD]
    功能描述：	[简要说明]
    ******************************************************************
    *							CHANGE LOG							 *
    ******************************************************************
    DATE		CR/EN NO.		PROGRAMMER		DESCR
    ------------------------------------------------------------------
    [YYYY/MM/DD]  V1.0        [作者]            [描述]
    ******************************************************************
    */
```

## 相关 Skill

- **sp-parser**：语法检查存储过程
- **connect-oracle**：连接 Oracle 数据库执行 SQL