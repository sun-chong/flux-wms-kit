---
name: flux-extconfig-gen
description: 根据存储过程参数声明生成标准业务扩展配置（BSM_STDBIZ_EXTCONFIG）。适用于前后置操作、定时器、RF端前置操作的注册。触发词：扩展配置、EXTCONFIG、前后置操作注册、定时器注册、RF端注册。
disable-model-invocation: true
---
# 标准业务扩展配置自动生成器

解析 Oracle 存储过程参数声明，生成并执行业务扩展配置 INSERT SQL，写入 `BSM_STDBIZ_EXTCONFIG` 和 `BSM_STDBIZ_EXTCONFIG_ML` 表。

## 工作流程

```
Step 1: 收集配置参数 → 用户提供场景/组织/仓库/功能编号/动作代码等，尽量一轮交互收齐
Step 2: 解析存储过程 → 查找 routine/ 下 .sql 文件，按 IN/OUT 声明解析参数
Step 3: 确认转换结果 → 展示参数对照表，请用户确认
Step 4: 生成 SQL 文件 → 用户确认 → 执行 INSERT → 成功验证 / 失败按 ORA 错误码分类处理
Step 5: 验证写入 → SELECT 查询确认数据正确
         [仅RF端] 执行完成后额外输出业务入参/出参拼接字符串
```

---

## Step 1：收集配置参数

**一条 `question` 收齐所有可独立确定的缺失字段，尽量减少交互轮次。** 先从用户消息提取已提供信息，仅对缺失字段提问。

- 若 SCENE 已知但 EXTENDTYPE 未提供：同一次 `question` 中追问 EXTENDTYPE（前后置场景下提供选项列表）
- 若 SCENE 也未知：`SCENE` 和 `EXTENDTYPE` 一起提问（SCENE 用选项，EXTENDTYPE 标注"待 SCENE 确定后自动/手动选择"）
- 定时器和 RF 端的 EXTENDTYPE 可自动确定，无需追问

### 参数总表

| 参数                   | 说明                         | 来源          | 必填 |
| :--------------------- | :-------------------------- | :------------ | :--: |
| 场景 (SCENE)           | 前后置 / 定时器 / RF端        | 用户提供/询问 |  是  |
| 组织编号 (ORGANIZATIONID) | 所属组织编码，不同项目不同   | **询问用户**  |  是  |
| 仓库编号 (WAREHOUSEID) | 所属仓库                      | 用户提供      |  是  |
| 功能编号 (FUNCTIONID)  | 关联的功能编号                 | 用户提供      |  是  |
| 扩展类型 (EXTENDTYPE)  | 见下方 EXTENDTYPE 取值规则     | 自动/询问     |  是  |
| 动作代码 (ACTIONCODE)  | 唯一标识                      | 用户提供      |  是  |
| 动作描述 (ACTIONDESCR) | 中文描述，不填则使用动作代码    | 用户提供      |  否  |
| 存储过程名 (SPNAME)    | 如 `SPUDF_XXX`                | 用户提供      |  是  |
| ADDWHO (操作人)        | 自动从上下文 `[作者署名]` 获取 | **自动**      |  -   |

> **关键**：
> - `ORGANIZATIONID` 必须从用户处收集，不可硬编码
> - `ADDWHO` 不向用户询问，自动使用项目约定的 `[作者署名]`（在 `CLAUDE.md` 中定义）

### 输入校验规则

收集参数后、使用前，执行以下校验：
- `ORGANIZATIONID` / `WAREHOUSEID` / `ACTIONCODE` / `SPNAME`：非空校验
- `ACTIONCODE`：建议长度不超过 30 字符（由数据库字段长度决定）
- 所有参数值通过绑定变量传入 SQL，无需手动转义（绑定变量自动处理特殊字符）

### EXTENDTYPE 取值规则

| 场景    | 扩展类型确定方式                                                  |                                    数据库码值                              |
| :------ | :-------------------------------------------------------------- | :-----------------------------------------------------------------------: |
| 前后置  | **询问用户**选择：前置操作/前置操作(事务内)/后置操作/后置操作(事务内) | `PREOPERATION` / `PREOPERATION_IN` / `POSTOPERATION` / `POSTOPERATION_IN` |
| 定时器  | **自动确定**为"定时器"，不询问                                     |                                     `TIMER`                               |
| RF端   | **自动确定**为"前置操作"，不询问                                    |                                 `PREOPERATION`                            |

