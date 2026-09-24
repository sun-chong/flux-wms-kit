# FLUX WMS 报表构建器

## 是什么

这个 Skill 帮你把一段**简化 SQL** 自动转换成 FLUX WMS 系统能用的自定义报表，涉及9步全流程自动化处理：

1. **信息收集** → 询问功能编号、组织、SQL、报表结构、系统版本
2. **SQL转换** → 生成完整SQL（含系统字段和占位符）
3. **功能验证** → 验证功能编号在系统中存在
4. **数据源写入** → 写入SQL配置 + 多表联动
5. **JSON生成** → 基于SQL字段生成列配置JSON
6. **列配置写入** → 写入列表字段配置到数据库
7. **表单写入** → 生成表单配置并写入数据库
8. **验证完成度** → 验证所有步骤是否已正确完成
9. **清理临时文件** → 清理所有中间产物

## 怎么用

此 Skill **仅通过斜杠命令触发**，输入 `/flux-report-builder` 后触发调用。

Claude 会自动收集缺失的信息，然后按9步流程完成全部工作。

## 写 SQL 要注意什么

### 1. 大小写问题

| 内容 | 规则 | 举例 |
|:---|:---|:---|
| 你的业务字段 | 大写小写都可以，原样保留 | `CUSTOMERID`、`customerId` 都行 |
| 别名（AS） | 大写小写随你 | `AS cid` → 列名就是 `cid` |
| 4 个系统字段 | **必须小驼峰** | `addWho`、`addTime`、`editWho`、`editTime` |

### 2. 不需要写的

- `${WHERE}` 占位符——系统会自动加
- `addWho`、`addTime` 等 13 个系统字段——系统会自动追加到 SELECT 末尾
- 表别名——不写也会自动分配 A、B、C…，但建议你写了更清晰

### 3. 明细报表 vs 主表头报表

- **不特别说明** = 主表头报表，会自动加日期范围过滤（`addTime` 起止日期参数）
- **说了是明细报表/子表** = 不加日期范围过滤

### 4. V6 vs V9 版本差异

- **V9 版本**：列表字段默认可编辑文本框（`edtxt`）
- **V6 版本**：列表字段默认只读（`ro`）

## 前置准备

一次性的，配好就不用再管：

1. Python 3.7+，装一个包：`pip install oracledb`
2. 数据库连接串配在项目根目录 `.env` 的 `DB_CONNECTION` 字段
3. 操作人账号配在项目根目录 `.env` 的 `CLAUDE_CODE_AUTHOR` 字段

## 关键步骤说明

### 信息收集

向用户询问的参数：
- **功能编号 (FUNCTIONID)** — 构建报表的唯一标识
- **组织编号 (ORGANIZATIONID)** — 所属组织，如 `ND`
- **简化SQL** — 报表数据源（SELECT + FROM + WHERE）
- **报表结构** — 表头结构还是明细结构
- **系统版本** — V6 还是 V9（影响字段类型）

### 版本逻辑

| 系统版本 | 列表字段 type |
|:---|:---:|
| V9 | `edtxt`（可编辑文本框） |
| V6 | `ro`（只读） |

### 页面描述逻辑

| 报表结构 | 中文描述 | 英文描述 |
|:---|:---|:---|
| 表头结构 | 头信息 | Header Information |
| 明细结构 | 明细信息 | Detail Information |

## 脚本列表

| 脚本 | 用途 | 对应步骤 |
|:---|:---|:---:|
| `check_function_exists.py` | 验证功能编号是否存在 | 步骤3 |
| `insert_query_config.py` | 写入数据源SQL配置 | 步骤4 |
| `generate_json.py` | 生成列配置JSON | 步骤5 |
| `insert_widget.py` | 写入列配置到数据库 | 步骤6 |
| `generate_form_config.py` | 生成并写入表单配置 | 步骤7 |
| `cleanup_temp_files.py` | 清理临时文件 | 步骤9 |

详细脚本用法见 `scripts/README.md`。

## 配置

配置文件为项目根目录的 `.env`：

```dotenv
DB_CONNECTION=username/password@host:port/service_name
CLAUDE_CODE_AUTHOR=USERNAME
```

## 依赖

```bash
pip install oracledb
```