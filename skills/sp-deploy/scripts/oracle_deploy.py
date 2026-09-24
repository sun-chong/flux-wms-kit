#!/usr/bin/env python3
"""
Oracle 存储过程部署脚本（Python oracledb thick mode）
解决 SQLcl 在 Windows 上的 UTF-8 中文乱码问题。

用法:
    python oracle_deploy.py <sql_file_path> [--check-only]
    python oracle_deploy.py <sql_file_path> --verify

参数:
    sql_file_path  : SQL 文件路径
    --check-only   : 仅检查编译错误，不执行部署
    --verify       : 部署后验证中文编码
"""

import sys
import os
import re
import oracledb

# 项目根目录（脚本位于 .agents/skills/sp-deploy/scripts/，向上 4 级到项目根）
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))

# Oracle Instant Client 路径（与脚本同目录）
INSTANT_CLIENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oracle-instant-client", "instantclient_19_24")

# 数据库配置文件路径
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def load_db_config():
    """从项目根目录 .env 读取数据库连接配置（DB_CONNECTION）"""
    settings_path = os.path.normpath(ENV_FILE)
    if not os.path.exists(settings_path):
        print(f"错误：找不到配置文件 {settings_path}")
        sys.exit(1)

    conn_str = ""
    with open(settings_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DB_CONNECTION="):
                conn_str = line.split("=", 1)[1].strip()
                break

    if not conn_str:
        print("错误：配置文件中未找到 DB_CONNECTION")
        sys.exit(1)

    # 解析连接字符串: USER/PASSWORD@HOST:PORT/SERVICE
    match = re.match(r"([^/]+)/(.+)@([^:]+):(\d+)/(.+)", conn_str)
    if not match:
        print(f"错误：无法解析连接字符串格式")
        sys.exit(1)

    user, password, host, port, service = match.groups()
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
        "service_name": service
    }


def extract_procedure_name(sql_content):
    """从 SQL 内容中提取存储过程/函数名称"""
    patterns = [
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)*PROCEDURE\s+(\w+)",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)*FUNCTION\s+(\w+)",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)*PACKAGE\s+(?:BODY\s+)?(\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sql_content, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def init_oracle_client():
    """初始化 Oracle Instant Client (thick mode)"""
    if os.path.isdir(INSTANT_CLIENT_DIR):
        oracledb.init_oracle_client(lib_dir=INSTANT_CLIENT_DIR)
        return True
    else:
        print(f"警告：Oracle Instant Client 目录不存在: {INSTANT_CLIENT_DIR}")
        print("尝试使用 thin mode（可能不支持 Oracle 11g）")
        return False


def get_connection(config):
    """获取数据库连接"""
    try:
        conn = oracledb.connect(
            user=config["user"],
            password=config["password"],
            dsn=f"{config['host']}:{config['port']}/{config['service_name']}"
        )
        return conn
    except oracledb.Error as e:
        print(f"数据库连接失败: {e}")
        sys.exit(1)


def check_compilation_errors(conn, obj_name):
    """检查编译错误"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT line, position, text FROM user_errors WHERE name = :name ORDER BY sequence",
        {"name": obj_name}
    )
    errors = cursor.fetchall()
    cursor.close()
    return errors


def check_object_status(conn, obj_name):
    """检查对象状态"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM user_objects WHERE object_name = :name AND object_type IN ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY')",
        {"name": obj_name}
    )
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else None