> **关键约束**：可独立确定的缺失字段应通过**同一次** `question` 工具调用发出。已提供的信息绝不重复提问。仅当 EXTENDTYPE 依赖未知的 SCENE 时，允许分两轮收集。

---

## Step 2：解析存储过程参数

### 2.1 定位文件

使用 glob 搜索 `src/WMS_FTEST/routine/{SPNAME}.sql`。文件不存在则提示用户，列出相似文件名。

### 2.2 参数分类规则

**判断依据：`IN`/`OUT`/`IN OUT` 关键字声明，而非参数名前缀。**

```
对于每个参数声明：
1. 提取参数名（第一个单词）
2. 检查声明中的关键字：
   - 声明包含 "OUT"（即 OUT 或 IN OUT）→ 出参
   - 声明包含 "IN" 或无关键字 → 入参（Oracle 默认为 IN）
```

**示例：**
```sql
CREATE PROCEDURE DONGCHENG_SPBCD_SKU(
    IN_ORGANIZATIONID IN VARCHAR2,     -- 声明含 IN → 入参
    WAREHOUSEID       IN VARCHAR2,     -- 声明含 IN → 入参
    V_OPERATION       VARCHAR2,        -- 无关键字，默认 IN → 入参
    IN_USERID         IN VARCHAR2,     -- 声明含 IN → 入参
    O_SKU             IN OUT VARCHAR2, -- 声明含 OUT → 出参
    R_SERIALNO        IN OUT VARCHAR2, -- 声明含 OUT → 出参
    OUT_RETURN_CODE   OUT VARCHAR2     -- 声明含 OUT → 出参
)
```

> **注意**：参数名前缀（`IN_`、`OUT_`、`V_`、`O_` 等）仅为命名习惯，**不作为入参/出参的判断依据**。

> **IN OUT 参数处理**：声明含 `IN OUT` 的参数，统一按**出参**处理（匹配系统级 `%` 参数或转为 `%xxx`）。RF 端输出字符串中，IN OUT 参数归入**出参**类。

### 2.3 前缀去除与名称清洗规则

**两步处理：先去前缀，再清洗名称。**

**第一步：去除前缀**
```
参数名含 "_" → 去掉第一个 "_" 及之前部分（作为前缀丢弃）
参数名无 "_" → 保留原始参数名
```

**第二步：清洗名称**
```
在剩余部分中，去掉所有 "_" 和 "-" 符号，合并为连续字符串
```

**完整示例：**
```
  IN_ORGANIZATIONID  → ORGANIZATIONID   （去前缀 IN → 无特殊符号）
  OUT_RETURN_CODE    → RETURNCODE       （去前缀 OUT → 去掉 _ → RETURNCODE）
  V_BIZORGID         → BIZORGID         （去前缀 V → 无特殊符号）
  O_SKU              → SKU              （去前缀 O → 无特殊符号）
  IN_TO_LOCATION     → TOLOCATION       （去前缀 IN → 去掉 _ → TOLOCATION）
  IN_ASN-_NO         → ASNNO            （去前缀 IN → 去掉 _ 和 - → ASNNO）
  ERRORMSG           → ERRORMSG         （无前缀，无特殊符号）
  WAREHOUSEID        → WAREHOUSEID      （无前缀，无特殊符号）
```

**碰撞检测：** 如果两个不同原始参数经清洗后得到相同名称（如 `IN_ASNNO` 和 `IN_ASN_NO` 都变成 `ASNNO`），必须提示用户，要求手动指定别名以区分。碰撞属于异常情况，不应静默处理。**用户指定的别名将替代清洗后名称，参与后续的 camelCase 转换和 `$`/`%` 前缀拼接。**

**系统级参数碰撞：** 若两个不同原始参数经清洗后都匹配同一系统级参数（如 `IN_ORGANIZATIONID` 和 `V_ORGID` 都匹配 `@bizOrgId`），视为异常，直接报错终止，提示用户检查存储过程参数声明。

> **注意**：清洗后的名称用于后续的系统参数关键词匹配和 camelCase 转换。

### 2.4 系统级参数匹配规则

**基于清洗后的名称（无前缀、无 `_`/`-`）进行关键词语义匹配，忽略大小写。**

