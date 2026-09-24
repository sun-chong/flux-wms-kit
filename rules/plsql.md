---
paths:
  - "**/*.sql"
---
# PL/SQL 开发规范

## PLJSON 库

项目包含完整的 PLJSON 库（位于 `body/PLJSON*.sql`），用于 Oracle PL/SQL 中的 JSON 处理：

- `pljson` - JSON对象操作
- `pljson_list` - JSON数组操作
- `pljson_parser` - JSON解析
- `pljson_helper` - 辅助函数（merge、join、equals等）

## 变量命名

- `V_*`：局部变量
- `IN_*`：入参
- `OUT_*`：出参
- `ITEM`：循环变量

## 存储过程与函数命名

### 命名规则

自定义的过程/函数：以 `SPUDF`（过程）或 `FNUDF`（函数）开头，后跟关键单据（例如，`ASN`, `SO`, `PO`, `TR`等），再跟逻辑名称（例如，`GET_ERRORMESSAGE`）

**使用 ddl-template skill 生成模板**

### 前缀列表

| 前缀        | 说明                          |
| ----------- | ----------------------------- |
| `SPUDF_`  | 自定义存储过程                |
| `FNUDF_`  | 自定义函数                    |
| `SP_`     | 标准存储过程                  |
| `SP_PLS_` | LES 子系统存储过程            |
| `PLS_`    | PLS 触发器/LES 子系统存储过程 |

## 数据库表命名

- `DOC_` - 单据表（ASN、订单、波次等）
- `BAS_` - 基础数据表（SKU、客户、库位等）
- `ACT_` - 业务活动表（分配、库存交易等）
- `INV_` - 库存表
- `RUL_` - 规则表
- `SYS_` - 系统表
- `TMP_` - 临时表
- `CUS_` - 自定义业务表（客户波次、标签等）
- `UDF_` - 用户自定义字段扩展表
- `PLS_` - LES 子系统专用表
- `SRM_` - SRM 相关表

## 重要临时表

- `TMP_CODE`：Oracle事务级临时表（ON COMMIT DELETE ROWS），用于处理长入参存储过程。先将数据批量插入TMP_CODE表，再在存储过程中查询获取，避免单个存储过程入参过多和IN查询性能问题。
- 标识符使用 `SYS_GUID()` 生成，不要用时间戳拼接
- 无需主动删除，事务结束自动清理

## 通用字段

- 标准审计字段：`ADDWHO`, `ADDTIME`, `EDITWHO`, `EDITTIME`, `NOTETEXT`, `CURRENTVERSION`, `OPRSEQFLAG`
- 多组织/仓库：`ORGANIZATIONID`, `WAREHOUSEID`
- 扩展字段：`dedi01-dedi10`, `hedi01-hedi20`, `UDF01-UDF06`
- 动态批次属性：`LOTATT01-LOTATT24`，具体配置说明可查阅 `BAS_LOTID_DETAILS` 表

## 空值判断

### Oracle NULL 语义

- Oracle 中空字符串 `''` 等同于 `NULL`（与其他数据库不同）
- `NULL || 字符串` 结果为 `NULL`，拼接前必须用 `NVL` 处理
- `LENGTH(NULL)` 返回 `NULL` 而非 `0`，数值比较时需 `NVL(LENGTH(...),0)`
- 算术运算和字符串操作前必须用 `NVL(col, default)` 包裹

### 常用模式

- 文本字段：`NVL(V_FIELD,'*')='*'`，使用 `'*'` 作为备用值
- 数量字段：`NVL(V_QTY,0)<=0`
- `LOTATT` 字段和 `TRACEID` 必须使用 `NVL(字段,'*')='*'` 判断

## 库存占用校验

- 硬占用判断：`QTYALLOCATED+QTYONHOLD+QTYRPOUT+QTYMVOUT>0`
- 软锁定校验：转移单（TDOCLINESTATUS='03'）、调整单（ADJLINESTATUS='03' AND QTY>TOQTY）

## SQL语句格式

- 本数据库版本是 Oracle Database 11g，不支持 `FETCH FIRST N ROWS ONLY`，必须使用 `ROWNUM <= N`
  ```sql
  -- ❌ 错误（12c+ 语法）
  SELECT * FROM DOC_ORDER_HEADER WHERE ROWNUM <= 10 ORDER BY ADDTIME DESC;
  -- ✅ 正确（11g 兼容，子查询先排序再取行）
  SELECT * FROM (
      SELECT * FROM DOC_ORDER_HEADER ORDER BY ADDTIME DESC
  ) WHERE ROWNUM <= 10;
  ```
