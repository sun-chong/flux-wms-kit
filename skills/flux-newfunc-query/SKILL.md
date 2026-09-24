---
name: flux-newfunc-query
description: |
  FLUX 新增功能与按钮权限查询。根据用户指定的日期，查询 WMS 系统中该日期之后新增的菜单功能和按钮权限，输出为树形结构文本。触发词：新增功能、新功能查询、新增菜单、新按钮查询、flux-newfunc。
  支持 `/flux-newfunc-query 2026-04-10` 直接传入日期，未传入日期时询问用户。
disable-model-invocation: true
---

# FLUX 新增功能与按钮权限树形查询

根据用户指定的日期，连接 Oracle 数据库查询 `BSM_FUNCTION`（功能菜单）和 `BSM_FUNCTION_ACTION`（按钮权限）表中该日期之后新增的记录，将功能和按钮按父子关系组织为树形结构，仅展示中文名称，输出为 `.txt` 文件保存到 `outputs/` 目录。

## 工作流程

> **核心约束：Step 2 到 Step 5 必须一口气连续执行，不得在中途任何步骤停下来询问用户或等待确认。** 三个 SQL 查询（功能 + 功能补全 + 按钮）应并行执行节省时间，查询结果返回后使用 Python 组装树形结构并写入文件。全流程只有一个交互点：Step 1 缺失日期时询问用户。

```
Step 1: 获取日期参数 → 若用户已传入则直接使用，否则询问
Step 2: 并行执行 SQL 查询（功能 + 全量按钮）
Step 3: 用 Python 筛选、组装树形结构
Step 4: 写入 outputs/ 目录的 txt 文件
Step 5: 告知用户文件路径，展示结果摘要
```

---

## Step 1：获取日期参数

从用户消息中提取日期。支持以下格式：
- `/flux-newfunc-query 2026-04-10` — 从 args 直接提取
- "查询2026-04-10之后的新增功能" — 从自然语言提取
- 未提供 → 使用 AskUserQuestion 询问一个日期（YYYY-MM-DD 格式）

提取到日期后，用 `TO_DATE('{date}', 'YYYY-MM-DD')` 在 SQL 中作为过滤起点。

---

## Step 2：查询功能与按钮（核心变更）

### 2.1 获取数据库连接

从项目根目录 `.env` 读取 `DB_CONNECTION`（Bash 中加载：`DB_CONNECTION=$(grep '^DB_CONNECTION=' .env | head -1 | cut -d'=' -f2- | tr -d '\r')`）。

### 2.2 三个并行查询

#### 查询 A：功能集（新增功能 + 有新增按钮的功能 + 祖先链）

使用 Bash + SQLcl heredoc 方式执行，将 `{DATE}` 替换为用户输入的日期：