`@bizOrgId`、`@bizWarehouseId`、`@languageId`、`@userId`、`@bizWorkStation`、`@userName`、`%returnCode` 是系统固定的系统级参数。只要存储过程中存在符合条件的参数，就自动识别并转换。

匹配优先级从上到下，命中即停：

| 优先级 | 匹配条件（基于清洗后名称，忽略大小写） | 转换结果 |
| :----: | :------------------------------------- | :------- |
|   1    | 含 `WORKSTATION`                        | `@bizWorkStation` |
|   2    | 含 `USERNAME`                           | `@userName`       |
|   3    | 含 `USERID`                             | `@userId`         |
|   4    | 含 `LANGUAGE`                           | `@languageId`     |
|   5    | 含 `WAREHOUSE`                          | `@bizWarehouseId` |
|   6    | 含 `ORGANIZATION` 或 `ORGID`            | `@bizOrgId`       |
|   7    | 出参、存储过程最后一个参数、且（整体为 `CODE`，或以 `CODE` 结尾，或含 `RETURNCODE`） | `%returnCode` |

> **`%returnCode` 匹配精确说明**（基于清洗后名称）：
> - 必须是存储过程的最后一个参数（声明顺序末尾），否则即使关键词匹配也**不转换** ❌
> - 以 `CODE` 结尾（如 `ERRCODE`、`RESULTCODE`、`INVOICECODE`），且满足"最后一个参数"条件 → 匹配 ✅
> - `INVOICECOUNTRY`（CODE 嵌在 COUNTRY 中间，不以 CODE 结尾）→ **不匹配** ❌
> - 未被选为 `%returnCode` 的其他 CODE 相关出参，按普通业务出参规则转换（`%` 前缀 + camelCase）
>
> **多个候选时**：当优先级 7 有多个出参同时满足关键词条件时，取声明顺序中**最后一个**作为 `%returnCode`。

### 2.5 业务字段转换规则

**基于清洗后名称（无前缀、无 `_`/`-`）进行 camelCase 转换。**

由于清洗后名称已无分隔符，camelCase 转换需识别大写字母边界：
- 大写字母后跟小写字母 → 该大写字母是新词的开始
- 连续大写的最后一个字母（后面跟小写）→ 属于新词
- 全大写字符串 → 按可识别的英语单词边界拆分为多个词（如 `ASNNO` → `ASN` + `NO`，`TOLOCATION` → `TO` + `LOCATION`，`PROCESSBY` → `PROCESS` + `BY`）。常见可拆分词根：`TO`、`FROM`、`BY`、`NO`、`QTY`、`DATE`、`TYPE`、`NAME`、`CODE`、`MSG`、`LIST`、`FLAG`、`STATUS`、`COUNT`、`TRACE`、`LINE`、`ORDER`、`BATCH`、`SKU`、`ASN`、`SO`、`PO`、`TR`、`TEXT`、`TIME`、`KEY`、`ID`。无法识别边界时整体作为一个词

**入参**（非系统级参数）：
1. 清洗后名称 → 识别单词边界 → 全小写 → 首词以外每词首字母大写
2. 加前缀 `$`

**出参**（非系统级参数）：
1. 清洗后名称 → 识别单词边界 → 全小写 → 首词以外每词首字母大写
2. 加前缀 `%`

**示例：**

| 原始参数 | 清洗后名称 | camelCase | 最终结果 |
| :------- | :--------- | :-------- | :------- |
| `IN_ASNNO` | `ASNNO` | `asnNo` | `$asnNo` |
| `IN_PROCESSBY` | `PROCESSBY` | `processBy` | `$processBy` |
| `IN_TO_LOCATION` | `TOLOCATION` | `toLocation` | `$toLocation` |
| `IN_ASN-_NO` | `ASNNO` | `asnNo` | `$asnNo` |
| `IN_BIZWAREHOUSEID` | `BIZWAREHOUSEID` | `bizWarehouseId` | `$bizWarehouseId` |
| `OUT_ERR_MSG` | `ERRMSG` | `errMsg` | `%errMsg` |

> **确认表提示**：在 Step 3 的参数对照表中，如果某个参数的 camelCase 转换结果明显不理想（如全大写缩写未拆分、拆词结果不符合业务含义），应在"规则"列标注 `⚠️ 建议人工确认`，提醒用户重点检查。