- 禁止使用 `GOTO` 语法，任何场景均不允许出现
- 禁止使用游标写法，对于批量数据的处理总是使用 `FOR` 循环结构
- 避免出现 N+1 查询模式
- JOIN的ON条件：第二个表别名条件写在前面
- 部分别名习惯：`DOC_ORDER_HEADER` 别名为 `H`，`ACT_TRANSACTION_LOG` 别名为 `T`，`ACT_ALLOCATION_DETAILS` 别名为 `AD`，`BAS_SKU` 别名为 `BS` 等
- 在查询中优先使用 `DECODE` 函数代替 `CASE` 语句，非查询语句不能代替
- 不要使用 `<>`，用 `!=` 代替
- 确保在需要时正确的处理 `CLOB` 类型和 `VARCHAR2` 类型的转换
- 子查询存在性检查必须使用 `EXISTS` / `NOT EXISTS`，禁止使用 `IN` / `NOT IN`（避免 NULL 导致的逻辑陷阱）
- 使用 `LISTAGG` 时必须防范溢出（VARCHAR2 上限 4000 字节）：拼接前校验字符串总长度，或拆分为多次聚合
- 动态 SQL 拼接时采用分段拼接法：
  - 每行一个条件，使用 `' || '` 连接
  - 固定值用 `''值''` 格式；变量用 `'''||变量名||'''` 格式

## 异常处理

### 返回码规范

- 存储过程成功返回：`OUT_CODE := '000#'`
- 存储过程失败返回：`OUT_CODE := '999#'||友好错误信息||关键参数信息`

### 项目异常模板

```sql
BEGIN
    [逻辑代码]
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        OUT_CODE := '999#根据转移单号：'||IN_TDOCNO||'和行号：'||IN_TDOCLINENO||'未获取到对应的转移单明细信息';
        ROLLBACK;
        RETURN;
    WHEN TOO_MANY_ROWS THEN
        OUT_CODE := '999#根据转移单号：'||IN_TDOCNO||'和行号：'||IN_TDOCLINENO||'获取到了多条信息，数据存在异常';
        ROLLBACK;
        RETURN;
    WHEN OTHERS THEN
        OUT_CODE := '999#获取转移单明细信息出现异常: '||SQLERRM||DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        ROLLBACK;
        RETURN;
END;
```

### 异常处理规则

- 单条数据查询必须使用 `BEGIN EXCEPTION` 包裹
- **每个 PL/SQL 块必须包含 `WHEN OTHERS THEN` 异常处理**，捕获未预期的错误并返回友好信息
- 单表主键查询、有 `ROWNUM=1` 的情况不需判断 `TOO_MANY_ROWS`
- 避免重复查询：直接查询用 EXCEPTION 处理，而非先 COUNT 再查值
- **禁止 `WHEN OTHERS THEN NULL`** — 静默吞掉所有异常是最危险的反模式

### 双捕获模式

> 参考：`.claude/skills/db/plsql/plsql-error-handling.md`（11g 完全兼容）

- `WHEN OTHERS` 中同时使用 `FORMAT_ERROR_STACK` + `FORMAT_ERROR_BACKTRACE`
- `SQLERRM` 最大 512 字节会截断；`FORMAT_ERROR_STACK` 最大 2000 字节
- `FORMAT_ERROR_BACKTRACE` 提供精确错误行号（10g+ 可用）

| 函数 | 最大长度 | 行号 | 推荐用途 |
|------|---------|------|---------|
| `SQLERRM` | 512 字节 | ❌ | 仅简单日志 |
| `FORMAT_ERROR_STACK` | 2000 字节 | ❌ | 完整错误信息 |
| `FORMAT_ERROR_BACKTRACE` | 可变 | ✅ | 定位错误源行号 |

### 共享异常包

- 常用 `PRAGMA EXCEPTION_INIT` 声明集中在共享包中，避免在每个包体中重复声明

### 自主事务错误日志

- 高风险操作使用 `PRAGMA AUTONOMOUS_TRANSACTION` 记录错误日志
- 确保主事务回滚后日志仍然保留

## 注释