```sql
SET PAGESIZE 0
SET FEEDBACK OFF
SET HEADING OFF
SET TAB OFF

SELECT f.functionId || '|' || f.parentFunctionId || '|' || COALESCE(ml.udfFunctionDescr, ml.functionDescr)
FROM BSM_FUNCTION f
LEFT JOIN BSM_FUNCTION_ML ml 
    ON ml.organizationId = f.organizationId AND ml.functionId = f.functionId AND ml.languageId = 'zh_CN'
WHERE f.organizationId = 'DONGCHENG'
  AND f.functionType IN ('M01','M02','M03','M04')
  AND f.subSystem IN ('SEC','WMS','RF','TMS','OCP','DATAHUB')
  AND f.functionId != 'TMSAPP'
  AND f.activeFlag = 'Y'
  AND (f.functionId IN (
    -- 原逻辑：新增功能 + 向上遍历祖先链
    SELECT functionId FROM BSM_FUNCTION
    WHERE organizationId = 'DONGCHENG'
    START WITH functionId IN (
        SELECT functionId FROM BSM_FUNCTION 
        WHERE organizationId = 'DONGCHENG'
          AND addTime >= TO_DATE('{DATE}', 'YYYY-MM-DD')
          AND functionType IN ('M01','M02','M03','M04')
          AND subSystem IN ('SEC','WMS','RF','TMS','OCP','DATAHUB')
          AND activeFlag = 'Y'
    )
    CONNECT BY PRIOR parentFunctionId = functionId
  )
  OR f.functionId IN (
    -- 新逻辑：有新增按钮但自身不新的功能 + 向上遍历祖先链
    SELECT functionId FROM BSM_FUNCTION
    WHERE organizationId = 'DONGCHENG'
    START WITH functionId IN (
        SELECT DISTINCT a.functionId FROM BSM_FUNCTION_ACTION a
        WHERE a.organizationId = 'DONGCHENG'
          AND a.activeFlag = 'Y'
          AND a.addTime >= TO_DATE('{DATE}', 'YYYY-MM-DD')
          AND a.functionId NOT IN (
            SELECT functionId FROM BSM_FUNCTION
            WHERE organizationId = 'DONGCHENG'
            START WITH functionId IN (
                SELECT functionId FROM BSM_FUNCTION 
                WHERE organizationId = 'DONGCHENG'
                  AND addTime >= TO_DATE('{DATE}', 'YYYY-MM-DD')
                  AND functionType IN ('M01','M02','M03','M04')
                  AND subSystem IN ('SEC','WMS','RF','TMS','OCP','DATAHUB')
                  AND activeFlag = 'Y'
            )
            CONNECT BY PRIOR parentFunctionId = functionId
          )
    )
    CONNECT BY PRIOR parentFunctionId = functionId
  ))
ORDER BY f.functionLevel, f.parentFunctionId, f.showSequence, f.functionId;
```

**变更说明**：原查询只覆盖"新增功能 + 祖先链"，遗漏了"有新增按钮但自身不旧"的功能（如 A3001 发运订单、A3012 波次计划）。新查询 UNION 了第二个 CONNECT BY，以有新增按钮的功能为起点向上遍历。

#### 查询 B：功能附加 addTime（用于判断功能是否新）

```sql
SET PAGESIZE 0
SET FEEDBACK OFF
SET HEADING OFF
SET TAB OFF

SELECT f.functionId || '|' || TO_CHAR(f.addTime, 'YYYY-MM-DD')
FROM BSM_FUNCTION f
WHERE f.organizationId = 'DONGCHENG'
  AND f.activeFlag = 'Y'
  AND f.functionId IN (
    -- 复用查询 A 的 WHERE 条件，替换为 functionId 列表
    -- （在实际实现中，直接基于查询 A 结果取 functionId 列表 + 查 addTime）
  )
ORDER BY f.functionId;
```

在实际实现中，查询 B 可以合并到查询 A 中（追加 addTime 列），也可以基于查询 A 的结果在 Python 中取 functionId 集合后批量查询。

#### 查询 C：有新增按钮的功能的**全部按钮**（含旧按钮）

```sql
SET PAGESIZE 0
SET FEEDBACK OFF
SET HEADING OFF
SET TAB OFF

SELECT a.functionId || '|' || a.actionId || '|' || a.parentActionId || '|' || TO_CHAR(a.addTime, 'YYYY-MM-DD') || '|' || COALESCE(aml.actionDescr, a.actionId)
FROM BSM_FUNCTION_ACTION a
LEFT JOIN BSM_FUNCTION_ACTION_ML aml 
    ON aml.organizationId = a.organizationId AND aml.functionId = a.functionId AND aml.actionId = a.actionId AND aml.languageId = 'zh_CN'
WHERE a.organizationId = 'DONGCHENG'
  AND a.activeFlag = 'Y'
  AND a.functionId IN (
    -- 有新增按钮的功能（与查询 A 的第二个 CONNECT BY 的 START WITH 相同）
    SELECT DISTINCT a2.functionId FROM BSM_FUNCTION_ACTION a2
    WHERE a2.organizationId = 'DONGCHENG'
      AND a2.activeFlag = 'Y'
      AND a2.addTime >= TO_DATE('{DATE}', 'YYYY-MM-DD')
  )
ORDER BY a.functionId, a.parentActionId, a.showSequence, a.actionId;
```

