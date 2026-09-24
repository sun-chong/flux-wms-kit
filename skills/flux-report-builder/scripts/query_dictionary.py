#!/usr/bin/env python3
"""
FLUX WMS 数据字典查询工具
查询表字段的中文名称
"""

import json
import os
import oracledb
import argparse
import sys
from pathlib import Path


def load_db_config(config_path: str = None) -> dict:
    """加载数据库连接配置和用户配置（从项目根目录 .env）"""
    if config_path is None:
        # 默认从项目根目录的 .env 读取
        # 先尝试从当前工作目录向上查找
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            candidate = parent / ".env"
            if candidate.exists():
                config_path = candidate
                break
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent.parent / ".env"

    env_values = {}
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            env_values[key.strip()] = value.strip()

    db_connection = env_values['DB_CONNECTION']

    # 解析连接字符串
    parts = db_connection.split('@')
    user_pass = parts[0].split('/')
    username = user_pass[0]
    password = user_pass[1]
    host_port_service = parts[1].split(':')
    host = host_port_service[0]
    port_service = host_port_service[1].split('/')
    port = int(port_service[0])
    service_name = port_service[1]

    # 从配置文件获取用户信息
    user = env_values.get('CLAUDE_CODE_AUTHOR', 'UNKNOWN')

    return {
        'username': username,
        'password': password,
        'host': host,
        'port': port,
        'service_name': service_name,
        'user': user
    }


def connect_database(db_config: dict):
    """连接数据库"""
    # Oracle Instant Client（复用 sp-deploy 的实例；缺失时由 setup_instantclient.py 自动下载）
    oracle_ic_dir = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "sp-deploy", "scripts", "oracle-instant-client"
    ))
    if oracle_ic_dir not in sys.path:
        sys.path.insert(0, oracle_ic_dir)
    from setup_instantclient import ensure_instant_client
    try:
        client_dir = ensure_instant_client()
        oracledb.init_oracle_client(lib_dir=client_dir)
    except RuntimeError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception:
        pass  # Instant Client 已初始化过则忽略
    return oracledb.connect(
        user=db_config['username'],
        password=db_config['password'],
        dsn=oracledb.makedsn(db_config['host'], db_config['port'], service_name=db_config['service_name'])
    )


def query_table_dictionary(cursor, table_name: str, org_id: str = 'ND') -> list:
    """
    查询表的所有字段中文名称

    Args:
        cursor: 数据库游标
        table_name: 表名
        org_id: 组织 ID (默认 'ND')

    返回:
        [
            {
                'field_name': 'FIELDNAME',
                'field_descr': '字段描述',
                'udf_field_descr': 'UDF字段描述'
            },
            ...
        ]
    """
    cursor.execute("""
        SELECT H1.FIELDNAME,
               H1ML.FIELDDESCR,
               H1ML.UDFFIELDDESCR
        FROM BSM_DATA_DICTIONARY_FIELD H1
        LEFT JOIN BSM_DATA_DICTIONARY_FIELD_ML H1ML
            ON H1ML.ORGANIZATIONID = H1.ORGANIZATIONID
            AND H1ML.WAREHOUSEID = H1.WAREHOUSEID
            AND H1ML.TABLENAME = H1.TABLENAME
            AND H1ML.FIELDNAME = H1.FIELDNAME
            AND H1ML.LANGUAGEID = 'zh_CN'
        WHERE H1.ORGANIZATIONID = :org_id
          AND H1.WAREHOUSEID = '*'
          AND H1.TABLENAME = :table_name
        ORDER BY H1.SHOWSEQUENCE, H1.FIELDNAME
    """, {'org_id': org_id, 'table_name': table_name})

    results = []
    for row in cursor.fetchall():
        results.append({
            'field_name': row[0],
            'field_descr': row[1],
            'udf_field_descr': row[2]
        })

    return results


def query_column_comments(cursor, table_name: str, field_names: list) -> dict:
    """
    查询数据库表字段注释（ALL_COL_COMMENTS.COMMENTS），作为数据字典查询的兜底

    当 BSM_DATA_DICTIONARY_FIELD 中找不到中文名称时使用此方法。

    Args:
        cursor: 数据库游标
        table_name: 表名
        field_names: 字段名列表

    返回:
        {字段名: 注释, ...}
    """
    if not field_names:
        return {}

    # 构建 IN 子句的占位符
    placeholders = ','.join([f':field_{i}' for i in range(len(field_names))])
    params = {f'field_{i}': name.upper() for i, name in enumerate(field_names)}
    params['table_name'] = table_name.upper()

    try:
        cursor.execute(f"""
            SELECT COLUMN_NAME, COMMENTS
            FROM ALL_COL_COMMENTS
            WHERE TABLE_NAME = :table_name
              AND UPPER(COLUMN_NAME) IN ({placeholders})
              AND COMMENTS IS NOT NULL
        """, params)

        result = {}
        for row in cursor.fetchall():
            original_name = next(
                (f for f in field_names if f.upper() == row[0].upper()),
                row[0]
            )
            result[original_name] = row[1]

        return result
    except Exception as e:
        print(f"  警告：查询表 {table_name} 字段注释失败: {e}")
        return {}