### 2.6 参数排列顺序

**严格按存储过程声明顺序排列，不重排。**

UDFOPRSPPARAMS 格式：
- 每行一个参数，参数间用 `,` + 换行分隔
- 系统级参数（`@`、`%returnCode`）和业务参数（`$`、`%`）混排，保持声明顺序
- `%returnCode` 通常是最后一个参数（存储过程声明的最后一个出参）

> **零参数处理**：若存储过程无任何参数，视为异常，直接报错终止，提示用户检查存储过程是否正确。

---

## Step 3：展示转换结果并确认

生成参数转换对照表，展示给用户确认。格式：

| 原始参数              | 声明类型 | 转换后          | 规则          |
| :-------------------- | :------: | :-------------- | :------------ |
| `IN_ORGANIZATIONID`   |   IN     | `@bizOrgId`     | 系统级: 组织  |
| `IN_ASNNO`            |   IN     | `$asnNo`        | 业务字段 → $  |
| `OUT_CODE`            |   OUT    | `%returnCode`   | 系统级: 返回码|

UDFOPRSPPARAMS 按存储过程声明顺序排列：保持声明顺序，不重排，每行一个参数。

---

## Step 4：生成并执行 INSERT SQL

### 4.1 目标表字段赋值

#### BSM_STDBIZ_EXTCONFIG（主表）

| 字段                | 值                   | 说明                                    |
| :------------------ | :------------------- | :-------------------------------------- |
| `ORGANIZATIONID`    | 用户输入             | 不可硬编码，必须从 Step 1 收集          |
| `WAREHOUSEID`       | 用户输入             |                                         |
| `FUNCTIONID`        | 用户输入             |                                         |
| `ACTIONCODE`        | 用户输入             |                                         |
| `EXTENDTYPE`        | 场景对应码值         |                                         |
| `EXTENDLINENO`      | `'1'`                | 固定，行号从1开始                       |
| `EXECUTESEQUENCE`   | `100`                | 固定，数值越小越先执行                  |
| `ACTIVEFLAG`        | `'Y'`                | 固定                                    |
| `APPSRVID`          | `'C0001SRV'`         | 固定，数据库存储过程统一使用            |
| `UDFOPRTYPE`        | `'DBSP'`             | 固定，DBSP=数据库存储过程               |
| `UDFOPRSPNAME`      | 存储过程名           |                                         |
| `UDFOPRSPPARAMS`    | 参数字符串（含换行） | 见 4.2                                  |
| `SYSTEMFLAG`        | `'N'`                | 固定，N=自定义扩展                      |
| `SUBSYSTEM`         | `'WMS'`              | 固定                                    |
| `ADDWHO`            | `[作者署名]`         | 自动获取，在 `CLAUDE.md` 中定义           |
| `ADDTIME`           | `SYSDATE`            | 系统当前时间                            |
| `EDITWHO`           | `[作者署名]`         | 同 ADDWHO（审计字段完整性要求）         |
| `EDITTIME`          | `SYSDATE`            | 同 ADDTIME（审计字段完整性要求）        |
| 其他字段            | 不列出               | UDF01-UDF06、JSONDATA、NOTETEXT等均留空 |

#### BSM_STDBIZ_EXTCONFIG_ML（多语言表）

| 字段                | 值                                  | 说明           |
| :------------------ | :---------------------------------- | :------------- |
| `ORGANIZATIONID`    | 用户输入                            | 同主表         |
| `WAREHOUSEID`       | 用户输入                            |                |
| `FUNCTIONID`        | 用户输入                            |                |
| `ACTIONCODE`        | 用户输入                            |                |
| `EXTENDTYPE`        | 场景对应码值                        |                |
| `EXTENDLINENO`      | `'1'`                               |                |
| `LANGUAGEID`        | `'zh_CN'`                           | 固定，简体中文 |
| `ACTIONDESCR`       | 用户输入，为空则使用 `ACTIONCODE`   |                |
| `ADDWHO`            | `[作者署名]`                        | 同主表         |
| `ADDTIME`           | `SYSDATE`                           | 系统当前时间   |
| `EDITWHO`           | `[作者署名]`                        | 同 ADDWHO      |
| `EDITTIME`          | `SYSDATE`                           | 同 ADDTIME     |