**变更说明**：原查询只返回 `addTime >= 日期` 的新增按钮。但新增按钮的父级按钮（如 ALL、BASIC、ALL_UDFOPR 等）可能在日期之前就已存在，缺少父级就无法构建树形层级。新查询返回**功能集的所有按钮**（含旧的），在 Python 后处理中区分新旧并裁剪。

---

## Step 3：组装树形结构

### 3.1 数据结构

将查询结果加载到三个内存结构中：
- `funcs: dict[functionId → (parentFunctionId, descr)]` — 全部功能
- `func_addtime: dict[functionId → addTime]` — 功能创建时间
- `full_actions: dict[functionId → [(actionId, parentActionId, descr, is_new)]]` — 全部按钮

### 3.2 输出规则（核心变更）

- **功能树**：所有在功能集内的功能都展示（新功能、旧功能、祖先功能均正常展示）
- **按钮展示规则**：
  - **新功能**（`addTime >= 用户日期`）：**不显示任何按钮**。新功能创建时系统会自动附带标准按钮（查询、新增、删除等），用户不关心这些
  - **旧功能**（`addTime < 用户日期`）：**只显示新增的自定义按钮**（`addTime >= 用户日期` 的且 actionId 含 UDF 的按钮）。标准按钮（ALL、BASIC、QRY、ADD 等）即使 addTime 达标也不显示

### 3.3 按钮树构建与裁剪

**对于旧功能**，使用 Python 构建按钮树：

1. 从 `full_actions` 构建完整的 `parentActionId → children` 映射（用于层级结构）
2. 标记新按钮集合 `new_ids = {actionId | addTime >= 用户日期}`
3. 从根（`parentActionId='0'`）开始递归遍历：
   - 如果节点在新按钮集合中 → 保留并继续遍历其子节点
   - 如果节点不在新按钮集合中（旧节点）→ **扁平化**：跳过此节点，将其子节点上挂到当前层级
   - 对同一层级的同级节点做**去重**（按中文名），避免 S02_INC_UDFOPR/S05_UDFOPR 都叫"自定义操作"时重复输出

### 3.4 树形输出

```
系统公共模块
├── 自定义导入
│   └── SO
│       └── 快递面单毛重信息批量导入
│
└── 自定义功能
    ├── 通州湾人名贴纸打印
    ├── 外贸货源信息配置
    └── 采购入库及时率报表

仓储管理系统
├── 出库操作
│   ├── 内贸发货标签打印
│   │   └── 按钮:
│   │       ├── 标准模板-客户标签打印-库存地点10*6
│   │       └── 通州湾RF客户标签打印10*6
│   ├── 波次计划
│   │   └── 按钮:
│   │       ├── 自定义操作
│   │       │   └── 通州湾瑞仕格任务重新下发
│   │       ├── 下发瑞仕格出库任务
│   │       ├── 通州湾成品指定分配：平库
│   │       └── 通州湾成品指定分配：瑞仕格
│   └── 发运订单
│       └── 按钮:
│           ├── 通州湾成品指定分配：平库
│           ├── 通州湾成品指定分配：瑞仕格
│           └── ...
└── 入库操作
    ├── SRM标签缓存表      ← 新功能，不显示按钮
    └── 【测试报表】       ← 新功能，不显示按钮
```

### 3.5 Python 组装方案

使用 Python 3 脚本（通过 heredoc 或临时文件执行）完成树形组装。核心逻辑：