def query_specific_fields(cursor, table_name: str, field_names: list, org_id: str = 'ND') -> dict:
    """
    查询指定字段的中文名称

    Args:
        cursor: 数据库游标
        table_name: 表名
        field_names: 字段名列表
        org_id: 组织 ID (默认 'ND')

    返回:
        {
            'FIELDNAME': '中文名称',
            ...
        }
    """
    if not field_names:
        return {}

    # 构建 IN 子句的占位符
    placeholders = ','.join([f':field_{i}' for i in range(len(field_names))])
    params = {f'field_{i}': name for i, name in enumerate(field_names)}
    params['table_name'] = table_name
    params['org_id'] = org_id

    cursor.execute(f"""
        SELECT H1.FIELDNAME,
               H1ML.FIELDDESCR,
               H1ML.UDFFIELDDESCR
        FROM BSM_DATA_DICTIONARY_FIELD H1
        LEFT JOIN BSM_DATA_DICTIONARY_FIELD_ML H1ML
            ON H1ML.ORGANIZATIONID = H1.ORGANIZATIONID
            AND H1ML.WAREHOUSEID = H1.WAREHOUSEID
            AND H1ML.TABLENAME = H1.TABLENAME
            AND H1ML.FIELDNAME = H1.FIELDNAME
            AND H1ML.LANGUAGEID = 'zh_CN'
        WHERE H1.ORGANIZATIONID = :org_id
          AND H1.WAREHOUSEID = '*'
          AND H1.TABLENAME = :table_name
          AND H1.FIELDNAME IN ({placeholders})
    """, params)

    result = {}
    for row in cursor.fetchall():
        # 优先使用 UDF_FIELDDESCR，如果为空则使用 FIELDDESCR
        label = row[2] if row[2] else row[1]
        result[row[0]] = label

    return result


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 数据字典查询工具')
    parser.add_argument('table_name', help='表名')
    parser.add_argument('--fields', nargs='+', help='指定查询的字段名列表（可选）')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')
    parser.add_argument('--format', choices=['json', 'table', 'csv'], default='json',
                       help='输出格式 (默认: json)')

    args = parser.parse_args()

    # 加载数据库配置
    try:
        db_config = load_db_config(args.config)
    except Exception as e:
        print(f"错误: 无法加载数据库配置: {e}", file=sys.stderr)
        sys.exit(1)

    # 连接数据库
    try:
        connection = connect_database(db_config)
    except Exception as e:
        print(f"错误: 无法连接数据库: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        cursor = connection.cursor()

        if args.fields:
            # 查询指定字段
            result = query_specific_fields(cursor, args.table_name, args.fields)

            if args.format == 'json':
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif args.format == 'table':
                print(f"{'字段名':<30} {'中文名称':<30}")
                print("-" * 60)
                for field_name in args.fields:
                    label = result.get(field_name, '(未找到)')
                    print(f"{field_name:<30} {label:<30}")
            elif args.format == 'csv':
                print("字段名,中文名称")
                for field_name in args.fields:
                    label = result.get(field_name, '')
                    print(f"{field_name},{label}")
        else:
            # 查询所有字段
            results = query_table_dictionary(cursor, args.table_name)

            if args.format == 'json':
                print(json.dumps(results, ensure_ascii=False, indent=2))
            elif args.format == 'table':
                print(f"{'字段名':<30} {'字段描述':<30} {'UDF字段描述':<30}")
                print("-" * 90)
                for row in results:
                    print(f"{row['field_name']:<30} {row['field_descr'] or '':<30} {row['udf_field_descr'] or '':<30}")
            elif args.format == 'csv':
                print("字段名,字段描述,UDF字段描述")
                for row in results:
                    print(f"{row['field_name']},{row['field_descr'] or ''},{row['udf_field_descr'] or ''}")

    finally:
        connection.close()


if __name__ == '__main__':
    main()