- 注释规范由 `ddl-template` skill 提供，使用该工具生成模板时会自动包含注释模板
- 自定义函数必须有文档注释头（作者/日期/功能描述/CHANGE LOG，格式见 ddl-template 模板）

## 通用约定

- 所有表使用复合主键：`(ORGANIZATIONID, WAREHOUSEID, ...)`

## Oracle 开发经验

- 审计字段完整性：INSERT 语句必须同时写入 `ADDWHO`, `ADDTIME`, `EDITWHO`, `EDITTIME`
- 文件命名规则：所有新建表的 SQL 文件、所有优化后的存储过程 SQL 文件，文件名都必须使用大写

## 批量处理最佳实践

> 参考：`.claude/skills/db/plsql/plsql-performance.md`（19c 基线，以下特性均为 11g 可用）

### BULK COLLECT + LIMIT

- 大批量查询必须使用 `BULK COLLECT` + `LIMIT` 分批，默认 100-500 行/批
- **禁止无 LIMIT 的 BULK COLLECT** — 会导致 PGA 内存溢出
- `FOR` 循环中的单行 DML 是主要性能瓶颈（每行一次上下文切换）

```sql
DECLARE
    TYPE t_data IS TABLE OF source_table%ROWTYPE;
    V_DATA t_data;
    V_BATCH_SIZE CONSTANT PLS_INTEGER := 500;
BEGIN
    LOOP
        SELECT col1, col2, col3
        BULK COLLECT INTO V_DATA
        FROM source_table
        WHERE condition
        LIMIT V_BATCH_SIZE;

        FORALL i IN 1..V_DATA.COUNT
            INSERT INTO target_table (col1, col2, col3)
            VALUES (V_DATA(i).col1, V_DATA(i).col2, V_DATA(i).col3);

        EXIT WHEN V_DATA.COUNT < V_BATCH_SIZE;
    END LOOP;
END;
```

### FORALL + SAVE EXCEPTIONS

- 批量 DML 使用 `SAVE EXCEPTIONS` 允许部分成功，避免单行失败导致整批回滚
- 异常时通过 `SQL%BULK_EXCEPTIONS` 获取失败行信息
- 需声明 `PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381)`

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1..V_DATA.COUNT SAVE EXCEPTIONS
        INSERT INTO target_table VALUES V_DATA(i);
EXCEPTION
    WHEN e_bulk_errors THEN
        FOR i IN 1..SQL%BULK_EXCEPTIONS.COUNT LOOP
            -- SQL%BULK_EXCEPTIONS(i).ERROR_INDEX: 失败的集合下标
            -- SQLERRM(-SQL%BULK_EXCEPTIONS(i).ERROR_CODE): 错误信息
            NULL;
        END LOOP;
END;
```

### NOCOPY 提示

- 大型 OUT 参数（集合类型）使用 `NOCOPY` 减少值拷贝开销
- 注意：异常时 OUT 参数不会回退到调用前的值

```sql
PROCEDURE process_data(OUT_DATA IN OUT NOCOPY collection_type) IS ...
```

## 安全编码

> 参考：`.claude/skills/db/plsql/plsql-security.md`（19c 基线，DBMS_ASSERT 为 10.2+ 可用，11g 完全支持）

### DBMS_ASSERT 防注入

- 动态 SQL 中的标识符（表名、列名）必须使用 `DBMS_ASSERT.SIMPLE_SQL_NAME` 验证
- Schema 名使用 `DBMS_ASSERT.SCHEMA_NAME` 验证
- 字符串字面量使用 `DBMS_ASSERT.ENQUOTE_LITERAL` 安全引用

| 函数 | 用途 | 异常 |
|------|------|------|
| `SIMPLE_SQL_NAME(str)` | 验证无特殊字符的 SQL 名称 | ORA-44003 |
| `SCHEMA_NAME(str)` | 验证且 schema 存在 | ORA-44001 |
| `SQL_OBJECT_NAME(str)` | 验证名称且对象存在 | ORA-44002 |
| `ENQUOTE_LITERAL(str)` | 安全引用字符串字面量 | — |

```sql
-- 动态 DDL 安全模式
DECLARE
    v_table VARCHAR2(128) := DBMS_ASSERT.SIMPLE_SQL_NAME(IN_TABLE_NAME);
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM all_tables
    WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA')
      AND table_name = v_table;
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE ' || v_table || ' ...';
    END IF;
END;
```