> **注意**：`CURRENTVERSION` 和 `OPRSEQFLAG` 字段不显式 INSERT，依赖数据库默认值写入。审计字段（`ADDWHO`、`ADDTIME`、`EDITWHO`、`EDITTIME`）必须同时写入两个表。

### 4.2 参数值处理

UDFOPRSPPARAMS 是一个多行文本字段，每个参数占一行，参数间用逗号+换行分隔。

该值在 **Python 端构造为完整字符串**（包含实际的 `$` 字符和换行符 `\n`），通过绑定变量 `:p_params` 传入 INSERT 语句。Python oracledb 原生支持特殊字符，无需 CHR 函数转义。

**示例**：Python 中构造的字符串内容：
```
@bizOrgId,\n$asnNo,\n%returnCode
```

传入 params JSON：
```json
{
  "p_org": "DONGCHENG",
  "p_wh": "WH01",
  "p_func": "FUNC01",
  "p_act": "PUTAWAY_SP",
  "p_ext": "PREOPERATION",
  "p_spname": "SPUDF_ASN_PUTAWAY",
  "p_params": "@bizOrgId,\n$asnNo,\n%returnCode",
  "p_user": "<自动获取[作者署名]>",  // 从 CLAUDE.md 的 [作者署名] 获取，不硬编码
  "p_actiondescr": "上架前置操作"
}
```

> **规则**：参数间用 `,` + `\n` 分隔，最后一个参数后不加 `,`。

### 4.3 INSERT 语句与执行流程

**重要：所有数据库操作（INSERT、验证查询）统一通过 Python oracledb 脚本执行，使用绑定变量避免 SQL 注入。**

**执行脚本位置**：`.agents/skills/flux-extconfig-gen/scripts/oracle_insert.py`

**脚本能力**：
- 读取 UTF-8 SQL 文件 → Python oracledb thick mode 执行（自动清理末尾 `/` 终止符）
- `--params PARAMS` 参数：绑定变量，支持 JSON 字符串或 JSON 文件路径
- `--query "SQL"` 参数：直接执行 SELECT 查询并输出结果（用于验证和错误诊断）
- 异常时自动回滚

**绑定变量规范**：SQL 模板中的动态值使用 `:p_org`、`:p_wh` 等命名占位符，实际值通过 `--params` 传入。参数名统一使用 `p_` 前缀 + 小写简称，与 JSON 键名一一对应。

UDFOPRSPPARAMS 的值在 Python 端构造为完整字符串（包含 `$` 前缀和换行符），作为绑定变量 `:p_params` 传入。参见 4.2 的构造说明。

**事务控制：** 两条 INSERT 语句放在同一个 PL/SQL 匿名块中执行，确保主表和多语言表同时写入。事务的 COMMIT/ROLLBACK **由 Python 脚本端控制**（oracle_insert.py 的 `conn.commit()` / `conn.rollback()`），PL/SQL 匿名块内不包含 COMMIT 或 EXCEPTION 块，避免双重提交导致 Python 端回滚失效。使用绑定变量接收所有动态值：

```sql
BEGIN
  INSERT INTO BSM_STDBIZ_EXTCONFIG (
    ORGANIZATIONID, WAREHOUSEID, FUNCTIONID, ACTIONCODE, EXTENDTYPE,
    EXTENDLINENO, EXECUTESEQUENCE, ACTIVEFLAG, APPSRVID, UDFOPRTYPE,
    UDFOPRSPNAME, UDFOPRSPPARAMS, SYSTEMFLAG, SUBSYSTEM,
    ADDWHO, ADDTIME, EDITWHO, EDITTIME
  ) VALUES (
    :p_org, :p_wh, :p_func, :p_act, :p_ext,
    '1', 100, 'Y', 'C0001SRV', 'DBSP',
    :p_spname, :p_params, 'N', 'WMS',
    :p_user, SYSDATE, :p_user, SYSDATE
  );

  INSERT INTO BSM_STDBIZ_EXTCONFIG_ML (
    ORGANIZATIONID, WAREHOUSEID, FUNCTIONID, ACTIONCODE, EXTENDTYPE,
    EXTENDLINENO, LANGUAGEID, ACTIONDESCR,
    ADDWHO, ADDTIME, EDITWHO, EDITTIME
  ) VALUES (
    :p_org, :p_wh, :p_func, :p_act, :p_ext,
    '1', 'zh_CN', :p_actiondescr,
    :p_user, SYSDATE, :p_user, SYSDATE
  );
END;
```

