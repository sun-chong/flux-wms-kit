#!/usr/bin/env python3
"""
Oracle 执行脚本（Python oracledb thick mode）
解决 SQLcl 在 Windows 上的 UTF-8 中文乱码问题。

专为 flux-extconfig-gen skill 设计，执行包含中文的 INSERT SQL。
支持绑定变量，避免 SQL 注入风险。

用法:
    python oracle_insert.py <sql_file_path> [--params PARAMS]
    python oracle_insert.py --query "SELECT ..." [--params PARAMS]

参数:
    sql_file_path     : SQL 文件路径（PL/SQL 匿名块）
    --params PARAMS   : 绑定变量参数，JSON 字符串或 JSON 文件路径
                        SQL 中使用 :param_name 占位，params 中提供 {"param_name": "value"}
    --query  "SQL"    : 直接执行 SELECT 查询并输出结果，无需 SQL 文件

返回:
    0 - 执行成功
    1 - 执行失败（ORA 错误信息输出到 stderr）

编码保障:
    - Python oracledb 直接读取 UTF-8 文件并通过 OCI 写入 Oracle
    - 完全绕过 SQLcl 的 JVM 编码链（Java -> Latin-1 -> UTF-8 双重编码问题）
    - 无需 JAVA_TOOL_OPTIONS 或 NLS_LANG 环境变量
"""

import sys
import os
import re
import json
import argparse
import oracledb

# 项目根目录（脚本位于 .agents/skills/flux-extconfig-gen/scripts/，向上 5 级到项目根）
# scripts -> flux-extconfig-gen -> skills -> .agents -> 项目根
PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)

# 默认 Instant Client 路径（回退位置：复用 sp-deploy 的实例）
_DEFAULT_INSTANT_CLIENT_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..",
        "sp-deploy", "scripts",
        "oracle-instant-client", "instantclient_19_24"
    )
)

# 数据库配置文件路径
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def load_db_config():
    """从项目根目录 .env 读取数据库连接配置（DB_CONNECTION），同时解析可选的 ORACLE_CLIENT_DIR"""
    settings_path = os.path.normpath(ENV_FILE)
    if not os.path.exists(settings_path):
        print(f"错误：找不到配置文件 {settings_path}")
        sys.exit(1)

    env_values = {}
    with open(settings_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_values[key.strip()] = value.strip()

    conn_str = env_values.get("DB_CONNECTION", "")
    if not conn_str:
        print("错误：配置文件中未找到 DB_CONNECTION")
        sys.exit(1)

    match = re.match(r"([^/]+)/(.+)@([^:]+):(\d+)/(.+)", conn_str)
    if not match:
        print("错误：无法解析连接字符串格式")
        sys.exit(1)

    user, password, host, port, service = match.groups()
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
        "service_name": service,
        "oracle_client_dir": env_values.get("ORACLE_CLIENT_DIR", ""),
    }


def load_params(params_str):
    """加载绑定变量参数（JSON 字符串或 JSON 文件路径）

    Args:
        params_str: JSON 字符串（以 { 开头）或 JSON 文件路径

    Returns:
        dict: 参数字典，无参数时返回空字典
    """
    if not params_str:
        return {}
    if params_str.startswith("{"):
        return json.loads(params_str)
    with open(params_str, "r", encoding="utf-8") as f:
        return json.load(f)


def init_oracle_client(oracle_client_dir=""):
    """初始化 Oracle Instant Client (thick mode)，失败时打印警告并继续（thin mode）

    优先使用 .env 中的 ORACLE_CLIENT_DIR，回退到默认路径。
    """
    client_dir = oracle_client_dir if oracle_client_dir else _DEFAULT_INSTANT_CLIENT_DIR
    if os.path.isdir(client_dir):
        oracledb.init_oracle_client(lib_dir=client_dir)
    else:
        print(f"警告：Oracle Instant Client 目录不存在: {client_dir}")
        print("尝试使用 thin mode（可能不支持 Oracle 11g）")


def get_connection(config):
    """获取数据库连接"""
    try:
        conn = oracledb.connect(
            user=config["user"],
            password=config["password"],
            dsn=f"{config['host']}:{config['port']}/{config['service_name']}",
        )
        return conn
    except oracledb.Error as e:
        print(f"数据库连接失败: {e}")
        sys.exit(1)


