# 参考资料

## 数据库连接

- **配置位置**：项目根目录 `.env`（不提交 Git）
- **连接字符串**：`DB_CONNECTION` 字段（完整连接串，用户名/密码@host:port/service）
- **SQLcl 工具**：位于用户环境变量 `%OracleSQLcl%`

**使用 connect-oracle skill**
- **触发关键词**：连接数据库、Oracle查询、执行SQL、查询表数据、数据库操作
- **强制要求**：所有数据库操作必须使用此 skill，禁止直接使用 PowerShell 执行 SQL

## 数据库字典

- **索引文件**：`docs/dictionaries/00_表索引.md`
- **详细目录**：`docs/dictionaries/tables/`（每表一个 .md 文件）
- **使用场景**：需要了解表结构、字段含义时查阅
- 使用 `database-dictionary` skill 可以自动生成或更新

## PL/SQL 开发规范

- **规则文件**：`.claude/rules/plsql.md`（变量命名、异常处理、批量处理、安全编码等）
- **Oracle Skills 库**：`.claude/skills/db/`（160+ 文件，按场景索引见 `CLAUDE.md`）
