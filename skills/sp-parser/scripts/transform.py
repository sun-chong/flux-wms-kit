#!/usr/bin/env python3
"""
Oracle 存储过程语法检查 - 代码转换模块

将存储过程 DDL 转换为用于 DBMS_SQL.PARSE 语法校验的影子匿名块
支持：长文本、多参数、引号标识符、末尾斜杠、多种声明方式
"""

import os
import re
import sys
import io
from pathlib import Path
from typing import Optional, Tuple

# Windows 控制台编码将在 main() 中设置

def read_file_with_encoding(file_path: str) -> str:
    """
    使用自动检测的编码读取文件（单次读取，避免重复 IO）

    参数:
        file_path: 文件路径

    返回:
        文件内容（字符串）

    优先尝试 UTF-8（现代标准），然后是 GBK（Windows 中文环境）
    """
    # 首先检查 BOM
    with open(file_path, 'rb') as f:
        raw = f.read(3)

    # 根据 BOM 确定编码
    if raw.startswith(b'\xef\xbb\xbf'):
        # UTF-8 with BOM
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return f.read()
    elif raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        # UTF-16
        with open(file_path, 'r', encoding='utf-16') as f:
            return f.read()

    # 无 BOM，尝试多个编码
    for encoding in ('utf-8', 'gbk'):
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue

    # 所有编码都失败，抛出异常
    raise RuntimeError(f"无法使用任何已知编码读取文件: {file_path}")

# 预编译正则表达式（提升性能）
_CREATE_PATTERN = re.compile(
    r'^\s*CREATE\s+(OR\s+REPLACE\s+)?(EDITIONABLE\s+|NONEDITIONABLE\s+)?',
    re.IGNORECASE | re.MULTILINE
)
_OBJ_TYPE_PATTERN = re.compile(
    r'^\s*(PROCEDURE|FUNCTION|PACKAGE|PACKAGE BODY|TRIGGER|TYPE|TYPE BODY)',
    re.IGNORECASE
)
_DRIVE_LETTER_PATTERN = re.compile(r'^[A-Za-z]:')

# 使用 frozenset 提升查找效率
SQL_KEYWORDS = frozenset([
    'CREATE', 'DROP', 'ALTER', 'BEGIN', 'DECLARE', 'END',
    'PROCEDURE', 'FUNCTION', 'PACKAGE', 'TRIGGER', 'TYPE',
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'IF', 'LOOP',
    'RETURN', 'IS', 'AS', 'THEN', 'ELSE', 'ELSIF'
])

# 搜索目录列表（已去重）
SEARCH_DIRS = [
    "",
    "src/WMS_FTEST/routine",
    "WMS_FTEST/routine",
    "outputs",
    "PROCEDURES",
    "procedures",
]

# 跳过搜索的目录
SKIP_DIRS = frozenset([
    'node_modules', '.git', '__pycache__', 'venv', '.venv', '.claude'
])


def transform_to_validation_block(raw_sql: str) -> str:
    """
    将存储过程 DDL 转换为用于语法校验的影子匿名块
    """
    sql = raw_sql.strip()
    if not sql:
        raise ValueError("输入的 SQL 代码不能为空")

    # 1. 清理末尾的 SQL*Plus 执行符 "/"
    if sql.endswith('/'):
        sql = sql[:-1].strip()

    # 2. 移除 CREATE 前缀
    clean_sql = _CREATE_PATTERN.sub('', sql)

    # 3. 检查是否包含有效的 PL/SQL 对象类型
    if not _OBJ_TYPE_PATTERN.match(clean_sql):
        raise ValueError(
            "无效的 PL/SQL 对象类型。当前支持: "
            "PROCEDURE, FUNCTION, PACKAGE, PACKAGE BODY, TRIGGER, TYPE, TYPE BODY"
        )

    # 4. 封装进影子匿名块
    return f"DECLARE\n{clean_sql}\nBEGIN\n  NULL;\nEND;"


def escape_sql_for_clob(sql: str) -> str:
    """
    将 SQL 代码转换为适用于 CLOB 赋值的格式
    - 双引单引号
    - 处理特殊字符
    """
    # 将单引号替换为两个单引号（PL/SQL 转义）
    escaped = sql.replace("'", "''")
    return escaped


def build_dbms_sql_check(clob_sql: str) -> str:
    """
    构建用于 DBMS_SQL.PARSE 语法检查的完整 SQL 块

    参数:
        clob_sql: 已转换的匿名块 SQL（已转义）

    返回:
        完整的 DBMS_SQL 检查语句
    """
    return f"""DECLARE
  c NUMBER;
  v_sql CLOB := '{clob_sql}';
BEGIN
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
END;
/"""