def check_chinese_encoding(conn, obj_name):
    """检查存储过程中的中文是否正确编码"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT line, text FROM user_source WHERE name = :name AND text LIKE '%功能%' ORDER BY line",
        {"name": obj_name}
    )
    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        # 没有找到包含"功能"的行，可能存储过程没有中文注释
        return None, "存储过程中未找到包含'功能'的中文注释行"

    # 检查是否有乱码特征
    garbled_patterns = ["锟", "�", "ï»¿"]
    for line_num, text in rows:
        for pattern in garbled_patterns:
            if pattern in text:
                return False, f"第 {line_num} 行检测到乱码: {text.strip()[:60]}"

    # 通过 RAW 转换验证 UTF-8 编码正确性
    cursor = conn.cursor()
    cursor.execute(
        """SELECT line, RAWTOHEX(UTL_RAW.CAST_TO_RAW(SUBSTR(TEXT, 1, 30)))
           FROM user_source WHERE name = :name AND text LIKE '%功能%' AND ROWNUM = 1""",
        {"name": obj_name}
    )
    row = cursor.fetchone()
    cursor.close()

    if row:
        raw_hex = row[1]
        # "功能描述" 的 UTF-8 编码: E58A9FE883BDE68F8FE8BFB0
        if "E58A9FE883BDE68F8FE8BFB0" in raw_hex:
            return True, "中文 UTF-8 编码正确"
        else:
            return False, f"UTF-8 编码验证失败，RAW: {raw_hex}"

    return None, "无法进行编码验证"


def deploy_sql_file(sql_file_path, check_only=False, verify=False):
    """部署 SQL 文件到 Oracle 数据库"""
    # 读取 SQL 文件
    if not os.path.exists(sql_file_path):
        print(f"错误：文件不存在 {sql_file_path}")
        sys.exit(1)

    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 提取存储过程名称
    obj_name = extract_procedure_name(sql_content)
    if not obj_name:
        print("警告：无法从 SQL 文件中提取存储过程/函数名称")
        # 尝试从文件名提取
        basename = os.path.splitext(os.path.basename(sql_file_path))[0]
        obj_name = basename.upper()

    print(f"存储过程名称: {obj_name}")
    print(f"SQL 文件: {sql_file_path}")

    # 加载数据库配置
    config = load_db_config()
    print(f"数据库: {config['user']}@{config['host']}:{config['port']}/{config['service_name']}")

    # 初始化 Oracle Client
    init_oracle_client()

    # 连接数据库
    conn = get_connection(config)
    print("数据库连接成功")

    if check_only:
        # 仅检查编译错误
        errors = check_compilation_errors(conn, obj_name)
        if errors:
            print(f"\n发现 {len(errors)} 个编译错误:")
            for line, pos, text in errors:
                print(f"  第 {line} 行, 第 {pos} 列: {text.strip()}")
            conn.close()
            return False
        else:
            status = check_object_status(conn, obj_name)
            print(f"编译状态: {'无错误' if status == 'VALID' else f'状态={status}'}")
            conn.close()
            return True

    # 执行 DDL
    print("\n正在执行存储过程脚本...")
    try:
        cursor = conn.cursor()
        # 分割 SQL 语句（处理 / 结尾的 PL/SQL 块）
        # 移除末尾的 / 和空白
        sql_clean = sql_content.rstrip().rstrip("/").rstrip()
        cursor.execute(sql_clean)
        cursor.close()
        print("脚本执行成功")
    except oracledb.Error as e:
        print(f"脚本执行失败: {e}")
        conn.close()
        return False

    # 检查编译错误
    errors = check_compilation_errors(conn, obj_name)
    if errors:
        print(f"\n发现 {len(errors)} 个编译错误:")
        for line, pos, text in errors:
            print(f"  第 {line} 行, 第 {pos} 列: {text.strip()}")
        conn.close()
        return False

    status = check_object_status(conn, obj_name)
    print(f"编译状态: {status}")

    # 验证中文编码
    if verify:
        print("\n正在验证中文编码...")
        encoding_ok, msg = check_chinese_encoding(conn, obj_name)
        if encoding_ok is True:
            print(f"中文编码检查: {msg}")
        elif encoding_ok is False:
            print(f"⚠️ 中文编码异常: {msg}")
        else:
            print(f"中文编码检查: {msg}")

    conn.close()
    print(f"\n存储过程 {obj_name} 部署成功")
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python oracle_deploy.py <sql_file_path> [--check-only] [--verify]")
        sys.exit(1)

    sql_file = sys.argv[1]
    check_only = "--check-only" in sys.argv
    verify = "--verify" in sys.argv

    success = deploy_sql_file(sql_file, check_only=check_only, verify=verify)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
