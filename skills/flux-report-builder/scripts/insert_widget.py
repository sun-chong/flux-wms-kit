#!/usr/bin/env python3
"""
FLUX WMS 报表配置写入工具
将 JSON 配置写入 DEV_UDFFUNCFG_WIDGET 表
"""

import json
import oracledb
import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加 scripts 目录到路径，复用公共模块
sys.path.insert(0, str(Path(__file__).parent))
from query_dictionary import load_db_config, connect_database


def check_existing_record(cursor, function_id: str, widget_name: str, org_id: str = 'ND') -> bool:
    """检查记录是否已存在"""
    cursor.execute("""
        SELECT COUNT(*) FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id
          AND FUNCTIONID = :func_id
          AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})

    count = cursor.fetchone()[0]
    return count > 0


def get_current_version(cursor, org_id: str, function_id: str) -> dict:
    """
    实时查询当前版本号和乐观锁标记。
    写入前必须执行，禁止硬编码版本号。
    """
    cursor.execute("""
        SELECT currentversion, oprseqflag
        FROM DEV_UDFFUNCFG
        WHERE organizationid = :org_id AND functionid = :func_id
    """, {'org_id': org_id, 'func_id': function_id})

    result = cursor.fetchone()
    if result is None:
        raise ValueError(f"功能 {function_id} 在 DEV_UDFFUNCFG 中不存在，请先创建功能。")

    return {
        'currentversion': result[0],
        'oprseqflag': result[1]
    }


def increment_version(current_version: str) -> str:
    """版本号递增：'101.00000000' -> '102.00000000'"""
    try:
        ver_num = int(float(current_version))
        return f"{ver_num + 1}.00000000"
    except (ValueError, TypeError):
        return f"{int(datetime.now().timestamp())}.00000000"


def generate_opr_seq_flag(function_id: str = 'C0102') -> str:
    """生成操作流水标记，格式与系统一致"""
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d%H%M%S%f')[:22]
    return f"{timestamp}RA010000222114[{function_id}]"


def insert_widget(connection, function_id: str, widget_name: str,
                  json_data: dict, user: str, org_id: str = 'ND'):
    """插入新的报表配置（使用实时版本号和乐观锁）"""
    cursor = connection.cursor()
    try:
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

        # 实时获取版本号和乐观锁
        version_info = get_current_version(cursor, org_id, function_id)
        new_version = increment_version(version_info['currentversion'])
        new_opr_seq = generate_opr_seq_flag(function_id)

        insert_sql = """
        INSERT INTO DEV_UDFFUNCFG_WIDGET
        (ORGANIZATIONID, FUNCTIONID, WIDGETNAME, JSONDATA, ACTIVEFLAG,
         CURRENTVERSION, OPRSEQFLAG, ADDWHO, EDITWHO, ADDTIME, EDITTIME)
        VALUES
        (:org_id, :func_id, :widget_name, :json_data, :active_flag,
         :current_version, :opr_seq_flag, :add_who, :edit_who, SYSDATE, SYSDATE)
        """

        cursor.execute(insert_sql, {
            'org_id': org_id,
            'func_id': function_id,
            'widget_name': widget_name,
            'json_data': json_str,
            'active_flag': 'Y',
            'current_version': new_version,
            'opr_seq_flag': new_opr_seq,
            'add_who': user,
            'edit_who': user
        })

        print(f"  当前版本: {version_info['currentversion']} → 新版本: {new_version}")
        print(f" INSERT 执行成功！功能编号: {function_id}, 组件: {widget_name}")
        return True
    finally:
        cursor.close()


def update_widget(connection, function_id: str, widget_name: str,
                  json_data: dict, user: str, org_id: str = 'ND'):
    """更新已有的报表配置（使用乐观锁）"""
    cursor = connection.cursor()
    try:
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

        # 实时获取 DEV_UDFFUNCFG 的版本号（用于递增）
        version_info = get_current_version(cursor, org_id, function_id)
        new_version = increment_version(version_info['currentversion'])

        # 实时获取 Widget 表自身的 oprseqflag（用于乐观锁匹配）
        cursor.execute("""
            SELECT oprseqflag FROM DEV_UDFFUNCFG_WIDGET
            WHERE ORGANIZATIONID = :org_id
              AND FUNCTIONID = :func_id
              AND WIDGETNAME = :widget_name
        """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})
        row = cursor.fetchone()
        if row is None:
            print("  [FAIL] 记录不存在，无法更新")
            return False
        old_opr_seq = row[0]

        new_opr_seq = generate_opr_seq_flag(function_id)

        update_sql = """
        UPDATE DEV_UDFFUNCFG_WIDGET
        SET JSONDATA = :json_data,
            CURRENTVERSION = :new_version,
            OPRSEQFLAG = :new_opr_seq,
            EDITWHO = :edit_who,
            EDITTIME = SYSDATE
        WHERE ORGANIZATIONID = :org_id
          AND FUNCTIONID = :func_id
          AND WIDGETNAME = :widget_name
          AND OPRSEQFLAG = :old_opr_seq
        """

        cursor.execute(update_sql, {
            'json_data': json_str,
            'new_version': new_version,
            'new_opr_seq': new_opr_seq,
            'edit_who': user,
            'org_id': org_id,
            'func_id': function_id,
            'widget_name': widget_name,
            'old_opr_seq': old_opr_seq
        })

        if cursor.rowcount == 0:
            print("  [FAIL] 乐观锁冲突：数据已被其他用户修改，请重试")
            connection.rollback()
            return False

        print(f"  当前版本: {version_info['currentversion']} → 新版本: {new_version}")
        print(f"  UPDATE 执行成功！功能编号: {function_id}, 组件: {widget_name}")
        return True
    finally:
        cursor.close()


def verify_insertion(cursor, function_id: str, widget_name: str, org_id: str = 'ND'):
    """验证插入结果"""
    # 验证记录存在
    cursor.execute("""
        SELECT FUNCTIONID, WIDGETNAME, LENGTH(JSONDATA) AS JSON_LENGTH
        FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id AND FUNCTIONID = :func_id AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})
    result = cursor.fetchone()

    if result:
        print(f"\n验证结果:")
        print(f"  功能编号: {result[0]}")
        print(f"  组件名称: {result[1]}")
        print(f"  JSON 长度: {result[2]} 字节")

    # 验证中文字符
    cursor.execute("""
        SELECT JSON_VALUE(JSONDATA, '$.items[0].udfLabel')
        FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id AND FUNCTIONID = :func_id AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})
    result = cursor.fetchone()
    if result and result[0]:
        print(f"  第一个字段的 udfLabel: {result[0]}")

    # 验证小驼峰字段
    cursor.execute("""
        SELECT JSON_VALUE(JSONDATA, '$.items[*].field')
        FROM DEV_UDFFUNCFG_WIDGET
        WHERE ORGANIZATIONID = :org_id AND FUNCTIONID = :func_id AND WIDGETNAME = :widget_name
    """, {'org_id': org_id, 'func_id': function_id, 'widget_name': widget_name})
    result = cursor.fetchone()
    if result and result[0]:
        fields = result[0]
        print(f"  包含 addWho: {'addWho' in fields}")
        print(f"  包含 addTime: {'addTime' in fields}")
        print(f"  包含 editWho: {'editWho' in fields}")
        print(f"  包含 editTime: {'editTime' in fields}")


def main():
    parser = argparse.ArgumentParser(description='FLUX WMS 报表配置写入工具')
    parser.add_argument('function_id', help='功能编号 (FUNCTIONID)')
    parser.add_argument('json_file', help='JSON 配置文件路径')
    parser.add_argument('--widget-name', default='headerGrid',
                       choices=['headerGrid', 'detailsGrid'],
                       help='组件名称 (默认: headerGrid)')
    parser.add_argument('--config', help='数据库配置文件路径 (可选)')
    parser.add_argument('--force', action='store_true', help='强制覆盖已有记录')
    parser.add_argument('--org-id', default='ND', help='组织 ID (默认: ND)')

    args = parser.parse_args()

    # 检查 JSON 文件是否存在
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"错误: JSON 文件不存在: {args.json_file}")
        sys.exit(1)

    # 加载 JSON 数据
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 文件格式错误: {e}")
        sys.exit(1)

    # 加载数据库配置
    try:
        db_config = load_db_config(args.config)
    except Exception as e:
        print(f"错误: 无法加载数据库配置: {e}")
        sys.exit(1)

    # 从配置文件获取用户信息
    user = db_config.get('user', 'UNKNOWN')
    print(f"操作用户: {user}")

    # 连接数据库
    try:
        connection = connect_database(db_config)
    except Exception as e:
        print(f"错误: 无法连接数据库: {e}")
        sys.exit(1)

    try:
        cursor = connection.cursor()
        try:
            # 检查记录是否已存在
            exists = check_existing_record(cursor, args.function_id, args.widget_name, args.org_id)
        finally:
            cursor.close()

        if exists and not args.force:
            print(f"警告: 记录已存在 (FUNCTIONID={args.function_id}, WIDGETNAME={args.widget_name})")
            print("使用 --force 参数强制覆盖")
            sys.exit(1)

        # 执行插入或更新
        success = False
        if exists:
            success = update_widget(connection, args.function_id, args.widget_name, json_data, user, args.org_id)
        else:
            success = insert_widget(connection, args.function_id, args.widget_name, json_data, user, args.org_id)

        if not success:
            connection.rollback()
            sys.exit(1)

        connection.commit()

        # 验证结果
        cursor = connection.cursor()
        try:
            verify_insertion(cursor, args.function_id, args.widget_name, args.org_id)
        finally:
            cursor.close()

    except Exception as e:
        connection.rollback()
        print(f"\n错误: {e}")
        sys.exit(1)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