覆盖模式的匿名块结构（DELETE + INSERT）：

```sql
BEGIN
  DELETE FROM BSM_STDBIZ_EXTCONFIG WHERE ORGANIZATIONID=:p_org AND WAREHOUSEID=:p_wh
    AND FUNCTIONID=:p_func AND ACTIONCODE=:p_act AND EXTENDTYPE=:p_ext AND EXTENDLINENO='1';
  DELETE FROM BSM_STDBIZ_EXTCONFIG_ML WHERE ORGANIZATIONID=:p_org AND WAREHOUSEID=:p_wh
    AND FUNCTIONID=:p_func AND ACTIONCODE=:p_act AND EXTENDTYPE=:p_ext AND EXTENDLINENO='1' AND LANGUAGEID='zh_CN';
  INSERT INTO BSM_STDBIZ_EXTCONFIG (...) VALUES (...);
  INSERT INTO BSM_STDBIZ_EXTCONFIG_ML (...) VALUES (...);
END;
```

**执行流程：**

1. 根据 Step 2 的转换结果和 Step 1 的配置参数，生成：
   - **SQL 模板文件** `outputs/TMP_EXTCONFIG_INSERT_{timestamp}.sql`：包含上述 PL/SQL 匿名块，动态值使用 `:p_xxx` 占位。`{timestamp}` 取当前时间 `HHmmss` 格式（如 `143022`），防止并发会话互相覆盖
   - **参数文件** `outputs/TMP_EXTCONFIG_PARAMS_{timestamp}.json`：包含所有绑定变量的实际值，时间戳与 SQL 文件一致
2. **展示完整 SQL（将参数值代入模板后展示）→ 用户确认**
3. **用户确认后**，通过 Python 脚本执行：

```bash
cd "项目根目录"; python .agents/skills/flux-extconfig-gen/scripts/oracle_insert.py outputs/TMP_EXTCONFIG_INSERT_{timestamp}.sql --params outputs/TMP_EXTCONFIG_PARAMS_{timestamp}.json
```

4. **根据执行结果分支**：

**成功（退出码 0）**：
- stderr 输出 `SQL 执行成功`
- 用验证查询确认行数（见 Step 5）
- 继续处理下一张表

**失败（退出码 1）**：
- stderr 输出包含 ORA 错误代码和消息
- 按 ORA 错误码分类处理（见下方 **ORA 错误码快速参考**）

5. **无论成功或失败，都删除临时文件**：
   - `rm -f outputs/TMP_EXTCONFIG_INSERT_{timestamp}.sql`
   - `rm -f outputs/TMP_EXTCONFIG_PARAMS_{timestamp}.json`
6. 将 SQL 语句（参数代入后的完整版本）打印到总结中，向用户展示

> **安全规则**：INSERT 语句执行前**必须**获得用户确认，禁止自主执行。

### 4.4 ORA 错误码快速参考

INSERT 失败时，从 stderr 的 Oracle 错误消息中提取 ORA 代码，按下表分类处理：

| ORA 代码 | 含义 | 用户提示 | 后续动作 |
| :------: | :--- | :------- | :------- |
| ORA-00001 | 主键/唯一约束冲突 | "目标表已有相同键值的记录" | 验证查询获取冲突记录 → 展示给用户 → 询问"覆盖/取消"。覆盖则生成 DELETE+INSERT 匿名块重新执行 |
| ORA-12899 | 字段值超过列宽 | "字段 X 的值 Y 超过列宽 Z"（从错误消息解析） | 停止，等用户缩短值后重试 |
| ORA-01400 | NOT NULL 约束违反 | "INSERT 缺少必填字段 X"（从错误消息解析） | 停止，等用户提供缺失值 |
| ORA-01722 | 无效数字 | "字段 X 的值格式错误（期望数字）"（从错误消息解析） | 停止，等用户修正格式 |
| ORA-01438 | 数值精度溢出 | "字段 X 的值超出允许范围"（从错误消息解析） | 停止，等用户修正数值 |
| ORA-02291 | 外键约束违反（父键不存在） | "字段 X 引用的值在父表中不存在"（从错误消息解析） | 停止，等用户检查关联数据 |
| ORA-02292 | 子记录存在 | "目标记录被子表引用，无法删除"（仅覆盖模式 DELETE 时） | 停止，等用户处理子记录 |
| 其他 ORA | 其他数据库错误 | 展示完整错误消息 | 停止，等用户分析 |
| 非 ORA | Python 异常 | "执行失败: {错误消息}" | 停止，等用户检查环境 |

