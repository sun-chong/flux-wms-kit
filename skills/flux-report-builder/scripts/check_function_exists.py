#!/usr/bin/env python3
"""
FLUX WMS 功能编号验证工具
验证 FUNCTIONID 是否存在于 DEV_UDFFUNCFG 表
"""

import json
import argparse
import sys
from pathlib import Path

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database


def check_function_exists(cursor, function_id: str, org_id: str = 'ND') -> dict:
    """
    验证功能编号是否存在于 DEV_UDFFUNCFG 表

    Args:
        cursor: 数据库游标
        function_id: 功能编号
        org_id: 组织 ID（默认: ND）

    返回:
        {
            'exists': bool,
            'active_flag': str or None,
            'function_id': str
        }
    """
    cursor.execute("""
        SELECT FUNCTIONID, ACTIVEFLAG
        FROM DEV_UDFFUNCFG
        WHERE ORGANIZATIONID = :org_id
          AND FUNCTIONID = :function_id
    """, {'org_id': org_id, 'function_id': function_id})

    result = cursor.fetchone()

    if result is None:
        return {
            'exists': False,
            'active_flag': None,
            'function_id': function_id
        }

    return {
        'exists': True,
        'active_flag': result[1],
        'function_id': result[0]
    }


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 功能编号验证工具')
    parser.add_argument('function_id', help='功能编号 (FUNCTIONID)')
    parser.add_argument('--org-id', default='ND', help='组织 ID（默认: ND）')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')
    parser.add_argument('--quiet', action='store_true', help='静默模式，仅输出结果')

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

        # 验证功能是否存在
        result = check_function_exists(cursor, args.function_id, args.org_id)

        if args.quiet:
            # 静默模式：仅输出 JSON 结果
            print(json.dumps(result, ensure_ascii=False))
        else:
            # 详细模式
            if not result['exists']:
                print(f"错误: 功能 '{args.function_id}' 在系统中不存在")
                print("请先在 FLUX WMS 系统中创建该功能，创建成功后告诉我继续。")
                sys.exit(1)
            elif result['active_flag'] != 'Y':
                print(f"警告: 功能 '{args.function_id}' 存在但未激活 (ACTIVEFLAG={result['active_flag']})")
                print("是否继续执行？")
                sys.exit(2)
            else:
                print(f"功能 '{args.function_id}' 已存在，验证通过")
                sys.exit(0)

    finally:
        connection.close()


if __name__ == '__main__':
    main()