def execute_sql_file(conn, sql_file_path, params=None):
    """执行 SQL 文件（PL/SQL 匿名块），支持绑定变量

    Args:
        conn: 数据库连接
        sql_file_path: SQL 文件路径
        params: 绑定变量参数字典（可选）
    """
    if not os.path.exists(sql_file_path):
        raise FileNotFoundError(f"文件不存在: {sql_file_path}")

    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_content = f.read().strip()

    # 移除 PL/SQL 匿名块末尾的 / 终止符（SQLcl 语法，Python oracledb 不需要）
    if sql_content.endswith("/"):
        sql_content = sql_content[:-1].strip()

    if not sql_content:
        raise ValueError(f"SQL 文件为空: {sql_file_path}")

    cursor = conn.cursor()
    try:
        cursor.execute(sql_content, params or {})
        print("SQL 执行成功", file=sys.stderr)
    finally:
        cursor.close()


def _filter_params_for_sql(sql, params):
    """过滤绑定变量字典，仅保留 SQL 中实际引用的键。

    oracledb 在 dict 模式下，传入 SQL 中不存在的绑定变量键会报 ORA-01036。
    此函数从 SQL 中提取 :bind_name 占位符，过滤 params 只保留匹配的键。
    """
    if not params:
        return {}
    # 宽松匹配：提取 SQL 中所有 :identifier 形式的绑定变量名。
    # 未排除字符串字面量中的同名标识符（宁可多传，避免遗漏导致 ORA-01036）。
    bind_names = set(re.findall(r':([A-Za-z_]\w*)', sql))
    return {k: v for k, v in params.items() if k in bind_names}


def execute_query(conn, sql, params=None, label="查询"):
    """执行 SELECT 查询并返回结构化结果

    Args:
        conn: 数据库连接
        sql: SELECT 查询语句（支持 :param_name 绑定变量）
        params: 绑定变量参数字典（可选，自动过滤为 SQL 中实际引用的键）
        label: 输出标签（如 "验证查询"、"查询"），用于日志区分

    Returns:
        dict: 结构化查询结果
            - success (bool): 执行是否成功
            - columns (list[str]): 列名列表
            - rows (list[tuple]): 结果行
            - count (int): 返回行数
    """
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, _filter_params_for_sql(sql, params))
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
        finally:
            cursor.close()

        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "count": len(rows),
        }
    except oracledb.Error as e:
        print(f"{label}失败: {e}")
        return {
            "success": False,
            "columns": [],
            "rows": [],
            "count": 0,
        }


def main():
    """主入口：执行 SQL 文件和/或查询"""
    parser = argparse.ArgumentParser(
        description="Oracle 执行脚本（Python oracledb thick mode，支持绑定变量）"
    )
    parser.add_argument(
        "sql_file", nargs="?", default=None,
        help="SQL 文件路径（PL/SQL 匿名块）"
    )
    parser.add_argument(
        "--params", metavar="PARAMS", default=None,
        help="绑定变量参数：JSON 字符串（以 { 开头）或 JSON 文件路径"
    )
    parser.add_argument(
        "--query", metavar="SQL", default=None,
        help="直接执行 SELECT 查询并输出结果"
    )
    args = parser.parse_args()

    # 至少需要 sql_file 或 --query 之一
    if args.query is None and args.sql_file is None:
        parser.error("需要提供 sql_file 或 --query 参数")

    # 加载绑定变量参数
    try:
        params = load_params(args.params)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"错误：无法加载参数 {args.params}: {e}")
        sys.exit(1)

    # 加载配置并连接
    db_config = load_db_config()
    init_oracle_client(db_config.get("oracle_client_dir", ""))
    conn = get_connection(db_config)

    # file_ok 跟踪 sql_file 执行状态，query_success 跟踪查询状态
    # 退出码由 sql_file 决定（主操作）；--query 作为辅助操作不影响退出码
    file_ok = True
    query_success = None
    try:
        if args.sql_file:
            execute_sql_file(conn, args.sql_file, params)

        if args.query:
            result = execute_query(conn, args.query, params, label="查询")
            query_success = result["success"]
            # 格式化输出查询结果
            if result["success"]:
                if result["count"] == 0:
                    print(f"查询：未返回数据（查询本身执行成功）")
                else:
                    header = " | ".join(result["columns"])
                    print(f"\n{header}")
                    print("-" * len(header))
                    for row in result["rows"]:
                        print(" | ".join(str(v) if v is not None else "(null)" for v in row))

        conn.commit()
    except oracledb.Error as e:
        file_ok = False
        print(f"执行失败: {e}", file=sys.stderr)
        conn.rollback()
    except (FileNotFoundError, ValueError) as e:
        file_ok = False
        print(f"错误: {e}", file=sys.stderr)
    finally:
        conn.close()

    # 退出码：有 sql_file 时由文件执行决定，仅有 --query 时由查询决定
    if args.sql_file:
        sys.exit(0 if file_ok else 1)
    else:
        sys.exit(0 if query_success else 1)


if __name__ == "__main__":
    main()