**错误消息解析示例**：
```
ORA-12899: value too large for column "WMS"."BSM_STDBIZ_EXTCONFIG"."ACTIONCODE" (actual: 40, maximum: 30)
→ 提示："字段 ACTIONCODE 的值长度 40 超过列宽 30"

ORA-00001: unique constraint (WMS.PK_BSM_STDBIZ_EXTCONFIG) violated
→ 提示："主键冲突：约束 PK_BSM_STDBIZ_EXTCONFIG，目标表已有相同键值的记录"
```

---

## Step 5：验证写入

INSERT 成功后，通过验证查询确认数据已正确写入（使用绑定变量）：

```bash
python .agents/skills/flux-extconfig-gen/scripts/oracle_insert.py --query "SELECT COUNT(*) AS CNT FROM BSM_STDBIZ_EXTCONFIG WHERE ORGANIZATIONID=:p_org AND WAREHOUSEID=:p_wh AND FUNCTIONID=:p_func AND ACTIONCODE=:p_act AND EXTENDTYPE=:p_ext AND EXTENDLINENO='1'" --params '{"p_org":"...","p_wh":"...","p_func":"...","p_act":"...","p_ext":"..."}'
```

> CNT > 0 表示写入成功，继续处理下一张表。CNT = 0 表示数据未写入，需排查原因。

---

## RF端特有输出

仅当场景为 RF端 时，执行完成后额外输出参数字符串（**不写入数据库**）：

```
入参字符串: {用户入参1},{用户入参2},...
出参字符串: {用户出参1},{用户出参2},...
```

输出仅包含 `$` 前缀的用户入参和 `%` 前缀中排除 `%returnCode` 的用户出参。参数名去掉前缀后用 `,` 拼接，按声明顺序排列。

**示例：**
```
入参字符串: asnNo,asnLineNo,toLocation
出参字符串: newTraceId,returnLotnum
```

---

## 错误处理

| 场景               | 处理方式                                                      |
| :----------------- | :------------------------------------------------------------ |
| 存储过程文件不存在 | 提示用户，列出 `routine/` 下相似文件名                       |
| 参数声明格式异常   | 提示解析失败，展示原始声明让用户手动指定每个参数的入参/出参分类 |
| INSERT 执行失败    | 按 4.4 ORA 错误码分类处理，向用户展示错误信息和后续建议       |
| 零参数处理         | 视为异常，报错终止                                            |

## 安全与约束

### 允许

- 读取存储过程 `.sql` 源文件
- 生成 INSERT SQL 并通过 Python oracledb 脚本（`scripts/oracle_insert.py`）执行，使用绑定变量避免注入
- 数据写入、验证查询全部通过 Python oracledb 脚本（`scripts/oracle_insert.py`）执行
- INSERT 失败时按 ORA 错误码分类处理，向用户展示错误详情和后续建议

### 禁止

- 使用 SQLcl 或 connect-oracle 执行任何数据库操作（全部通过 Python oracledb，避免编码和引号转义问题）
- 修改存储过程源文件
- 在 `src/` 目录下创建任何文件
- 未经用户确认执行 INSERT/UPDATE/DELETE（**安全规则**）
- 修改已有扩展配置数据（除非用户确认覆盖）

### SQL 生成规范

- SQL 文件必须使用绑定变量 `:p_org`、`:p_wh` 等作为占位符，禁止硬编码业务值
- 日期值使用 TO_DATE 函数包装：`TO_DATE(:p_date, 'YYYY-MM-DD HH24:MI:SS')`
- 参数名统一使用 `p_` 前缀 + 小写简称，与 JSON 参数文件中的键名一一对应
- 每张表的参数分组放在 params JSON 的对应节中
- JSON 数值类型字段值：在 params 文件中直接写数值（不加引号），让 oracledb 正确推断绑定类型
- `--query` 的 SQL 必须使用相同的绑定变量名称，脚本会从 `--params` 中过滤匹配