```python
from collections import defaultdict

# 加载数据
funcs = {}           # fid → (parentFunctionId, descr)
func_addtime = {}    # fid → addTime
full_actions = defaultdict(list)  # fid → [(aid, pid, desc, is_new)]

# 构建功能树
# 确定哪个功能是新功能
# 对旧功能构建按钮树（只显示新增按钮）

def build_button_tree(fid):
    """构建旧功能的按钮树：只显示新增按钮，旧父节点扁平化。"""
    new_acts = [(aid, pid, desc) for aid, pid, desc, is_new in full_actions[fid] if is_new]
    if not new_acts:
        return []
    # 从全量按钮构建父链映射
    act_children = defaultdict(list)
    for aid, pid, desc, _ in full_actions[fid]:
        act_children[pid].append((aid, desc))
    # 按描述排序
    for pid in act_children:
        act_children[pid].sort(key=lambda x: x[1])
    new_ids = {aid for aid, _, _ in new_acts}
    
    def make_nodes(pid):
        result, seen = [], set()
        for aid, desc in act_children.get(pid, []):
            kids = make_nodes(aid)
            if aid in new_ids:
                if desc not in seen:
                    result.append((desc, kids))
                    seen.add(desc)
            else:
                # 旧节点：上挂其新子节点
                for item in kids:
                    if item[0] not in seen:
                        result.append(item)
                        seen.add(item[0])
        return result
    
    return make_nodes('0')
```

---

## Step 4：写入文件

1. 文件名：`outputs/flux_newfunc_tree_{YYYYMMDD}.txt`
2. 文件头：`WMS系统业务功能树（{YYYY-MM-DD} 之后新增）`
3. UTF-8 无 BOM 编码
4. Python 脚本直接写文件（不要用终端 stdout，终端可能无法渲染中文）

---

## Step 5：告知用户

输出文件路径和结果摘要，包括：
- 新增功能数量
- 显示按钮的旧功能数量
- 如果查询结果为 0，提示"指定日期之后没有新增功能"

---

## 错误处理

| 场景 | 处理方式 |
| :--- | :--- |
| 无法连接数据库 | 提示检查 `DB_CONNECTION` 配置和网络连接 |
| 日期格式不合法 | 提示用户使用 YYYY-MM-DD 格式 |
| 查询结果为 0 | 提示"指定日期之后没有新增功能"并输出空文件（仅含文件头） |
| 按钮查询返回空（无新增按钮功能） | 正常处理，仅输出功能树，不输出按钮节点 |
| 父功能在数据库中不存在 | 将该功能置于当前层级根下，加注释 `（父功能xxx不存在）` |

---

## 变更记录

| 日期 | 变更 |
| :--- | :--- |
| 2026-07-16 | **修复两个盲区**：(1) 功能查询遗漏"有新增按钮的旧功能"，UNION 第二个 CONNECT BY 修复；(2) 按钮查询新增按钮缺少父级，改为获取全量按钮 + Python 裁剪 |
| 2026-07-16 | **修复按钮过度显示**：新功能的标准按钮不应显示（与用户无关的系统自动产物）；旧功能只显示新增自定义按钮；旧父节点扁平化处理；同级去重 |

---

## 安全与约束

### 允许
- 读取项目根目录 `.env` 获取数据库连接字符串
- 执行 SELECT 查询（只读操作）
- 在 `outputs/` 目录创建 `.txt` 文件

### 禁止
- 执行 INSERT / UPDATE / DELETE / DDL 操作
- 在 `src/` 目录下创建任何文件
- 修改任何数据库对象

---

## 项目上下文

本 Skill 项目为东成 WMS 系统（Oracle 11g），数据库连接信息在项目根目录 `.env` 中配置。相关表结构参考：
- `BSM_FUNCTION` — 功能菜单表（`functionType`: M01-M04 为菜单层级）
- `BSM_FUNCTION_ML` — 功能多语言表（`languageId = 'zh_CN'`）
- `BSM_FUNCTION_ACTION` — 功能按钮权限表
- `BSM_FUNCTION_ACTION_ML` — 按钮多语言表
