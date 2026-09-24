#!/usr/bin/env python3
"""
Oracle 存储过程语法检查 - 一站式脚本

封装完整的"转换→执行→清理"流程，确保临时文件和 __pycache__ 被自动清理。
使用 Python oracledb thick 模式，无需依赖 SQLcl（避免 Windows 控制台问题）。

用法:
    python syntax_check.py <文件路径|存储过程名|SQL代码>
    python syntax_check.py path/to/procedure.sql
    python syntax_check.py DONGCHENG_SPBCD_SKU

退出码:
    0 = 语法检查通过
    1 = 语法错误或执行异常
"""

import os
import sys
import io
import shutil
import re

# 将 scripts/ 目录加入 path，复用 transform.py 的转换逻辑
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from transform import process_input, escape_sql_for_clob, transform_to_validation_block

# Oracle Instant Client 路径（与 sp-deploy 共用；缺失时由 setup_instantclient.py 自动下载）
ORACLE_IC_DIR = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "sp-deploy", "scripts", "oracle-instant-client")
)
INSTANT_CLIENT_DIR = os.path.join(ORACLE_IC_DIR, "instantclient_19_24")
sys.path.insert(0, ORACLE_IC_DIR)
from setup_instantclient import ensure_instant_client


def load_db_config():
    """从项目根目录 .env 读取数据库连接配置（DB_CONNECTION）"""
    project_root = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
    env_file = os.path.join(project_root, ".env")

    if not os.path.isfile(env_file):
        raise FileNotFoundError(f"找不到配置文件: {env_file}")

    conn_str = ""
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DB_CONNECTION="):
                conn_str = line.split("=", 1)[1].strip()
                break

    if not conn_str:
        raise ValueError(".env 中未找到 DB_CONNECTION")

    match = re.match(r"([^/]+)/(.+)@([^:]+):(\d+)/(.+)", conn_str)
    if not match:
        raise ValueError(f"无法解析连接字符串格式: {conn_str}")

    user, password, host, port, service = match.groups()
    return user, password, host, int(port), service


def run_syntax_check(sql_content, user, password, host, port, service):
    """使用 oracledb thick 模式执行语法检查，返回 (success, output)"""
    import oracledb

    # 初始化 Oracle Instant Client（thick mode，目录缺失时自动下载）
    try:
        ensure_instant_client()
    except RuntimeError as e:
        print(f"错误：{e}")
        sys.exit(1)
    oracledb.init_oracle_client(lib_dir=INSTANT_CLIENT_DIR)

    escaped = escape_sql_for_clob(sql_content)
    lines = escaped.split('\n')

    # 构建 APPEND 语句块
    append_lines = []
    for i, line in enumerate(lines):
        if i == 0:
            append_lines.append(f"  DBMS_LOB.APPEND(v_sql, '{line}');")
        else:
            append_lines.append(f"  DBMS_LOB.APPEND(v_sql, CHR(10)||'{line}');")
    append_block = '\n'.join(append_lines)

    plsql = f"""DECLARE
  c NUMBER;
  v_sql CLOB;
BEGIN
  DBMS_LOB.CREATETEMPORARY(v_sql, TRUE);
{append_block}
  c := DBMS_SQL.OPEN_CURSOR;
  DBMS_SQL.PARSE(c, v_sql, DBMS_SQL.NATIVE);
  DBMS_SQL.CLOSE_CURSOR(c);
  DBMS_OUTPUT.PUT_LINE('SYNTAX_CHECK_PASSED');
EXCEPTION
  WHEN OTHERS THEN
    IF DBMS_SQL.IS_OPEN(c) THEN
      DBMS_SQL.CLOSE_CURSOR(c);
    END IF;
    RAISE_APPLICATION_ERROR(-20001, 'Syntax check failed: ' || SQLERRM);
END;"""

    conn = oracledb.connect(user=user, password=password, dsn=f"{host}:{port}/{service}")
    cur = conn.cursor()
    cur.callproc("DBMS_OUTPUT.ENABLE")

    try:
        cur.execute(plsql)
        return True, "SYNTAX_CHECK_PASSED"
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        return False, str(error_obj.message)
    finally:
        cur.close()
        conn.close()


def cleanup_pycache():
    """清理 scripts/ 目录下的 __pycache__"""
    pycache_dir = os.path.join(SCRIPT_DIR, "__pycache__")
    if os.path.isdir(pycache_dir):
        shutil.rmtree(pycache_dir, ignore_errors=True)


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print("用法: python syntax_check.py <文件路径|存储过程名|SQL代码>")
        print("")
        print("示例:")
        print("  python syntax_check.py src/WMS_FTEST/routine/DONGCHENG_SPBCD_SKU.sql")
        print("  python syntax_check.py DONGCHENG_SPBCD_SKU")
        sys.exit(1)

    input_text = sys.argv[1]

    try:
        # 1. 转换
        result = process_input(input_text)
        if not result.get("transformed"):
            print("错误: 无法转换输入内容")
            sys.exit(1)

        print(f"来源: {result['source']}")
        print(f"类型: {result['input_type']}")

        # 2. 加载数据库配置
        user, password, host, port, service = load_db_config()

        # 3. 执行语法检查
        print("正在执行语法检查...")
        success, output = run_syntax_check(
            result["transformed"], user, password, host, port, service
        )

        # 4. 输出结果
        if success:
            print("\n✅ SYNTAX_CHECK_PASSED")
        else:
            print(f"\n❌ 语法检查失败: {output}")
            cleanup_pycache()
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"文件错误: {e}")
        cleanup_pycache()
        sys.exit(1)
    except Exception as e:
        print(f"执行异常: {e}")
        cleanup_pycache()
        sys.exit(1)
    finally:
        # 5. 无论成功失败，始终清理 __pycache__
        cleanup_pycache()


if __name__ == "__main__":
    main()