def process_input(input_text: str) -> dict:
    """
    处理用户输入，返回转换后的检查 SQL

    参数:
        input_text: 用户输入（可能是代码、文件路径或存储过程名）

    返回:
        包含以下键的字典:
        - raw_sql: 原始 SQL 代码
        - transformed: 转换后的匿名块
        - dbms_sql_check: 完整的 DBMS_SQL 检查语句
        - input_type: 输入类型 (code/path/name)
        - source: 来源描述
    """
    result = {
        "raw_sql": "",
        "transformed": "",
        "dbms_sql_check": "",
        "input_type": "unknown",
        "source": ""
    }

    # 1. 检查是否是文件路径
    if _is_file_path(input_text):
        result["input_type"] = "path"
        result["source"] = f"文件: {input_text}"
        try:
            result["raw_sql"] = read_file_with_encoding(input_text)
        except FileNotFoundError:
            raise FileNotFoundError(f"找不到文件: {input_text}")
        except Exception as e:
            raise RuntimeError(f"读取文件失败: {e}")

    # 2. 检查是否是存储过程名称（不包含 SQL 关键字）
    elif _is_procedure_name(input_text):
        result["input_type"] = "name"
        result["source"] = f"存储过程名: {input_text}"

        # 在项目文件夹中查找对应的 .sql 文件
        found_file = find_sql_file_by_name(input_text.strip())

        if found_file:
            result["source"] = f"文件: {found_file}"
            try:
                result["raw_sql"] = read_file_with_encoding(found_file)
            except Exception as e:
                raise RuntimeError(f"读取找到的文件失败: {e}")
        else:
            # 未找到文件，列出搜索过的路径
            raise FileNotFoundError(
                f"未找到存储过程 '{input_text}' 对应的 .sql 文件。\n"
                "请检查：\n"
                "  1. 文件是否存在于项目目录中\n"
                "  2. 文件名是否与存储过程名称匹配（不区分大小写）\n"
                "  3. 或者直接提供文件路径或完整代码"
            )

    # 3. 认为是完整代码
    else:
        result["input_type"] = "code"
        result["source"] = "直接输入的代码"
        result["raw_sql"] = input_text

    # 如果有原始代码，进行转换
    if result["raw_sql"]:
        result["transformed"] = transform_to_validation_block(result["raw_sql"])
        escaped = escape_sql_for_clob(result["transformed"])
        result["dbms_sql_check"] = build_dbms_sql_check(escaped)

    return result


def _is_file_path(text: str) -> bool:
    """判断输入是否是文件路径"""
    text = text.strip()
    # 以 .sql 结尾（最明确的文件路径标识）
    if text.lower().endswith('.sql'):
        return True
    # 驱动器路径（如 D: 或 D:\path）
    if _DRIVE_LETTER_PATTERN.match(text):
        return True
    # 相对路径：以 ./ 或 ../ 开头
    if text.startswith('./') or text.startswith('../'):
        return True
    # 包含路径分隔符且不是纯 SQL 代码（简单检查：不是以关键字开头）
    if ('/' in text or '\\' in text) and not _looks_like_sql(text):
        return True
    return False


def _looks_like_sql(text: str) -> bool:
    """检查文本是否看起来像 SQL 代码"""
    upper = text.strip().upper()
    sql_indicators = ['CREATE ', 'SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ',
                      'BEGIN ', 'DECLARE ', 'PROCEDURE ', 'FUNCTION ', 'PACKAGE ']
    return any(upper.startswith(indicator) for indicator in sql_indicators)


def _is_procedure_name(text: str) -> bool:
    """判断输入是否是存储过程名称（不包含 SQL 关键字）"""
    text = text.strip()
    upper_text = text.upper()

    # 如果包含 SQL 关键字，认为是代码
    if SQL_KEYWORDS & set(upper_text.split()):
        return False

    # 名称应该比较短
    if len(text) > 100:
        return False

    return True


def find_sql_file_by_name(procedure_name: str, search_base: str = None) -> Optional[str]:
    """在项目文件夹中查找指定名称的 .sql 文件"""
    if search_base is None:
        search_base = os.getcwd()

    # 标准化存储过程名称
    proc_name = procedure_name.strip()
    upper_name = proc_name.upper()
    if upper_name.endswith('.SQL'):
        proc_name = proc_name[:-4]
    elif upper_name.endswith('.PKG'):
        proc_name = proc_name[:-4]

    search_name = f"{proc_name}.sql"

    # 方法1：检查常见位置
    for dir_name in SEARCH_DIRS:
        dir_path = os.path.join(search_base, dir_name) if dir_name else search_base
        if os.path.isdir(dir_path):
            file_path = os.path.join(dir_path, search_name)
            if os.path.isfile(file_path):
                return file_path

    # 方法2：递归搜索
    for root, dirs, files in os.walk(search_base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if search_name.upper() in (f.upper() for f in files):
            return os.path.join(root, search_name)

    return None


def main():
    """命令行入口点"""
    # 设置 Windows 控制台输出编码为 UTF-8
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print("用法: python transform.py <存储过程代码|文件路径|存储过程名>")
        print("")
        print("示例:")
        print("  python transform.py 'CREATE OR REPLACE PROCEDURE test IS BEGIN NULL; END;/'")
        print("  python transform.py 'src/WMS_FTEST/procedures/test.sql'")
        print("  python transform.py 'MY_PROCEDURE'")
        sys.exit(1)

    input_text = sys.argv[1]

    try:
        result = process_input(input_text)

        print("=" * 60)
        print("输入类型:", result["input_type"])
        print("来源:", result["source"])
        print("=" * 60)

        if result["transformed"]:
            print("\n【转换后的匿名块】")
            print(result["transformed"])
            print("\n【完整的 DBMS_SQL 检查语句】")
            print(result["dbms_sql_check"])
        else:
            print("\n【提示】")
            print("未能在项目文件夹中找到对应的 .sql 文件")
            print("请提供完整的文件路径或存储过程代码")

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()